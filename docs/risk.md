# How an alert is decided (step 7)

Code: `src/risk/` - all thresholds in `config/risk.yaml` (every number there is our own judgment, stated as an estimate).

1. **Signals** (`signals.py`): every source becomes the same kind of signal: what, where (ports / countries / products), when
   (window), direction (delay / higher cost), source class, confidence inputs.
   News + notices come from the reader's `events` table, disasters from GDACS (Orange/Red only), forecasts from Open-Meteo
   (thresholds in config), exchange-rate moves from the ECB.
2. **Matching** (`matching.py`): delay signals are checked against WHERE each shipment will be at that time
   (`checkpoint_windows` in `src/prediction/utils.py`, same equal-segment assumption as the old position code). A signal that
   names a port on the route and overlaps the time the ship is there matches at *port* precision; a disaster within its radius at
   *region*; only a country at *country*. Tariffs match origin country + product + effective date vs the shipment's arrival.
3. **Loss if it happens** (`exposure.py`, in code, never by the model): delay = holding cost per day + late-order loss on demand
   the inventory cannot cover; tariff = rate x shipment value; exchange rate = move x pending-order value.
4. **Confidence** (`confidence.py`): High / Medium / Low plus reasons, from six parts (source type, independent confirmation,
   forecast distance, text clarity, match precision, age). Parts that do not apply are left out.
5. **Risk score** = likelihood(band) x loss if it happens (0.70 / 0.40 / 0.15).
6. **Level** (`alerts.py`): Notify when expected loss >= the trader's own threshold (`trader_settings`, default $2,000) OR stock would
   run out (days of stock < delay + replacement lead time, any amount). Low confidence never notifies unless the possible loss
   is >= $250,000 (rare-event guard). Otherwise Watch (>= 25% of the threshold) or Log. No repeat notification unless the
   expected loss grew by 25%, the band rose, or the level rose. Every alert stores its explanation (e.g. "stock covers 21 days;
   delay 5 + lead time 7 = 12 -> no stockout risk").
7. **Heads-up vs happening now**: a signal that has not started yet is a heads-up with a lead time and an act-by date (the last day to
   order a replacement, or the day before a duty takes effect); one that has started is "now".

Run: `python -m src.risk.pipeline [business_id]` (writes the `alerts` table).

Known simplifications (honest): the delay length is a config default per event type (no source states it); stockout ignores other
incoming shipments; pending orders are assumed spread evenly until their last due date; route checkpoints share the journey time
equally; a tariff is priced ONLY with a duty rate the notice states (the reader's `rate_percent`); with no stated rate nothing is guessed: the alert is a Watch that says "check the rate manually" and can never Notify.
