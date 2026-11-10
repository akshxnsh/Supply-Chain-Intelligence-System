"""Step 7 tests: confidence, signals, matching, exposure, alert rules and persistence (constructed scenarios)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.risk.alerts import decide, lead_time_days, should_renotify
from src.risk.config import load_config
from src.risk.confidence import ConfidenceInput, compute_confidence
from src.risk.exposure import CompanyData, compute_exposure, stock_for_category
from src.risk.geo import PortIndex, haversine_km, norm_place
from src.risk.matching import match_all, match_delay, match_fx, match_tariff, product_matches, same_country
from src.risk.pipeline import AlertRow, best_precision, evaluate, persist
from src.risk.signals import (Signal, signals_from_disasters, signals_from_events, signals_from_forecast,
                              signals_from_fx, usd_per_unit)

CFG = load_config()
TODAY = date(2026, 11, 10)


def ts(days):  # an aware datetime `days` from TODAY at 00:00 UTC
    return datetime.combine(TODAY + timedelta(days=days), datetime.min.time(), tzinfo=timezone.utc)


PORT_ROWS = [
    {"location_id": "p-bal", "kind": "port", "name": "Baltimore", "country": "United States", "lat": 39.27, "lon": -76.58},
    {"location_id": "p-ham", "kind": "port", "name": "Hamburg", "country": "Germany", "lat": 53.54, "lon": 9.97},
    {"location_id": "p-bus", "kind": "port", "name": "Busan", "country": "South Korea", "lat": 35.1, "lon": 129.04},
    {"location_id": "p-la", "kind": "port", "name": "Los Angeles-Long Beach", "country": "United States", "lat": 33.74, "lon": -118.27},
    {"location_id": "p-nor", "kind": "port", "name": "Port of Virginia", "country": "United States", "lat": 36.9, "lon": -76.3},
    {"location_id": "c-suez", "kind": "chokepoint", "name": "Suez Canal", "country": None, "lat": 30.59, "lon": 32.43},
]
PORTS = PortIndex(PORT_ROWS)


def shipment(sid="shp-001", route="Port of Hamburg > English Channel > Atlantic Crossing > Port of Baltimore", etd=-12, eta=7,
             country="Germany", category="auto_parts", value=182000.0, supplier="sup-001", origin="Port of Hamburg",
             dest="Port of Baltimore"):
    return {"shipment_id": sid, "supplier_id": supplier, "supplier_name": "Bavarian Parts GmbH", "country": country,
            "product_category": category, "shipment_value_usd": value, "origin_port": origin, "destination_port": dest,
            "etd": ts(etd).isoformat(), "eta": ts(eta).isoformat(), "journey_time_hours": (eta - etd) * 24.0, "route": route,
            "status": "in_transit"}


def company(inventory=20000.0, lead=3.0):
    orders = [{"product_category": "auto_parts", "order_value_usd": v, "required_by_date": TODAY + timedelta(days=d)}
              for v, d in [(58400, 14), (41200, 18), (78000, 21), (24600, 25)]]
    return CompanyData(orders, {"auto_parts": inventory}, {"auto_parts": lead},
                       {"auto_parts": {"name": "Harrisburg Auto Parts", "country": "USA"}})


def delay_signal(**kw):
    base = dict(signal_id="s1", dedupe_key="s1", kind="delay", source="gdelt", source_class="news", event_type="port_strike",
                title="Baltimore dockworkers strike", status="expected", reference_date=TODAY, locations=["Baltimore"],
                countries=["United States"], start=TODAY + timedelta(days=5), end=TODAY + timedelta(days=7),
                expected_delay_days=5.0, independent_sources=3, date_clarity="explicit", location_clarity="explicit")
    base.update(kw)
    return Signal(**base)


# -- config ------------------------------------------------------------------------------------------------

def test_config_is_complete_and_weights_sum_to_one():
    assert set(CFG["likelihood_by_band"]) == {"high", "medium", "low"}
    assert CFG["likelihood_by_band"]["high"] > CFG["likelihood_by_band"]["medium"] > CFG["likelihood_by_band"]["low"]
    assert abs(sum(CFG["confidence"]["weights"].values()) - 1.0) < 1e-9
    assert CFG["alerts"]["default_notify_threshold_usd"] > 0 and CFG["alerts"]["rare_event_guard_usd"] > CFG["alerts"]["default_notify_threshold_usd"]


# -- confidence ---------------------------------------------------------------------------------------------

def test_official_notice_beats_forecast_beats_single_news():
    def conf(**kw):
        return compute_confidence(ConfidenceInput(match_precision="port", reference_date=TODAY, today=TODAY, **kw), CFG)

    notice = conf(source_class="official_notice", date_clarity="explicit", location_clarity="explicit")
    forecast = conf(source_class="forecast_model", days_ahead=2)
    news1 = conf(source_class="news", independent_sources=1, date_clarity="implied", location_clarity="implied")
    assert notice.score > forecast.score > news1.score
    assert notice.band == "high" and news1.band == "low"
    news_clear = conf(source_class="news", independent_sources=1, date_clarity="explicit", location_clarity="explicit")
    news_three = conf(source_class="news", independent_sources=3, date_clarity="explicit", location_clarity="explicit")
    assert news_clear.band == "medium" and news_three.band == "high"   # confirmation by independent outlets lifts a news signal
    assert any("official notice" in r for r in notice.reasons) and any("1 independent outlet" in r for r in news1.reasons)


def test_confirmation_has_diminishing_returns_after_three():
    def score(n):
        return compute_confidence(ConfidenceInput(source_class="news", independent_sources=n, date_clarity="explicit",
                                                  location_clarity="explicit", match_precision="port",
                                                  reference_date=TODAY, today=TODAY), CFG).parts["confirmation"]

    assert score(1) < score(2) < score(3) < score(4) and score(4) == score(9) == 1.0
    assert score(2) - score(1) > 0 and score(4) - score(3) < score(3) - score(2) + 0.05


def test_forecast_confidence_falls_with_days_ahead_and_age_matters():
    f = lambda d: compute_confidence(ConfidenceInput(source_class="forecast_model", days_ahead=d, match_precision="port",
                                                     reference_date=TODAY, today=TODAY), CFG)
    assert f(1).score > f(4).score > f(8).score and f(30).parts["forecast_distance"] == CFG["confidence"]["forecast_distance"]["floor"]
    old = compute_confidence(ConfidenceInput(source_class="news", independent_sources=2, match_precision="port",
                                             reference_date=TODAY - timedelta(days=20), today=TODAY), CFG)
    new = compute_confidence(ConfidenceInput(source_class="news", independent_sources=2, match_precision="port",
                                             reference_date=TODAY, today=TODAY), CFG)
    assert new.score > old.score and old.parts["age"] == 0.3


def test_parts_that_do_not_apply_are_left_out_not_punished():
    c = compute_confidence(ConfidenceInput(source_class="official_alert", match_precision="region"), CFG)
    assert set(c.parts) == {"source", "match"} and 0.5 < c.score < 1.0
    country = compute_confidence(ConfidenceInput(source_class="official_alert", match_precision="country"), CFG)
    port = compute_confidence(ConfidenceInput(source_class="official_alert", match_precision="port"), CFG)
    assert port.score > country.score


# -- places --------------------------------------------------------------------------------------------------

def test_place_names_and_distances():
    assert norm_place("Port of Houston (US-TX)") == "houston"
    assert PORTS.find("Port of Baltimore").name == "Baltimore" and PORTS.find("Los Angeles").name == "Los Angeles-Long Beach"
    assert PORTS.find("Atlantic Crossing") is None and PORTS.kind_of("Suez") == "chokepoint"
    assert PORTS.country_of("Port of Hamburg") == "Germany"
    assert 250 < haversine_km(39.27, -76.58, 36.9, -76.3) < 280   # Baltimore - Norfolk is about 265 km
    assert same_country("USA", "United States") and not same_country("Germany", "China")


# -- signals ------------------------------------------------------------------------------------------------------

def event_row(**kw):
    base = {"event_id": "news:c1", "source_type": "news", "source_ref": "c1", "relevant": True, "event_type": "port_strike",
            "status": "expected", "direction": "delay", "locations": ["Baltimore"], "countries": ["United States"], "products": [],
            "start_date": TODAY + timedelta(days=5), "end_date": TODAY + timedelta(days=7), "rate_percent": None,
            "date_clarity": "explicit", "location_clarity": "explicit", "summary": "Strike at Baltimore",
            "independent_sources": 3, "reference_date": TODAY}
    base.update(kw)
    return base


def test_events_become_delay_or_tariff_signals():
    delay, tariff, ignored = signals_from_events([
        event_row(),
        event_row(event_id="notice:n1", source_type="notice", source_ref="n1", event_type="tariff_or_trade_rule", direction="higher_cost",
                  countries=["Germany"], products=["auto parts"], rate_percent=25.0),
        event_row(event_id="news:c9", relevant=False)], CFG, TODAY)[:3] + [None]
    assert delay.kind == "delay" and delay.source_class == "news" and delay.expected_delay_days == CFG["default_delay_days"]["port_strike"]
    assert tariff.kind == "tariff" and tariff.source_class == "official_notice" and tariff.rate_percent == 25.0 and not tariff.rate_assumed
    assert len(signals_from_events([event_row(relevant=False)], CFG, TODAY)) == 0
    no_rate = signals_from_events([event_row(event_type="tariff_or_trade_rule", direction="higher_cost")], CFG, TODAY)[0]
    assert no_rate.rate_assumed and no_rate.rate_percent == CFG["loss_model"]["assumed_tariff_increase_pct"]


def test_signal_window_and_now_vs_headsup():
    s = delay_signal()
    assert s.window(TODAY, CFG) == (TODAY + timedelta(days=5), TODAY + timedelta(days=7)) and not s.is_now(TODAY)
    happened = delay_signal(status="happened", start=None, end=None)
    assert happened.window(TODAY, CFG)[0] == TODAY and happened.is_now(TODAY)
    unknown = delay_signal(start=None, end=None)
    assert unknown.window(TODAY, CFG) == (TODAY, TODAY + timedelta(days=CFG["horizon_days"]))
    assert lead_time_days(s.start, TODAY) == 5 and lead_time_days(None, TODAY) is None


def test_disasters_only_orange_red_with_coordinates():
    rows = [{"event_id": "TC-1", "event_type": "TC", "name": "Storm", "alert_level": "Red", "is_current": True, "lat": 30.0, "lon": -75.0,
             "country": None, "from_date": ts(-1), "to_date": ts(3), "date_modified": ts(0), "report_url": "http://x"},
            {"event_id": "FL-2", "event_type": "FL", "name": "Flood", "alert_level": "Green", "is_current": True, "lat": 1, "lon": 1,
             "from_date": ts(0), "to_date": ts(1), "date_modified": ts(0)}]
    sigs = signals_from_disasters(rows, CFG, TODAY)
    assert len(sigs) == 1 and sigs[0].radius_km == 500 and sigs[0].event_type == "severe_weather" and sigs[0].source_class == "official_alert"


def test_forecast_signal_per_location_covers_breach_days():
    base = {"location_id": "p-bal", "wind_gust_max_kmh": 20.0, "wave_height_max_m": None, "precipitation_sum_mm": 0.0}
    rows = [{**base, "forecast_date": TODAY + timedelta(days=d), "wind_gust_max_kmh": g} for d, g in [(1, 20.0), (2, 95.0), (3, 110.0), (4, 30.0)]]
    (sig,) = signals_from_forecast(rows, PORTS, CFG, TODAY)
    assert sig.locations == ["Baltimore"] and sig.start == TODAY + timedelta(days=2) and sig.end == TODAY + timedelta(days=3)
    assert sig.days_ahead == 2 and sig.source_class == "forecast_model" and "110" in sig.title
    assert signals_from_forecast([{**r, "location_id": "unknown"} for r in rows], PORTS, CFG, TODAY) == []


def test_fx_signal_when_supplier_currency_strengthens():
    hist = {TODAY - timedelta(days=30): {"USD": 1.10, "CNY": 8.00, "EUR": 1.0},
            TODAY: {"USD": 1.10, "CNY": 7.70}}                       # CNY per EUR fell -> CNY stronger
    assert usd_per_unit({"USD": 1.1, "CNY": 8.0}, "CNY") == pytest.approx(0.1375) and usd_per_unit({"USD": 1.1}, "EUR") == 1.1
    (sig,) = signals_from_fx(hist, CFG, TODAY)
    assert sig.fx_currency == "CNY" and sig.fx_move_pct == pytest.approx(3.9, abs=0.05) and "China" in sig.countries
    weaker = {TODAY - timedelta(days=30): {"USD": 1.10, "CNY": 8.00}, TODAY: {"USD": 1.10, "CNY": 8.20}}
    assert signals_from_fx(weaker, CFG, TODAY) == []


# -- matching ------------------------------------------------------------------------------------------------------

def test_expected_strike_matches_when_the_ship_will_be_there_then():
    m = match_delay(delay_signal(), shipment(), PORTS, CFG, TODAY)
    assert m and m.precision == "port" and m.checkpoint == "Port of Baltimore"
    assert m.window[0] <= TODAY + timedelta(days=7) and m.window[1] >= TODAY + timedelta(days=5)


def test_expected_strike_far_in_the_future_or_already_passed_does_not_match():
    far = delay_signal(start=TODAY + timedelta(days=40), end=TODAY + timedelta(days=42))
    assert match_delay(far, shipment(), PORTS, CFG, TODAY) is None
    passed = delay_signal(locations=["Hamburg"], countries=[], status="happened", start=TODAY - timedelta(days=1), end=TODAY)
    assert match_delay(passed, shipment(), PORTS, CFG, TODAY) is None     # the ship left Hamburg 12 days ago


def test_country_level_and_distance_matches_have_lower_precision():
    country = delay_signal(locations=[], countries=["Germany"], start=TODAY, end=TODAY + timedelta(days=3))
    assert match_delay(country, shipment(), PORTS, CFG, TODAY).precision == "country"
    storm = delay_signal(source="gdacs", source_class="official_alert", event_type="severe_weather", locations=[], countries=[],
                         lat=37.5, lon=-75.0, radius_km=500.0, status="ongoing", start=TODAY, end=TODAY + timedelta(days=6))
    m = match_delay(storm, shipment(), PORTS, CFG, TODAY)
    assert m and m.precision == "region" and m.checkpoint == "Port of Baltimore"
    suez = delay_signal(locations=["Suez Canal"], countries=[], start=TODAY + timedelta(days=1), end=TODAY + timedelta(days=3))
    ship = shipment(route="Port of Hamburg > Suez Canal > Port of Busan", dest="Port of Busan", eta=15)
    assert match_delay(suez, ship, PORTS, CFG, TODAY).precision == "chokepoint"
    assert best_precision([match_delay(country, shipment(), PORTS, CFG, TODAY), match_delay(delay_signal(), shipment(), PORTS, CFG, TODAY)]) == "port"


def tariff_signal(**kw):
    base = dict(signal_id="t1", dedupe_key="t1", kind="tariff", source="federal_register", source_class="official_notice",
                event_type="tariff_or_trade_rule", title="25% duty on German auto parts", status="expected", reference_date=TODAY,
                countries=["Germany"], products=["auto parts"], start=TODAY + timedelta(days=5), rate_percent=25.0,
                date_clarity="explicit", location_clarity="explicit")
    base.update(kw)
    return Signal(**base)


def test_tariff_matches_origin_product_and_effective_date():
    assert match_tariff(tariff_signal(), shipment(), PORTS, CFG, TODAY)                       # eta +7 >= effective +5
    assert match_tariff(tariff_signal(start=TODAY + timedelta(days=20)), shipment(), PORTS, CFG, TODAY) is None  # arrives before
    assert match_tariff(tariff_signal(countries=["China"]), shipment(), PORTS, CFG, TODAY) is None
    assert match_tariff(tariff_signal(products=["bananas"]), shipment(), PORTS, CFG, TODAY) is None
    assert match_tariff(tariff_signal(products=[]), shipment(), PORTS, CFG, TODAY)            # country-wide duty
    assert match_tariff(tariff_signal(countries=[], products=[]), shipment(), PORTS, CFG, TODAY) is None
    assert product_matches(["steel bolts"], "fasteners", CFG) and not product_matches(["steel bolts"], "auto_parts", CFG)


def test_fx_matches_supplier_country_and_match_all_groups_by_signal():
    fx = Signal("fx1", "fx1", "fx", "ecb", "observed_data", "other", "EUR up", "ongoing", TODAY, countries=["Germany"],
                fx_currency="EUR", fx_move_pct=3.0)
    assert match_fx(fx, shipment(), PORTS, CFG, TODAY) and match_fx(fx, shipment(country="China"), PORTS, CFG, TODAY) is None
    grouped = match_all([fx, delay_signal(), tariff_signal(countries=["India"])], [shipment(), shipment("shp-2", country="China")], PORTS, CFG, TODAY)
    assert set(grouped) == {"fx1", "s1"} and len(grouped["fx1"]) == 1 and len(grouped["s1"]) == 2


# -- exposure ----------------------------------------------------------------------------------------------------------

def test_delay_loss_and_stockout_numbers():
    sig = delay_signal(event_type="port_closure", expected_delay_days=10.0, start=TODAY + timedelta(days=5), end=TODAY + timedelta(days=9))
    m = match_delay(sig, shipment(), PORTS, CFG, TODAY)
    exp = compute_exposure(sig, [m], company(), CFG, TODAY)
    assert exp.components["delay_cost"] == pytest.approx(182000 * 0.005 * 10)                      # 9,100
    # orders due by arrival (today+7) + 10 days = today+17: only the 58,400 order; inventory 20,000 -> 38,400 uncovered
    assert exp.components["late_orders"] == pytest.approx(38400 * 0.30)
    assert exp.loss_if_happens_usd == pytest.approx(9100 + 11520)
    (s,) = exp.stock
    assert s.daily_demand == pytest.approx(202200 / 25) and s.days_of_stock == pytest.approx(2.5, abs=0.05)
    assert s.stockout_risk and s.act_by == TODAY and "STOCKOUT RISK" in s.explanation
    assert exp.affected_suppliers[0]["supplier_id"] == "sup-001" and exp.worst_stock is s


def test_no_stockout_when_stock_is_deep_and_shows_the_numbers():
    s = stock_for_category("auto_parts", company(inventory=400000.0), 5.0, CFG, TODAY)
    assert not s.stockout_risk and s.act_by is None and "no stockout risk" in s.explanation and "stock covers 49 days" in s.explanation
    assert stock_for_category("auto_parts", CompanyData([], {}, {}), 5.0, CFG, TODAY).days_of_stock is None


def test_act_by_is_the_last_day_to_order_a_replacement():
    # 100,000 stock, demand 202,200 over 25 days = 8,088/day -> 12.4 days of stock; delay 8 + lead 7 = 15 > 12.4 -> risk
    s = stock_for_category("auto_parts", company(inventory=100000.0, lead=7.0), 8.0, CFG, TODAY)
    assert s.stockout_risk and s.stockout_date == TODAY + timedelta(days=12) and s.act_by == TODAY + timedelta(days=5)


def test_tariff_and_fx_loss_formulas():
    t = tariff_signal()
    exp = compute_exposure(t, [match_tariff(t, shipment(), PORTS, CFG, TODAY)], company(), CFG, TODAY)
    assert exp.components["tariff"] == pytest.approx(182000 * 0.25) and not exp.assumptions
    assumed = tariff_signal(rate_percent=10.0, rate_assumed=True)
    exp2 = compute_exposure(assumed, [match_tariff(assumed, shipment(), PORTS, CFG, TODAY)], company(), CFG, TODAY)
    assert exp2.components["tariff"] == pytest.approx(18200) and "assumed" in exp2.assumptions[0]
    fx = Signal("fx1", "fx1", "fx", "ecb", "observed_data", "other", "x", "ongoing", TODAY, countries=["Germany"], fx_currency="EUR", fx_move_pct=3.0)
    exp3 = compute_exposure(fx, [match_fx(fx, shipment(), PORTS, CFG, TODAY)], company(), CFG, TODAY)
    assert exp3.components["fx"] == pytest.approx(202200 * 0.03)


# -- alert rules -------------------------------------------------------------------------------------------------------------

def make_exposure(loss, stockout=False):
    from src.risk.exposure import Exposure, StockInfo

    stock = [StockInfo("auto_parts", 1000, 100, 10.0, 5.0, 7.0, stockout, TODAY if stockout else None, TODAY if stockout else None,
                       "auto_parts: stock covers 10 days; delay 5 + lead 7 = 12 -> " + ("STOCKOUT RISK" if stockout else "no stockout risk"))]
    return Exposure(delay_signal(), [], loss, {"delay_cost": loss}, ["shp-1"], [], ["auto_parts"], stock)


def conf(band):
    from src.risk.confidence import ConfidenceResult

    return ConfidenceResult({"high": 0.8, "medium": 0.55, "low": 0.3}[band], band, [])


@pytest.mark.parametrize("loss,band,stockout,expected_level", [
    (10000, "high", False, "notify"),      # 7,000 expected >= 2,000
    (10000, "medium", False, "notify"),    # 4,000 expected
    (10000, "low", False, "watch"),        # 1,500 expected < threshold anyway; low confidence never notifies
    (30000, "low", False, "watch"),        # 4,500 expected >= threshold, but low confidence and below the rare-event guard
    (400000, "low", False, "notify"),      # rare-event guard: huge possible loss notifies even at low confidence
    (100, "high", True, "notify"),         # stockout risk notifies regardless of the amount
    (100, "low", True, "watch"),           # ... but not on a low-confidence signal
    (3000, "medium", False, "watch"),      # 1,200 expected: >= 25% of the threshold (500) but below it -> watch
    (400, "medium", False, "log"),         # 160 expected: far below -> log only
])
def test_alert_level_rules(loss, band, stockout, expected_level):
    d = decide(make_exposure(loss, stockout), conf(band), 2000.0, CFG)
    assert d.level == expected_level and d.expected_loss_usd == pytest.approx(CFG["likelihood_by_band"][band] * loss, abs=0.01)
    assert any("threshold" in line for line in d.explanation) and any("stock covers 10 days" in line for line in d.explanation)


def test_the_trader_threshold_decides():
    exp, c = make_exposure(10000), conf("high")
    assert decide(exp, c, 2000.0, CFG).level == "notify"
    assert decide(exp, c, 20000.0, CFG).level == "watch"        # expected 7,000 < 20,000 but >= 25% of it
    assert decide(exp, c, 100000.0, CFG).level == "log"


def test_no_repeat_notification_unless_worse():
    prev = {"last_notified_at": TODAY, "last_notified_loss": 5000.0, "last_notified_band": "medium", "last_notified_level": "notify"}
    assert should_renotify(None, "notify", 5000.0, "medium", CFG) == (True, "first notification")
    assert should_renotify(prev, "notify", 5200.0, "medium", CFG)[0] is False                  # +4%: suppressed
    assert should_renotify(prev, "notify", 4000.0, "medium", CFG)[0] is False
    assert should_renotify(prev, "notify", 6300.0, "medium", CFG)[0] is True                   # +26%: re-notify
    assert should_renotify(prev, "notify", 5000.0, "high", CFG)[0] is True                     # confidence rose
    assert should_renotify(prev, "watch", 9000.0, "high", CFG)[0] is False                     # only notify-level alerts notify
    assert should_renotify({**prev, "last_notified_level": "watch"}, "notify", 5000.0, "medium", CFG)[0] is True


# -- whole pipeline on a constructed scenario ----------------------------------------------------------------------------

def test_evaluate_headsup_strike_with_act_by_and_lead_time():
    sig = delay_signal(event_type="port_closure", expected_delay_days=10.0, end=TODAY + timedelta(days=9),
                       independent_sources=4, source_class="news")
    rows = evaluate([sig], [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    assert len(rows) == 1
    r = rows[0]
    assert r.alert_type == "heads_up" and r.lead_time_days == 5 and r.level == "notify"
    assert r.act_by == TODAY and "Order replacement auto_parts from Harrisburg Auto Parts" in r.action and "now" in r.action
    assert r.exposure.loss_if_happens_usd == pytest.approx(20620) and r.confidence.band in ("high", "medium")
    assert r.decision.expected_loss_usd == pytest.approx(r.exposure.loss_if_happens_usd * CFG["likelihood_by_band"][r.confidence.band], abs=0.01)
    assert any("stock covers" in line for line in r.explanation) and any(line.startswith("matched:") for line in r.explanation)


def test_evaluate_happening_now_alert_and_unmatched_signal_is_skipped():
    now_sig = delay_signal(signal_id="s2", dedupe_key="s2", status="ongoing", start=TODAY - timedelta(days=1), end=TODAY + timedelta(days=2))
    elsewhere = delay_signal(signal_id="s3", dedupe_key="s3", locations=["Busan"], countries=["South Korea"])
    rows = evaluate([now_sig, elsewhere], [shipment()], company(inventory=900000.0), PORTS, CFG, TODAY, 2000.0, "biz")
    assert [r.signal.signal_id for r in rows] == ["s2"] and rows[0].alert_type == "now" and rows[0].lead_time_days is None
    assert rows[0].act_by is None and "Warn customers" in rows[0].action and rows[0].level in ("notify", "watch", "log")


def test_evaluate_tariff_headsup_has_act_before_effective_date():
    rows = evaluate([tariff_signal()], [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    (r,) = rows
    assert r.alert_type == "heads_up" and r.act_by == TODAY + timedelta(days=4) and "25% duty" in r.action
    assert r.confidence.band == "high" and r.level == "notify" and r.exposure.loss_if_happens_usd == pytest.approx(45500)


# -- persistence ---------------------------------------------------------------------------------------------------------------

@pytest.fixture()
def alerts_db(pg_url):
    from src.ingestion.db import execute

    execute("TRUNCATE TABLE alerts")
    return pg_url


def test_persist_writes_alert_and_suppresses_repeat_notifications(alerts_db):
    from src.ingestion.db import run_query

    sig = delay_signal(event_type="port_closure", expected_delay_days=10.0, end=TODAY + timedelta(days=9), independent_sources=4)

    def run(loss_scale=1.0):
        rows = evaluate([sig], [shipment(value=182000.0 * loss_scale)], company(), PORTS, CFG, TODAY, 2000.0, "biz")
        persist(rows, CFG, now=datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc))
        return rows[0]

    first = run()
    assert first.notify_now and first.notify_reason == "first notification"
    row = run_query("SELECT * FROM alerts")[0]
    assert row["alert_type"] == "heads_up" and row["level"] == "notify" and row["lead_time_days"] == 5
    assert row["act_by"] == TODAY and row["confidence_band"] == first.confidence.band and row["stockout_risk"] is True
    assert row["affected_shipments"] == ["shp-001"] and row["affected_suppliers"][0]["supplier_id"] == "sup-001"
    assert row["evidence"] == [] and any("stock covers" in x for x in row["explanation"]) and row["notified_count"] == 1
    assert row["exposure_usd"] == pytest.approx(first.exposure.loss_if_happens_usd)

    second = run()                                             # same facts again: no repeat
    assert not second.notify_now and "repeat suppressed" in second.notify_reason
    assert run_query("SELECT notified_count FROM alerts")[0]["notified_count"] == 1

    worse = run(loss_scale=3.0)                                # expected loss grew a lot: notify again
    assert worse.notify_now and "rose" in worse.notify_reason
    final = run_query("SELECT * FROM alerts")[0]
    assert final["notified_count"] == 2 and len(run_query("SELECT 1 FROM alerts")) == 1
    assert final["last_notified_loss"] == pytest.approx(worse.decision.expected_loss_usd)
