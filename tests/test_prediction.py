from datetime import datetime, timedelta, timezone

from src.prediction.utils import predict_shipment_position


def _shipment(etd, journey_hours=10):
    return {
        "etd": etd.isoformat(),
        "journey_time_hours": journey_hours,
        "route": "Port of Houston > Memphis Rail Hub > Port of Baltimore",
    }


def test_predict_shipment_position_early_in_route():
    now = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)
    shipment = _shipment(now - timedelta(hours=1))

    position = predict_shipment_position(shipment, now)

    assert position["current_checkpoint"] == "Port of Houston"
    assert position["next_checkpoint"] == "Memphis Rail Hub"
    assert position["passed_checkpoints"] == []


def test_predict_shipment_position_later_in_route_marks_passed_checkpoints():
    now = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)
    shipment = _shipment(now - timedelta(hours=8))

    position = predict_shipment_position(shipment, now)

    assert position["current_checkpoint"] == "Port of Baltimore"
    assert position["passed_checkpoints"] == ["Port of Houston", "Memphis Rail Hub"]
    assert position["upcoming_checkpoints"] == ["Port of Baltimore"]
