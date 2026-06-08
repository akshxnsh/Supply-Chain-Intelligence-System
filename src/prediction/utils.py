"""Utility functions for shipment location prediction and news‑port matching.

These helpers are used by the disruption detector to reduce false alerts.
"""

from datetime import datetime, timezone
import re
from typing import List, Dict, Any

# ---------------------------------------------------------------------------
# Fetch shipment schedule (wrapper around the BigQuery client function).
# ---------------------------------------------------------------------------
def fetch_shipment_schedule(business_id: str) -> List[Dict[str, Any]]:
    """Return active shipments for the given business.

    The underlying query is defined in ``src.ingestion.bq_client`` as
    ``query_supplier_timetable``.  If that function returns an empty list (e.g.
    because the BigQuery dependency is missing), this helper simply propagates
    the empty result.
    """
    try:
        from src.ingestion.bq_client import query_supplier_timetable
    except Exception:
        return []
    return query_supplier_timetable(business_id)

# ---------------------------------------------------------------------------
# Predict current port based on dispatch time, ETA and total distance.
# ---------------------------------------------------------------------------
def predict_shipment_location(shipment: Dict[str, Any], now: datetime = None) -> str:
    """Estimate the current port of a shipment.

    If the shipment is past its estimated arrival, the destination port is
    returned.  Otherwise we compute the fraction of the route completed using
    average speed and map that fraction to either the origin or destination
    port (a simple linear approximation – sufficient for the current use‑case).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    dispatch = shipment.get("dispatch_timestamp")
    eta = shipment.get("estimated_arrival")
    if not dispatch or not eta:
        # Fallback to origin port if timestamps are missing.
        return shipment.get("origin_port", "")

    # Ensure timestamps are aware datetime objects.
    if isinstance(dispatch, str):
        dispatch = datetime.fromisoformat(dispatch.rstrip('Z')).replace(tzinfo=timezone.utc)
    if isinstance(eta, str):
        eta = datetime.fromisoformat(eta.rstrip('Z')).replace(tzinfo=timezone.utc)

    if now >= eta:
        return shipment.get("destination_port", "")

    # Simple linear model: if less than 50% of the time elapsed, we assume the
    # shipment is still at the origin port; otherwise it is considered to be at
    # the destination port.  More sophisticated models could interpolate along a
    # route, but this keeps the implementation lightweight.
    total_seconds = (eta - dispatch).total_seconds()
    elapsed_seconds = (now - dispatch).total_seconds()
    if total_seconds == 0:
        return shipment.get("origin_port", "")
    progress = elapsed_seconds / total_seconds
    return shipment.get("destination_port" if progress >= 0.5 else "origin_port", "")

# ---------------------------------------------------------------------------
# Extract port or city names from a news headline.
# ---------------------------------------------------------------------------
def extract_ports_from_headline(headline: str) -> List[str]:
    """Return a list of capitalised words that look like port or city names.

    This is a very lightweight heuristic: we capture capitalised words that are
    at least three characters long.  In production you would replace this with a
    proper NER model.
    """
    if not headline:
        return []
    # Find words that start with a capital letter and are not at the very start
    # of the sentence (to avoid generic words like "The").
    candidates = re.findall(r"(?<!^)(?<!\s)[A-Z][a-z]{2,}", headline)
    # Normalise to lower case for comparison.
    return [c.lower() for c in candidates]

# ---------------------------------------------------------------------------
# Determine if a port is currently affected by weather or port activity.
# ---------------------------------------------------------------------------
def is_port_affected(port: str, weather_alerts: List[Dict[str, Any]], port_status: List[Dict[str, Any]]) -> bool:
    """Return True if *port* appears in any weather ``affected_ports`` list or
    has a strike/congestion flag in ``port_status``.
    """
    if not port:
        return False
    port_lc = port.lower()
    # Weather alerts
    for w in weather_alerts:
        affected = w.get("affected_ports", "")
        if affected and port_lc in affected.lower():
            return True
    # Port activity
    for p in port_status:
        name = p.get("port_name", "").lower()
        if name == port_lc and (p.get("strike_flag") or p.get("congestion_score", 0) > 5.0):
            return True
    return False

# ---------------------------------------------------------------------------
# Match a news item to a shipment based on port mentions and current impact.
# ---------------------------------------------------------------------------
def match_news_to_shipment(news_item: Dict[str, Any], shipment: Dict[str, Any], now: datetime,
                           weather_alerts: List[Dict[str, Any]], port_status: List[Dict[str, Any]]) -> bool:
    """Return True if the news headline mentions the shipment's current port (or its city)
    and that port is confirmed to be affected.
    """
    headline = news_item.get("headline", "")
    mentioned_ports = extract_ports_from_headline(headline)
    current_port = predict_shipment_location(shipment, now).lower()
    if current_port in mentioned_ports:
        return is_port_affected(current_port, weather_alerts, port_status)
    return False
