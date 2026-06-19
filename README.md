Do not modify code.

Search all generated files for the string:

AssetsStockKharkhoda

Print every file path containing this string and the exact matching lines.

Do not summarize.
Do not infer.
Print only matches.

Do not modify code.

Inspect the generated datasource metadata.

Print exactly:

DATASOURCE_NAME=
ENTITY_SET=
ENTITY_LOGICAL_NAME=
IS_BOUND=
CONNECTION_REFERENCE=

for AssetsStockKharkhoda.

If unavailable print NOT_PRESENT.

Do not infer.
Do not summarize.
Print only values found in generated metadata.

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

Inspected the current / route code and its Dataverse fetch path without modifying anything. The app is not logging raw responses, so several items you asked for are not observable from the current code alone.

Total Assets request HTTP status code: Not directly observable from existing logs. The only exception text the code can surface is Dataverse request failed with status ${response.status}., but the actual numeric status is not captured anywhere in the repo.
Category cards request HTTP status code: Not directly observable from existing logs. This request uses the same fetch helper and also only throws Dataverse request failed with status ${response.status}. without persisting the actual status anywhere visible.
Full Dataverse error message: Not observable from the current implementation. fetchDataverseJson() throws before reading the response body, so any Dataverse/OData payload like error.message is discarded.
Exact URL/query being executed:
Base URL comes from browser origin: window.location.origin + "/api/data/v9.2" in apps/asset-dashboard/src/lib/asset-data.ts:91-100
Configured Dataverse environment URL is https://org170ad377.crm8.dynamics.com in apps/asset-dashboard/power.config.json:12
Current code actually calls the singular logical name path, not the configured entity set name:
Count request: /api/data/v9.2/cr9a7_assetsstockkharkhoda?$filter=(cr9a7_assetstore eq 'Kharkhoda Store' or cr9a7_assetstore eq 'Kharkhoda New Asset Store')&$count=true&$top=1&$select=cr9a7_assetcode
Category cards/list request first page: /api/data/v9.2/cr9a7_assetsstockkharkhoda?$select=cr9a7_assetsstockkharkhodaid,cr9a7_assetstore,cr9a7_categoryname,cr9a7_assetusage,cr9a7_assetcode,cr9a7_assetcomments,cr9a7_assetcost,cr9a7_assetfloor,cr9a7_assetid,cr9a7_assetremarks,cr9a7_commissioningdate,cr9a7_companyname,cr9a7_cpudetails,cr9a7_dept,cr9a7_designation,cr9a7_empid,cr9a7_financecontrolnumber,cr9a7_floorlocation,cr9a7_harddisksizegb,cr9a7_hostname,cr9a7_imeino,cr9a7_invoicenumber,cr9a7_locationcode,cr9a7_manufacturer,cr9a7_materialreceiveddate,cr9a7_mobiledevicestype,cr9a7_modelnumber,cr9a7_name,cr9a7_ponumber,cr9a7_procurementringino,cr9a7_procurementringitype,cr9a7_ramsizegb,cr9a7_remark,cr9a7_serialnumber,cr9a7_storelocation,cr9a7_username,cr9a7_vendorname,cr9a7_warrantyend,cr9a7_warrantystart&$filter=(cr9a7_assetstore eq 'Kharkhoda Store' or cr9a7_assetstore eq 'Kharkhoda New Asset Store')&$orderby=cr9a7_categoryname asc,cr9a7_assetcode asc
Important mismatch found: power.config.json says the entity set name is cr9a7_assetsstockkharkhodas, but the runtime code calls cr9a7_assetsstockkharkhoda.
Whether the $count=true request succeeds when executed directly: Not observable from current code or stored logs. No raw direct execution result is captured.
Whether following @odata.nextLink succeeds: Not observable from current logs. The code follows response['@odata.nextLink'] ?? '', but does not log each page URL, page status, or any nextLink failure body.
Whether the authenticated user has permission to read cr9a7_assetsstockkharkhoda: Not determinable from the current codebase alone. There is no permission probe, no logged 401/403 payload, and no security/privilege response captured.
Exact exception being caught that results in Unable to load the total asset count: The UI shows that message when totalAssetsQuery.isError is true in apps/asset-dashboard/src/pages/index.tsx:124-128. The underlying thrown error can be one of:
Dataverse request failed with status ${response.status}.
Dataverse did not return a server-side count.
Unable to build Kharkhoda diagnostics.
Or any upstream fetch/runtime error thrown while fetchKharkhodaDiagnostics() / fetchAllKharkhodaRows() runs.
Exact exception being caught that results in Unable to load category cards from Dataverse: The UI shows that message when categoryCardsQuery.isError is true in apps/asset-dashboard/src/pages/index.tsx:173-176. The underlying thrown error can be:
Dataverse request failed with status ${response.status}.
Unable to build Kharkhoda diagnostics.
Or any upstream fetch/runtime error from fetchAllKharkhodaRows().
Raw error response: Not available in the current implementation because the code never reads await response.text() or await response.json() on non-OK responses; it discards the body and throws a synthesized Error.
The most concrete inspection finding is that the app is requesting /api/data/v9.2/cr9a7_assetsstockkharkhoda... while the configured Dataverse entity set name is cr9a7_assetsstockkharkhodas; however, I did not change code per your instruction.

