"""Small Fivetran REST helper (uses FIVETRAN_API_KEY = base64 "key:secret" from .env; never prints it).

    python -m scripts.fivetran_api status          # every connection: state, last sync, schema
    python -m scripts.fivetran_api sync            # start a sync for every fivetran_raw_* connection
    python -m scripts.fivetran_api schedule        # apply the sync frequencies from docs/fivetran.md
"""

from __future__ import annotations

import sys

import requests
from dotenv import dotenv_values

API = "https://api.fivetran.com/v1"
FREQUENCY_MINUTES = {"gdelt": 30, "gdacs": 180, "portwatch": 1440, "federal_register": 360, "open_meteo": 360, "ecb": 1440}


def _headers() -> dict:
    key = dotenv_values().get("FIVETRAN_API_KEY")
    if not key:
        raise SystemExit("FIVETRAN_API_KEY missing in .env")
    return {"Authorization": f"Basic {key}", "Accept": "application/json", "Content-Type": "application/json"}


def connections() -> list[dict]:
    r = requests.get(f"{API}/connections", headers=_headers(), params={"limit": 100}, timeout=30)
    r.raise_for_status()
    return [c for c in r.json()["data"]["items"] if c["schema"].startswith("fivetran_raw_")]


def main(cmd: str) -> None:
    for c in sorted(connections(), key=lambda c: c["schema"]):
        source = c["schema"].removeprefix("fivetran_raw_")
        if cmd == "sync":
            r = requests.post(f"{API}/connections/{c['id']}/sync", headers=_headers(), json={"force": False}, timeout=30)
            print(f"{c['schema']:28} sync -> HTTP {r.status_code} {r.json().get('message', r.json().get('code', ''))[:80]}")
        elif cmd == "schedule":
            r = requests.patch(f"{API}/connections/{c['id']}", headers=_headers(), timeout=30,
                               json={"sync_frequency": FREQUENCY_MINUTES[source], "paused": False})
            print(f"{c['schema']:28} every {FREQUENCY_MINUTES[source]:>4} min -> HTTP {r.status_code}")
        else:
            st = c["status"]
            print(f"{c['schema']:28} id={c['id']:24} setup={st['setup_state']:11} sync={st['sync_state']:11} "
                  f"succeeded={c.get('succeeded_at')} failed={c.get('failed_at')} paused={c['paused']} freq={c['sync_frequency']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "status")
