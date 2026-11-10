"""News-volume baseline for the black-swan check, from REAL daily news counts.

The old check compared a COUNT of news events with the average of calibration SEVERITY scores (a 0-10 scale), so
ordinary news volume looked like a huge spike. Now both sides are the same unit: articles per day from the news feed
(fivetran_raw_gdelt.articles). With fewer than MIN_HISTORY_DAYS of complete days there is no honest baseline, so the
function says "not enough history" instead of guessing.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

MIN_HISTORY_DAYS = 7
MIN_STD = 1.0            # a perfectly flat history must not make a +1 article look like a spike
MIN_STD_FRACTION = 0.25  # ... and noise is at least 25% of the mean for news counts

SQL_DAILY_COUNTS = """
    SELECT (seen_at AT TIME ZONE 'UTC')::date AS day, count(*) AS n
    FROM fivetran_raw_gdelt.articles
    WHERE NOT _fivetran_deleted AND seen_at IS NOT NULL
      AND (seen_at AT TIME ZONE 'UTC')::date < (now() AT TIME ZONE 'UTC')::date   -- complete days only
    GROUP BY 1 ORDER BY 1
"""
SQL_LAST_24H = """
    SELECT count(*) AS n FROM fivetran_raw_gdelt.articles
    WHERE NOT _fivetran_deleted AND seen_at >= now() - interval '24 hours'
"""


@dataclass
class NewsBaseline:
    current_24h: int
    history_days: int
    mean: float | None
    std: float | None
    zscore: float | None
    enough_history: bool
    note: str


def news_volume_zscore(current: int, daily_counts: list[int], min_days: int = MIN_HISTORY_DAYS) -> NewsBaseline:
    """z-score of today's (last 24 h) count against the daily counts of complete earlier days."""
    n = len(daily_counts)
    if n < min_days:
        return NewsBaseline(current, n, None, None, None, False,
                            f"only {n} complete day(s) of news history; need {min_days} for a baseline")
    mean = statistics.mean(daily_counts)
    std = max(statistics.pstdev(daily_counts), MIN_STD, MIN_STD_FRACTION * mean)
    return NewsBaseline(current, n, round(mean, 2), round(std, 2), round((current - mean) / std, 2), True,
                        f"baseline from {n} days: {mean:.0f} +/- {std:.0f} articles/day")


def load_news_baseline() -> NewsBaseline:
    from src.ingestion.db import run_query

    counts = [int(r["n"]) for r in run_query(SQL_DAILY_COUNTS)]
    current = int(run_query(SQL_LAST_24H)[0]["n"])
    return news_volume_zscore(current, counts)
