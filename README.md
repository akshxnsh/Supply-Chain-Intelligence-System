Do not modify UI.

Regenerate the Dataverse binding for AssetsStockKharkhoda.

Remove the existing generated datasource metadata for AssetsStockKharkhoda and recreate it from the current Dataverse schema.

Do not modify components.
Do not modify hooks.
Do not modify UI.
Only refresh datasource metadata and generated service bindings.

Publish after regeneration.

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

apps/asset-dashboard/src/generated/services/assets-stock-kharkhoda-service.ts 2#QV:import type { AssetsStockKharkhoda } from '../models/assets-stock-kharkhoda-model'; 5#XS:const DATA_SOURCE_NAME = 'AssetsStockKharkhoda'; 7#VS:export class AssetsStockKharkhodaService { 8#BJ: static async create(record: Omit<AssetsStockKharkhoda, 'id'>): Promise<AssetsStockKharkhoda> { 11#PR: return result.data as AssetsStockKharkhoda; 16#TZ: changedFields: Partial<Omit<AssetsStockKharkhoda, 'id'>> 17#MN: ): Promise<AssetsStockKharkhoda> { 20#PR: return result.data as AssetsStockKharkhoda; 28#NW: static async get(id: string): Promise<AssetsStockKharkhoda> { 31#PR: return result.data as AssetsStockKharkhoda; 34#NH: static async getAll(options?: IOperationOptions): Promise<AssetsStockKharkhoda[]> { 37#TY: return result.data as AssetsStockKharkhoda[];

apps/asset-dashboard/src/generated/hooks/use-assets-stock-kharkhoda.ts 2#ZQ:import { AssetsStockKharkhodaService } from "../services/assets-stock-kharkhoda-service"; 3#JP:import type { AssetsStockKharkhoda } from "../models/assets-stock-kharkhoda-model"; 9#PW: * Retrieve all AssetsStockKharkhoda records with optional filtering and sorting. 14#JT:export function useAssetsStockKharkhodaList(options?: IOperationOptions) { 17#JK: queryFn: () => AssetsStockKharkhodaService.getAll(options), 22#MP: * Retrieve a single AssetsStockKharkhoda record by its unique identifier. 25#PW:export function useAssetsStockKharkhoda(id: string) { 28#JT: queryFn: () => AssetsStockKharkhodaService.get(id), 34#BJ: * Create a new AssetsStockKharkhoda record. 35#ZX: * @remarks Form validation: use CreateAssetsStockKharkhodaSchema with zodResolver for type-safe create forms 37#PK:export function useCreateAssetsStockKharkhoda() { 40#BX: mutationFn: (data: Omit<AssetsStockKharkhoda, "id">) => AssetsStockKharkhodaService.create(data), 48#RS: * Update an existing AssetsStockKharkhoda record. 49#ZX: * @remarks Form validation: use UpdateAssetsStockKharkhodaSchema.partial().omit({ id: true }) with zodResolver for edit forms (matches changedFields input) 51#YP:export function useUpdateAssetsStockKharkhoda() { 59#SZ: changedFields: Partial<Omit<AssetsStockKharkhoda, "id">>; 60#JZ: }) => AssetsStockKharkhodaService.update(id, changedFields), 69#RX: * Delete a AssetsStockKharkhoda record by its unique identifier. 71#NY:export function useDeleteAssetsStockKharkhoda() { 74#YB: mutationFn: (id: string) => AssetsStockKharkhodaService.delete(id), 83#HR:export const AssetsStockKharkhoda_DATA_SOURCE_TYPE = 'Dataverse' as const; 85#JW:export { AssetsStockKharkhodaSchema, CreateAssetsStockKharkhodaSchema, UpdateAssetsStockKharkhodaSchema } from "../validators/assets-stock-kharkhoda-validator"; 86#XM:export type { AssetsStockKharkhodaInput, CreateAssetsStockKharkhodaInput, UpdateAssetsStockKharkhodaInput } from "../validators/assets-stock-kharkhoda-validator";

apps/asset-dashboard/src/generated/models/assets-stock-kharkhoda-model.ts 1#VY:export interface AssetsStockKharkhoda { 3#HS: * @displayName AssetsStockKharkhoda 163#KH:export const _AssetsStockKharkhoda = 'AssetsStockKharkhoda' as const;

apps/asset-dashboard/src/generated/validators/assets-stock-kharkhoda-validator.ts 4#JW: * Zod schema for AssetsStockKharkhoda validation 6#YS:export const AssetsStockKharkhodaSchema = z.object({ 49#WX: * Schema for creating a new AssetsStockKharkhoda (omits system-generated ID) 51#HZ:export const CreateAssetsStockKharkhodaSchema = AssetsStockKharkhodaSchema.omit({ id: true }); 54#MZ: * Schema for updating an existing AssetsStockKharkhoda 56#MM:export const UpdateAssetsStockKharkhodaSchema = AssetsStockKharkhodaSchema; 58#BT:export type AssetsStockKharkhodaInput = z.infer<typeof AssetsStockKharkhodaSchema>; 59#TS:export type CreateAssetsStockKharkhodaInput = z.infer<typeof CreateAssetsStockKharkhodaSchema>; 60#NJ:export type UpdateAssetsStockKharkhodaInput = z.infer<typeof UpdateAssetsStockKharkhodaSchema>;

data-model/full-data-model.json 9#HS: "Label": "AssetsStockKharkhoda", 40#QM: "SchemaName": "cr9a7_AssetsStockKharkhoda", 309#XR: "SchemaName": "cr9a7_AssetsStockKharkhodaId", 325#HS: "Label": "AssetsStockKharkhoda",
