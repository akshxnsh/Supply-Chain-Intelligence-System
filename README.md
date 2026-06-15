# Supply Chain Disruption Intelligence Agent

## Overview

This project implements a Supply Chain Disruption Intelligence Agent that monitors events that can affect a business's suppliers and inbound shipments, estimates customer fulfillment impact, and recommends mitigation actions.

The agent ingests:

- Disruption events: news, geopolitical incidents, infrastructure failures
- Weather alerts: hurricanes, storms, extreme conditions
- Port activity: strikes, congestion, vessel delays
- Tariff updates: duties that affect inbound supply cost
- Business data: suppliers, inbound shipments, pending client orders, inventory, and supplier history

By cross-referencing signals with supplier relationships, `shipment_timetable`, `pending_orders`, and `inventory`, the system identifies affected suppliers, estimates whether inventory can cover pending client demand, suggests alternative suppliers, drafts an owner email, and can generate a purchase order for the top alternative.

## Repository Structure

```text
src/
├─ actions/                 # Helper actions, such as PO generation
├─ agent/                   # Google ADK multi-agent orchestration
├─ dashboard/               # FastAPI backend and React/Vite dashboard
├─ detection/               # Multi-signal disruption detection
├─ exposure/                # Business impact and inventory coverage calculation
├─ ingestion/               # BigQuery client, schema init, seed, verification
├─ prediction/              # Shipment-location prediction and port matching
└─ suppliers/               # Supplier scoring and ranking
```

Configuration files live under `config/`.

## Key Components

### Detection

`src/detection/disruption_detector.py` reads recent disruption events, weather alerts, port activity, tariffs, business suppliers, and active inbound shipments. It uses seeded shipment `route`, `etd`, `eta`, and `journey_time_hours` fields to estimate the current route checkpoint and suppress alerts for checkpoints already passed. It returns affected suppliers with signal details and tariff cost impact calculated against inbound shipment value.

### Exposure

`src/exposure/calculator.py` calculates impact from three data sources:

- `shipment_timetable`: supplier-side inbound shipments at risk
- `pending_orders`: demand-side client/customer orders the business must fulfill
- `inventory`: on-hand inventory coverage by product category

If inventory covers pending client demand for affected categories, expected loss and severity are reduced. If inventory is insufficient, uncovered demand increases expected loss.

### Supplier Scoring

`src/suppliers/scorer.py` ranks alternative suppliers using cost, lead time, static reliability, completed-order history, and supplier reviews.

### Google ADK Agents

The application uses a native Google ADK multi-agent system:

- `SupplyChainIntelligenceAgent`: root coordinator
- `DisruptionDetectionAgent`: disruption, weather, port, tariff, and anomaly analysis
- `SupplierRiskAgent`: exposure, inventory coverage, and supplier alternatives
- `ProcurementAgent`: purchase order and owner communication drafting
- `CalibrationAgent`: historical calibration lookup

## BigQuery Tables

Schemas are defined in `src/ingestion/init_tables.py`. The key demand/supply split is:

- `pending_orders`: client/customer orders placed with the business
- `shipment_timetable`: inbound supplier shipments headed to the business
- `inventory`: current inventory buffer used to reduce impact when it covers demand

Run:

```bash
python -m src.ingestion.init_tables
python -m src.ingestion.seed_data
python -m src.ingestion.verify_tables
```

See `BIGQUERY_TABLES_GUIDE.md` for the full table map.

## Setup

### Prerequisites

- Python 3.10+
- Node.js for the dashboard UI
- Google Cloud project with BigQuery access
- Gemini / Google API credentials
- Optional Arize Phoenix credentials for tracing

### Install

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Frontend:

```bash
cd src/dashboard/frontend
npm install
```

## Runtime

Run one agent cycle:

```bash
python run.py once
```

Run the API:

```bash
python -m src.dashboard.api
```

Run the dashboard frontend:

```bash
cd src/dashboard/frontend
npm run dev
```

## Configuration

The app maps `GEMINI_API_KEY` to ADK's `GOOGLE_API_KEY` automatically.

For persistent ADK sessions:

```bash
ADK_SESSION_DB_URL=sqlite+aiosqlite:///./supply_chain_sessions.db
```

For BigQuery credentials, set `GOOGLE_APPLICATION_CREDENTIALS` to a local service-account JSON file or place a valid local key at `gcp-key.json`. Do not commit service-account private keys, and rotate any key pasted into chat or shared outside a secret manager.

## Fivetran MCP

Configure Streamable HTTP:

```bash
FIVETRAN_MCP_URL=https://your-fivetran-mcp-endpoint
FIVETRAN_MCP_TOKEN=your-token
```

Or stdio:

```bash
FIVETRAN_MCP_COMMAND="your-fivetran-mcp-command --flag"
```

The root agent allows these Fivetran tools:

- `check_connector_status`
- `get_last_sync_time`
- `list_connectors`
- `trigger_sync`
- `monitor_sync`

## Phoenix Tracing

Supported variables:

```bash
PHOENIX_API_KEY=...
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/s/your-space
PHOENIX_PROJECT_NAME=supply-chain-agent
```

## Tests

```bash
python -m pytest -q
```

## Extending

- Add new signal sources in `src/ingestion/bq_client.py` and `src/detection/disruption_detector.py`.
- Adjust supplier scoring in `src/suppliers/scorer.py`.
- Replace the owner email template with Slack, Teams, or SMS integrations.

## License

This project is licensed under the MIT License. See `LICENSE` for details.


The current implementation is failing after the pagination fix.

Do not use custom pagination logic, rows.length from fetched records, client-side aggregation, local collections, OData aggregate queries, or complex Dataverse count/groupby queries.

Start over from the connected Dataverse table and rebuild the data layer using standard Dataverse-supported queries.

Requirements:

- Filter records where Asset Store is either "Kharkhoda Store" or "Kharkhoda New Asset Store".
- Treat both store values as a single logical store named "Kharkhoda".
- Calculate Total Assets from all matching records, not a paginated subset.
- Dynamically generate category cards from unique Category Name values within the filtered Kharkhoda dataset.
- Each category card must show the count of records where Asset Usage = "In Stock(STK)".
- Clicking a category card should show a dynamic breakdown of all Asset Usage values and their counts for that category.
- Asset Usage values must be read dynamically from data and not hardcoded.
- Add Asset Code search and asset details page.
- Use only Dataverse-supported, delegation-safe operations.
- Verify the exact Dataverse table logical name and column logical names before generating queries.
- Fix all current loading errors and ensure the dashboard loads successfully.

Before making changes, tell me:

1. The Dataverse table logical name.
2. The logical names of Asset Store, Category Name, Asset Usage, and Asset Code.
3. The current error causing "Unable to load the total asset count" and "Unable to load category cards from Dataverse".


The schema issue is fixed, but Total Assets is still exactly 500.

This indicates the dashboard is still counting only the first Dataverse page rather than all matching Kharkhoda records.

Verify the following:

1. What is the actual number of records in Dataverse where:
   cr9a7_assetstore = "Kharkhoda Store"
   OR
   cr9a7_assetstore = "Kharkhoda New Asset Store"

2. Show the exact query used to calculate Total Assets.

3. Is Total Assets being calculated using:
   
   - rows.length
   - fetchedRecords.length
   - a local array length
   - only the first API page

4. How many records are returned in the first Dataverse page?

5. How many total pages are available?

6. Is the query following @odata.nextLink until all pages are processed?

7. If not, implement full pagination or use a Dataverse server-side count query.

Report:

- Actual Kharkhoda record count
- First page record count
- Number of pages
- Final Total Assets returned by the corrected query