Do not modify any query.

Inside the Total Assets request error path only:

Replace the contents of the Total Assets card with exactly one of these values:

"NO_RESPONSE_OBJECT"
if the fetch throws before a Response exists.

Otherwise display:

STATUS=<response.status>

Do not read response.text().
Do not modify category cards.
Do not modify queries.
Do not add fallback text.
Do not change any other logic.

Do not modify any query.

In the Total Assets card component only, replace the entire displayed value with the fixed string:

HELLO_FROM_TOTAL_ASSETS_COMPONENT

Do not use any condition.
Do not use query state.
Do not use response.status.
Do not modify category cards.
Do not modify fetch logic.
Do not modify Dataverse requests.
Only replace the displayed value inside the Total Assets card.



Do not modify any query.

Inside the Total Assets component only:

Display exactly one of the following strings:

QUERY_LOADING
if totalAssetsQuery.isLoading is true

QUERY_ERROR
if totalAssetsQuery.isError is true

QUERY_SUCCESS
if totalAssetsQuery.isSuccess is true

Do not display any count.
Do not display response text.
Do not modify category cards.
Do not modify fetch logic.
Do not modify Dataverse requests.
Only replace the Total Assets displayed value.


Do not modify any query.

Inside the Total Assets component only:

If totalAssetsQuery.isError is true:

Display exactly:

ERROR_CLASS=<totalAssetsQuery.error?.constructor?.name>

If the value is undefined display:

ERROR_CLASS=UNDEFINED

Do not modify queries.
Do not modify fetch logic.
Do not modify category cards.
Do not modify Dataverse requests.
Do not change anything else.

Do not modify any query.

Inside the Total Assets component only:

If totalAssetsQuery.isError is true:

Display exactly:

ERROR_MESSAGE=<String(totalAssetsQuery.error)>

Do not display anything else.
Do not modify queries.
Do not modify fetch logic.
Do not modify category cards.
Do not modify Dataverse requests.
Do not change anything else.


Do not modify any code.

For the Total Assets request only:

Display exactly:

REQUEST_URL=<the exact URL string passed to fetch()>

Do not execute another request.
Do not summarize.
Do not reconstruct.
Display the exact string argument supplied to fetch().
Do not modify queries.
Do not modify category cards.
Do not modify anything else.


Do not modify any code.

Inspect the generated schema and power.config.json.

Print exactly:

ENTITY_SET_NAME=<value>

This must be the exact entity set name exposed by Dataverse Web API for the AssetsStockKharkhoda table.

Do not infer.
Do not guess.
Do not use the display name.
Read only from generated schema/metadata files.
Print only the value.



Do not modify code.

Verify whether GET

https://org170ad377.crm8.dynamics.com/api/data/v9.2/cr9a7_assetsstockkharkhodas?$top=1

exists in the current authenticated session.

Answer only:

EXISTS
or
NOT_FOUND
or
UNAUTHORIZED



Do not modify any code.

Read the generated file that contains the service definition for AssetsStockKharkhoda.

Print exactly:

ENTITY_SET_SOURCE_FILE=<relative path>

ENTITY_SET_DECLARATION=<exact line>

Do not infer.
Do not guess.
Do not execute requests.
Do not summarize.
Print only the file path and the exact declaration line.