"""
Initialize Google Sheets source tabs for the demo ingestion pipeline.

Creates or reuses a spreadsheet named "Supply Chain Data", creates one tab per
mirrored table, and writes schema headers using the existing table definitions.
Optionally loads existing seed/demo rows with --seed.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

from src.ingestion.init_postgres import TABLE_IDS, load_bigquery_table_definitions
from src.ingestion.seed_postgres import WriteDisposition, load_seed_namespace

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SPREADSHEET_TITLE = "Supply Chain Data"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def credential_path() -> Path:
    raw_path = (
        os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        or os.getenv("GOOGLE_SHEETS_KEY_FILE")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    )
    if not raw_path:
        raise RuntimeError(
            "Google Sheets credentials are missing. Set GOOGLE_SHEETS_CREDENTIALS in .env."
        )

    path = Path(raw_path).expanduser()
    if not path.exists():
        raise RuntimeError(f"Google Sheets credentials file does not exist: {path}")

    return path


def google_services():
    credentials = service_account.Credentials.from_service_account_file(
        credential_path(),
        scopes=SCOPES,
    )
    sheets = build("sheets", "v4", credentials=credentials)
    drive = build("drive", "v3", credentials=credentials)
    return sheets, drive


def find_spreadsheet(drive) -> str | None:
    configured_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if configured_id:
        logger.info("Using spreadsheet from GOOGLE_SHEETS_SPREADSHEET_ID.")
        return configured_id

    query = (
        "mimeType='application/vnd.google-apps.spreadsheet' "
        f"and name='{SPREADSHEET_TITLE}' "
        "and trashed=false"
    )
    response = drive.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
        pageSize=10,
    ).execute()
    files = response.get("files", [])
    if not files:
        return None

    logger.info("Reusing existing spreadsheet: %s", files[0]["id"])
    return files[0]["id"]


def create_spreadsheet(sheets) -> str:
    spreadsheet = {
        "properties": {"title": SPREADSHEET_TITLE},
        "sheets": [{"properties": {"title": TABLE_IDS[0]}}],
    }
    response = sheets.spreadsheets().create(body=spreadsheet, fields="spreadsheetId").execute()
    spreadsheet_id = response["spreadsheetId"]
    logger.info("Created spreadsheet: %s", spreadsheet_id)
    return spreadsheet_id


def spreadsheet_metadata(sheets, spreadsheet_id: str) -> dict[str, Any]:
    return sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="spreadsheetId,spreadsheetUrl,sheets(properties(sheetId,title))",
    ).execute()


def ensure_tabs(sheets, spreadsheet_id: str) -> None:
    metadata = spreadsheet_metadata(sheets, spreadsheet_id)
    existing_titles = {
        sheet["properties"]["title"]
        for sheet in metadata.get("sheets", [])
    }

    requests = []
    for table_id in TABLE_IDS:
        if table_id not in existing_titles:
            requests.append({"addSheet": {"properties": {"title": table_id}}})

    if not requests:
        logger.info("All expected tabs already exist.")
        return

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    logger.info("Created %s missing tabs.", len(requests))


def table_headers() -> dict[str, list[str]]:
    tables = load_bigquery_table_definitions()
    return {
        table_id: [field.name for field in tables[table_id]["schema"]]
        for table_id in TABLE_IDS
    }


def write_headers(sheets, spreadsheet_id: str, headers_by_table: dict[str, list[str]]) -> None:
    data = [
        {
            "range": f"'{table_id}'!A1",
            "values": [headers],
        }
        for table_id, headers in headers_by_table.items()
    ]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "RAW",
            "data": data,
        },
    ).execute()
    logger.info("Header rows written for %s tabs.", len(data))


def normalize_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def collect_seed_rows() -> dict[str, list[dict[str, Any]]]:
    seed_rows = {table_id: [] for table_id in TABLE_IDS}

    def load_rows(
        table_id: str,
        rows: list[dict[str, Any]],
        write_disposition=WriteDisposition.WRITE_TRUNCATE,
    ):
        if table_id not in seed_rows:
            return

        if write_disposition == WriteDisposition.WRITE_TRUNCATE:
            seed_rows[table_id] = []

        seed_rows[table_id].extend(rows)

    seed = load_seed_namespace(load_rows)
    seed["seed_business_suppliers"]()
    seed["seed_pending_orders"]()
    seed["seed_shipment_timetable"]()
    seed["seed_alternative_suppliers"]()
    seed["seed_port_activity"]()
    seed["seed_disruption_events"]()
    seed["seed_weather_alerts"]()
    seed["seed_tariff_updates"]()
    seed["seed_inventory"]()
    seed["seed_completed_orders"]()
    seed["seed_supplier_reviews"]()
    return seed_rows


def write_seed_data(
    sheets,
    spreadsheet_id: str,
    headers_by_table: dict[str, list[str]],
) -> None:
    seed_rows = collect_seed_rows()

    clear_ranges = [f"'{table_id}'!A2:ZZ" for table_id in TABLE_IDS]
    sheets.spreadsheets().values().batchClear(
        spreadsheetId=spreadsheet_id,
        body={"ranges": clear_ranges},
    ).execute()

    data = []
    for table_id, rows in seed_rows.items():
        headers = headers_by_table[table_id]
        values = [
            [normalize_value(row.get(column)) for column in headers]
            for row in rows
        ]
        if values:
            data.append({"range": f"'{table_id}'!A2", "values": values})
        logger.info("%s: prepared %s seed rows", table_id, len(values))

    if data:
        sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": data,
            },
        ).execute()
    logger.info("Seed/demo data written to Google Sheets.")


def init_google_sheets(seed: bool = False) -> str:
    logger.info("Initializing Google Sheets source workbook.")
    try:
        sheets, drive = google_services()
        spreadsheet_id = find_spreadsheet(drive) or create_spreadsheet(sheets)

        ensure_tabs(sheets, spreadsheet_id)
        headers_by_table = table_headers()
        write_headers(sheets, spreadsheet_id, headers_by_table)

        if seed:
            write_seed_data(sheets, spreadsheet_id, headers_by_table)
        else:
            logger.info("Skipping seed/demo data. Pass --seed to populate rows.")

        metadata = spreadsheet_metadata(sheets, spreadsheet_id)
        spreadsheet_url = metadata["spreadsheetUrl"]
        logger.info("Google Sheets initialization complete.")
        print(spreadsheet_url)
        return spreadsheet_url
    except Exception:
        logger.exception("Google Sheets initialization failed.")
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize Google Sheets source workbook.")
    parser.add_argument("--seed", action="store_true", help="Populate tabs with existing seed/demo data.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    init_google_sheets(seed=args.seed)
