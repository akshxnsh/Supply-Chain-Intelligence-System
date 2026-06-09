"""Shipment route prediction and disruption matching helpers."""

from datetime import datetime, timezone
import re
from typing import Any


def fetch_shipment_schedule(business_id: str) -> list[dict[str, Any]]:
    """Return active shipments for the given business."""
    try:
        from src.ingestion.bq_client import query_supplier_timetable
    except Exception:
        return []
    return query_supplier_timetable(business_id)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def split_route(route: str) -> list[str]:
    """Split the seeded route string into ordered checkpoints."""
    return [part.strip() for part in route.split(">") if part.strip()]


def normalize_checkpoint(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def checkpoint_matches(left: str, right: str) -> bool:
    left_norm = normalize_checkpoint(left)
    right_norm = normalize_checkpoint(right)
    return bool(
        left_norm
        and right_norm
        and (
            left_norm == right_norm
            or left_norm in right_norm
            or right_norm in left_norm
        )
    )


def predict_shipment_position(
    shipment: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Estimate route progress from seeded ETD, journey time, and route."""
    if now is None:
        now = datetime.now(timezone.utc)

    route = split_route(shipment.get("route") or "")
    if not route:
        route = [
            checkpoint
            for checkpoint in (
                shipment.get("origin_port"),
                shipment.get("destination_port"),
            )
            if checkpoint
        ]

    etd = _parse_timestamp(shipment.get("etd") or shipment.get("dispatch_timestamp"))
    journey_hours = float(shipment.get("journey_time_hours") or 0)
    if journey_hours <= 0:
        eta = _parse_timestamp(shipment.get("eta") or shipment.get("estimated_arrival"))
        journey_hours = max((eta - etd).total_seconds() / 3600, 1)

    elapsed_hours = (now - etd).total_seconds() / 3600
    progress = max(0.0, min(elapsed_hours / journey_hours, 1.0))
    index = min(int(progress * len(route)), len(route) - 1)

    return {
        "current_checkpoint": route[index],
        "next_checkpoint": route[index + 1] if index + 1 < len(route) else None,
        "progress_pct": round(progress * 100, 1),
        "passed_checkpoints": route[:index],
        "upcoming_checkpoints": route[index:],
        "route": route,
    }


def predict_shipment_location(
    shipment: dict[str, Any],
    now: datetime | None = None,
) -> str:
    """Return the approximate current checkpoint for compatibility callers."""
    return predict_shipment_position(shipment, now)["current_checkpoint"]


def checkpoint_is_current_or_upcoming(
    checkpoint: str,
    shipment: dict[str, Any],
    now: datetime | None = None,
) -> bool:
    position = predict_shipment_position(shipment, now)
    return any(
        checkpoint_matches(checkpoint, route_checkpoint)
        for route_checkpoint in position["upcoming_checkpoints"]
    )


def extract_matching_route_checkpoints(
    text: str,
    shipment: dict[str, Any],
) -> list[str]:
    """Return seeded route checkpoints mentioned by a signal."""
    if not text:
        return []
    return [
        checkpoint
        for checkpoint in split_route(shipment.get("route") or "")
        if checkpoint_matches(checkpoint, text)
    ]


def extract_ports_from_headline(headline: str) -> list[str]:
    """Return lightweight capitalized-name candidates from a headline."""
    if not headline:
        return []
    candidates = re.findall(r"\b(?:Port of )?[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3}", headline)
    return [candidate.strip().lower() for candidate in candidates]


def affected_weather_checkpoints(weather_alert: dict[str, Any]) -> list[str]:
    affected = weather_alert.get("affected_ports", "")
    return [part.strip() for part in affected.split(",") if part.strip()]


def is_port_affected(
    port: str,
    weather_alerts: list[dict[str, Any]],
    port_status: list[dict[str, Any]],
) -> bool:
    """Return True when a port is affected by weather or port activity."""
    if not port:
        return False
    for weather in weather_alerts:
        for affected in affected_weather_checkpoints(weather):
            if checkpoint_matches(port, affected):
                return True
    for status in port_status:
        name = status.get("port_name", "")
        if checkpoint_matches(port, name) and (
            status.get("strike_flag")
            or status.get("congestion_score", 0) > 5.0
        ):
            return True
    return False


def match_news_to_shipment(
    news_item: dict[str, Any],
    shipment: dict[str, Any],
    now: datetime,
    weather_alerts: list[dict[str, Any]],
    port_status: list[dict[str, Any]],
) -> bool:
    """Return True when news mentions a current/upcoming route checkpoint."""
    headline = news_item.get("headline", "")
    for checkpoint in extract_matching_route_checkpoints(headline, shipment):
        if checkpoint_is_current_or_upcoming(checkpoint, shipment, now):
            return True

    for port in extract_ports_from_headline(headline):
        if checkpoint_is_current_or_upcoming(port, shipment, now):
            return is_port_affected(port, weather_alerts, port_status)
    return False
