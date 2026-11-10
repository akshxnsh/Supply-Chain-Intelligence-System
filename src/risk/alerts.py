"""Turn an exposure + confidence into an alert decision: Notify / Watch / Log, always with the reason.

Rules (loss is loss, NO relative-size rule; thresholds are in config/risk.yaml and the trader's own settings):
  1. expected loss >= the trader's money threshold                      -> candidate for Notify
  2. stockout risk (days of stock < delay + replacement lead time)      -> candidate for Notify, whatever the amount
  3. guardrail: a LOW-confidence signal does not notify, EXCEPT when the possible loss is very large (rare-event guard);
     otherwise it is downgraded to Watch
  4. nothing triggered: Watch if expected loss >= 25% of the threshold, else Log
  5. no repeats: an alert that already notified only notifies again if the expected loss grew by the configured factor,
     the confidence band rose, or the level rose
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.risk.confidence import BANDS, ConfidenceResult
from src.risk.exposure import Exposure

LEVELS = ("log", "watch", "notify")


@dataclass
class Decision:
    level: str                             # notify | watch | log
    expected_loss_usd: float
    likelihood: float
    explanation: list[str] = field(default_factory=list)


def decide(exposure: Exposure, conf: ConfidenceResult, threshold_usd: float, cfg: dict) -> Decision:
    a = cfg["alerts"]
    if exposure.unpriced_reason:  # facts only: a loss that cannot be priced is never a loud alert
        return Decision("watch", 0.0, cfg["likelihood_by_band"][conf.band],
                        [f"cannot price this: {exposure.unpriced_reason}",
                         f"shipments worth ${exposure.value_at_risk_usd:,.0f} match the notice",
                         "unpriced -> Watch only (check the duty rate manually); it can never Notify"])
    likelihood = cfg["likelihood_by_band"][conf.band]
    expected = round(likelihood * exposure.loss_if_happens_usd, 2)
    why = [f"possible loss ${exposure.loss_if_happens_usd:,.0f} x likelihood {likelihood:.2f} ({conf.band} confidence) = expected loss ${expected:,.0f}"]
    loss_trigger = expected >= threshold_usd
    stock_trigger = exposure.stockout_risk
    why.append(f"expected loss ${expected:,.0f} {'>=' if loss_trigger else '<'} your threshold ${threshold_usd:,.0f}")
    why.extend(s.explanation for s in exposure.stock)

    if loss_trigger or stock_trigger:
        if conf.band == "low" and exposure.loss_if_happens_usd < a["rare_event_guard_usd"]:
            why.append("low confidence and the possible loss is below the rare-event guard "
                       f"(${a['rare_event_guard_usd']:,.0f}) -> Watch, not Notify")
            return Decision("watch", expected, likelihood, why)
        if conf.band == "low":
            why.append(f"rare-event guard: possible loss >= ${a['rare_event_guard_usd']:,.0f} notifies even at low confidence")
        why.append("trigger: " + " and ".join(t for t, on in (("expected loss over threshold", loss_trigger), ("stockout risk", stock_trigger)) if on))
        return Decision("notify", expected, likelihood, why)

    if expected >= a["watch_floor_fraction"] * threshold_usd:
        why.append(f"no trigger, but expected loss is at least {a['watch_floor_fraction']:.0%} of the threshold -> Watch")
        return Decision("watch", expected, likelihood, why)
    why.append("no trigger and well below the threshold -> Log only")
    return Decision("log", expected, likelihood, why)


def should_renotify(previous: dict | None, level: str, expected_loss: float, band: str, cfg: dict) -> tuple[bool, str]:
    """For an alert that wants to Notify: has it already notified, and is it now worse enough to notify again?"""
    if level != "notify":
        return False, "not a notify-level alert"
    if not previous or not previous.get("last_notified_at"):
        return True, "first notification"
    f = cfg["alerts"]["repeat_loss_increase_factor"]
    prev_loss = float(previous.get("last_notified_loss") or 0)
    if prev_loss and expected_loss >= prev_loss * f:
        return True, f"expected loss rose from ${prev_loss:,.0f} to ${expected_loss:,.0f} (x{expected_loss / prev_loss:.2f})"
    prev_band = previous.get("last_notified_band")
    if prev_band in BANDS and BANDS.index(band) > BANDS.index(prev_band):
        return True, f"confidence rose from {prev_band} to {band}"
    if previous.get("last_notified_level") != "notify":
        return True, "level rose to notify"
    return False, "already notified and not worse (repeat suppressed)"


def lead_time_days(start: date | None, today: date) -> int | None:
    return max(0, (start - today).days) if start else None
