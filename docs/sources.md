# Data sources (checked against the live APIs on 2026-11-10)

All six are free and need no key. Code: `src/fetchers/<source>.py`. Each has a plain `fetch_*` function (timeouts,
retries with backoff in `src/fetchers/http.py`) and a pure `parse_*` function tested on a saved real response in
`tests/fixtures/` (`python -m scripts.capture_fixtures` refreshes them).

| Source | What it gives | Endpoint | Observed limits / terms |
|---|---|---|---|
| GDELT DOC 2.0 | news articles (title, url, domain, country) matching our 3 searches | `api.gdeltproject.org/api/v2/doc/doc` | 1 request / 5 s or HTTP 429; slow (TLS handshake > 5 s, ~15-20 s per call) so it has 30/90 s timeouts; max 250 articles per call; **no article text** |
| GDACS | disasters (cyclone, flood, quake, volcano) with alert level, dates, severity | `gdacs.org/gdacsapi/api/events/geteventlist/SEARCH` | none seen; GeoJSON |
| IMF PortWatch | port list (2,065 ports with lat/lon), 28 chokepoints, disruption events | ArcGIS `services9.arcgis.com/.../PortWatch_*_database` | **Daily traffic layers now need an ArcGIS token** (see below). The open disruptions layer last changed 2026-08-15 (132 rows) |
| Federal Register | US trade rules, proposed rules, notices (future effective / comment dates) | `federalregister.gov/api/v1/documents.json` | none seen; filtered to 4 trade agencies + "tariff OR duties OR duty" |
| Open-Meteo | daily weather + marine forecast per location | `api.open-meteo.com`, `marine-api.open-meteo.com` | **Non-commercial use only**, CC BY 4.0 (show `open_meteo.ATTRIBUTION`), ~10,000 calls/day; one forecast, no uncertainty range; ports inside a harbour have no wave data |
| ECB reference rates | daily EUR cross rates (USD, CNY, KRW, INR, ...) | `data-api.ecb.europa.eu/service/data/EXR/...` | none seen; ~30 currencies only; business days only |

## PortWatch daily traffic (token-gated)
`Daily_Ports_Data` and `Daily_Chokepoints_Data` answer `Token Required`. The only public daily layer
(`Daily_Trade_Data_TEST4`) holds 2,314 rows and stops in May 2025, so it is not used. `fetch_daily_ports` /
`fetch_daily_chokepoints` read `PORTWATCH_ARCGIS_TOKEN` from `.env`, raise `PortWatchTokenRequired` without it, and
have only been tested on a sample shaped like the public TEST layer (the real token-gated schema is unverified).
Until a token (or a downloaded CSV) exists, the "port / chokepoint traffic trend" signal is **off**, and the
resume must not claim it.
