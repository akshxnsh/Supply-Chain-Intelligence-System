import json
from src.ingestion.bq_client import (
    query_completed_orders_by_supplier,
    query_supplier_reviews,
)

def score_suppliers(candidates: list, calibration_baseline: float = None) -> str:
    """
    Score and rank alternative suppliers using weighted formula.
    Reliability is computed dynamically from completed_orders (on-time rate + defect rate)
    and supplier_reviews (average rating). Falls back to static score if no history.
    Formula: lead_time*0.30 + price*0.25 + dynamic_reliability*0.25 + geographic_risk*0.20
    """
    scored = []
    for s in candidates:
        supplier_id = s.get("id", "")

        # ── Dynamic reliability from order history ────────────────────────────
        completed = query_completed_orders_by_supplier(supplier_id)
        reviews   = query_supplier_reviews(supplier_id)

        if completed:
            on_time_count   = sum(1 for o in completed if (o.get("delay_days") or 0) <= 0)
            on_time_rate    = on_time_count / len(completed)          # 0.0 – 1.0
            avg_defects     = sum((o.get("defective_items_count") or 0) for o in completed) / len(completed)
            defect_penalty  = min(avg_defects * 0.05, 2.0)           # max 2-point penalty
            history_score   = (on_time_rate * 10) - defect_penalty    # 0 – 10
        else:
            history_score   = s.get("reliability_score", 5.0)         # static fallback
            on_time_rate    = None
            avg_defects     = None

        if reviews:
            avg_rating      = sum(r.get("rating", 3.0) for r in reviews) / len(reviews)
            review_score    = (avg_rating / 5.0) * 10                 # normalise to 0–10
        else:
            review_score    = s.get("reliability_score", 5.0)         # static fallback
            avg_rating      = None

        # Blend: 60% history-based, 40% review-based (or pure fallback if neither)
        if completed and reviews:
            dynamic_reliability = (history_score * 0.60) + (review_score * 0.40)
        elif completed:
            dynamic_reliability = history_score
        elif reviews:
            dynamic_reliability = review_score
        else:
            dynamic_reliability = s.get("reliability_score", 5.0)

        dynamic_reliability = round(max(0, min(10, dynamic_reliability)), 2)

        # ── Other scoring dimensions ──────────────────────────────────────────
        lead_score  = max(0, 10 - (s.get("lead_time_days", 30) - 7) * 0.3)
        price_score = max(0, 10 - s.get("unit_price_usd", 5) * 0.5)
        geo_risk    = s.get("geographic_risk_score", 7.0)

        total = (lead_score          * 0.30 +
                 price_score         * 0.25 +
                 dynamic_reliability * 0.25 +
                 geo_risk            * 0.20)

        scored.append({
            **s,
            "dynamic_reliability_score": dynamic_reliability,
            "on_time_rate": on_time_rate,
            "avg_defects_per_order": round(avg_defects, 2) if avg_defects is not None else None,
            "avg_review_rating": round(avg_rating, 2) if avg_rating is not None else None,
            "completed_orders_count": len(completed),
            "reviews_count": len(reviews),
            "total_score": round(total, 2),
        })

    scored.sort(key=lambda x: x["total_score"], reverse=True)
    return json.dumps(scored[:3], default=str)