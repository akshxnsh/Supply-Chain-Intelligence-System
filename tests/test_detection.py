import json
from datetime import datetime, timedelta, timezone

from src.detection import disruption_detector
from src.prediction import utils as prediction_utils


def _shipment(etd_hours_ago, journey_hours=10):
    now = datetime.now(timezone.utc)
    etd = now - timedelta(hours=etd_hours_ago)
    eta = etd + timedelta(hours=journey_hours)
    return {
        "shipment_id": "shp-1",
        "supplier_id": "sup-1",
        "product_category": "roofing_materials",
        "shipment_value_usd": 10000,
        "origin_port": "Port of Houston",
        "destination_port": "Port of Baltimore",
        "etd": etd.isoformat(),
        "eta": eta.isoformat(),
        "journey_time_hours": journey_hours,
        "route": "Port of Houston > Memphis Rail Hub > Port of Baltimore",
        "status": "in_transit",
    }


def _patch_base_detection(monkeypatch, shipment, weather_alerts):
    monkeypatch.setattr(disruption_detector, "query_recent_events", lambda hours: [])
    monkeypatch.setattr(
        disruption_detector,
        "query_business_suppliers",
        lambda business_id: [
            {
                "id": "sup-1",
                "supplier_name": "Texas Gulf Imports",
                "country": "USA",
                "product_category": "roofing_materials",
                "annual_spend_usd": 180000,
            }
        ],
    )
    monkeypatch.setattr(
        disruption_detector,
        "query_recent_weather_alerts",
        lambda hours: weather_alerts,
    )
    monkeypatch.setattr(disruption_detector, "query_tariff_updates", lambda days_back: [])
    monkeypatch.setattr(disruption_detector, "query_port_status", lambda port_name: [])
    monkeypatch.setattr(
        prediction_utils,
        "fetch_shipment_schedule",
        lambda business_id: [shipment],
    )


def test_detect_disruptions_flags_current_checkpoint_weather(monkeypatch):
    _patch_base_detection(
        monkeypatch,
        _shipment(etd_hours_ago=1),
        [{"affected_ports": "Port of Houston", "severity": 8.5}],
    )

    result = json.loads(disruption_detector.detect_disruptions("demo-business-001"))

    assert result["total_affected"] == 1
    assert "weather_alert" in result["affected_suppliers"][0]["signals"]


def test_detect_disruptions_suppresses_passed_checkpoint_weather(monkeypatch):
    _patch_base_detection(
        monkeypatch,
        _shipment(etd_hours_ago=8),
        [{"affected_ports": "Port of Houston", "severity": 8.5}],
    )

    result = json.loads(disruption_detector.detect_disruptions("demo-business-001"))

    assert result["total_affected"] == 0


def test_detect_disruptions_flags_upcoming_checkpoint_weather(monkeypatch):
    _patch_base_detection(
        monkeypatch,
        _shipment(etd_hours_ago=8),
        [{"affected_ports": "Port of Baltimore", "severity": 8.5}],
    )

    result = json.loads(disruption_detector.detect_disruptions("demo-business-001"))

    assert result["total_affected"] == 1
    assert "weather_alert" in result["affected_suppliers"][0]["signals"]


def test_detect_disruptions_tariff_uses_shipments_not_pending_orders(monkeypatch):
    monkeypatch.setattr(disruption_detector, "query_recent_events", lambda hours: [])
    monkeypatch.setattr(
        disruption_detector,
        "query_business_suppliers",
        lambda business_id: [
            {
                "id": "sup-1",
                "supplier_name": "Guangzhou Metal Works",
                "country": "China",
                "product_category": "roofing_materials",
                "annual_spend_usd": 95000,
            }
        ],
    )
    monkeypatch.setattr(
        disruption_detector,
        "query_recent_weather_alerts",
        lambda hours: [],
    )
    monkeypatch.setattr(
        disruption_detector,
        "query_tariff_updates",
        lambda days_back: [
            {
                "country_of_origin": "China",
                "product_category": "roofing_materials",
                "tariff_rate_percentage": 25.0,
                "effective_date": "2026-06-01",
            }
        ],
    )
    monkeypatch.setattr(disruption_detector, "query_port_status", lambda port_name: [])
    monkeypatch.setattr(
        prediction_utils,
        "fetch_shipment_schedule",
        lambda business_id: [
            {
                "shipment_id": "shp-1",
                "supplier_id": "sup-1",
                "product_category": "roofing_materials",
                "shipment_value_usd": 10000,
                "origin_port": "Port of Shanghai",
                "destination_port": "Port of Baltimore",
                "dispatch_timestamp": "2026-06-01T00:00:00+00:00",
                "estimated_arrival": "2026-06-20T00:00:00+00:00",
                "status": "in_transit",
            }
        ],
    )

    result = json.loads(
        disruption_detector.detect_disruptions("demo-business-001")
    )

    assert result["total_affected"] == 1
    assert result["total_cost_impact_usd"] == 2500
    supplier = result["affected_suppliers"][0]
    assert supplier["supplier_id"] == "sup-1"
    assert supplier["tariff_cost_impact_usd"] == 2500
    assert "tariff_update" in supplier["signals"]
