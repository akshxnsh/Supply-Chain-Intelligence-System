"""ECB euro reference exchange rates (free, no key) via the ECB Data Portal SDMX API.

Docs: https://data.ecb.europa.eu/help/api/data
Series: EXR / D.<CCY>.EUR.SP00.A  (daily average, units of <CCY> per 1 EUR). Published once per
working day around 16:00 CET. Cross rates (e.g. CNY per USD) are computed in code from these.
Only ~30 currencies exist; a supplier country with another currency simply has no FX signal.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from src.fetchers.http import FetchError, get_json

URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.{ccys}.EUR.SP00.A"
DEFAULT_CURRENCIES = ("USD", "CNY", "KRW", "INR", "JPY", "GBP", "MXN", "TRY", "VND", "THB", "BRL", "CAD", "PLN")


def rate_params(since: date | None = None, last_n: int | None = None) -> dict:
    p: dict = {"format": "jsondata"}
    if since:
        p["startPeriod"] = since.isoformat()
    elif last_n:
        p["lastNObservations"] = last_n
    return p


def parse_rates(payload: dict) -> list[dict]:
    """SDMX-JSON -> rows (currency, rate_date, eur_rate)."""
    try:
        struct = payload["structure"]["dimensions"]
        ccy_idx = next(i for i, d in enumerate(struct["series"]) if d["id"] == "CURRENCY")
        ccy_values = [v["id"] for v in struct["series"][ccy_idx]["values"]]
        periods = [v["id"] for v in struct["observation"][0]["values"]]
        series = payload["dataSets"][0]["series"]
    except (KeyError, IndexError, StopIteration) as exc:
        raise FetchError(f"unexpected ECB response shape: {exc!r}") from exc

    rows = []
    for key, s in series.items():
        ccy = ccy_values[int(key.split(":")[ccy_idx])]
        for obs_idx, obs in (s.get("observations") or {}).items():
            if obs and obs[0] is not None:
                rows.append({"currency": ccy, "rate_date": periods[int(obs_idx)], "eur_rate": float(obs[0])})
    return sorted(rows, key=lambda r: (r["currency"], r["rate_date"]))


def fetch_rates(currencies: Sequence[str] = DEFAULT_CURRENCIES, since: date | None = None,
                last_n: int | None = None, **http_kwargs) -> list[dict]:
    url = URL.format(ccys="+".join(currencies))
    payload = get_json(url, rate_params(since, last_n if since is None else None), **http_kwargs)
    return parse_rates(payload)
