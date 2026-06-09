# BigQuery Tables Setup Guide

This document describes the BigQuery tables used by the Supply Chain Intelligence System and how they are wired into the codebase.

## Table Overview

The system currently defines 14 BigQuery tables in `src/ingestion/init_tables.py`:

| # | Table | Source | Purpose |
|---|-------|--------|---------|
| 1 | `disruption_events` | Fivetran NewsAPI | External disruption events and news signals |
| 2 | `weather_alerts` | Fivetran OpenWeatherMap / seed data | Regional weather warnings affecting ports |
| 3 | `alternative_suppliers` | Manual/CSV seed data | Candidate suppliers for mitigation |
| 4 | `business_suppliers` | ERP / QuickBooks / seed data | Active supplier relationships for each business |
| 5 | `pending_orders` | Shopify / CRM / seed data | Client/customer orders placed with the business |
| 6 | `shipment_timetable` | ERP / freight tracker / seed data | Inbound supplier shipments for the business |
| 7 | `port_activity` | Port data feed / seed data | Port congestion, strike, and delay signals |
| 8 | `tariff_updates` | Trade feed / seed data | Tariff changes by country and product category |
| 9 | `inventory` | ERP / WMS / seed data | On-hand inventory value by product category |
| 10 | `agent_alerts` | Agent writes | Persisted disruption alerts |
| 11 | `agent_calibration` | Agent + historical seed data | Recommendation outcome calibration |
| 12 | `phoenix_traces` | Arize Phoenix OTEL | Observability traces and spans |
| 13 | `completed_orders` | Order history | Supplier reliability scoring input |
| 14 | `supplier_reviews` | Owner/ERP reviews | Supplier reliability scoring input |

## Demand vs Supply Tables

`pending_orders` is demand-side data. It stores orders placed by the business owner's clients/customers and is used to estimate what the business must fulfill during a disruption.

`shipment_timetable` is supply-side data. It stores inbound shipments from suppliers and is used to determine which supplier shipments are at risk when a supplier, port, country, weather region, or tariff changes.

Impact calculation combines:

- affected inbound shipment value from `shipment_timetable`
- pending client demand from `pending_orders`
- on-hand coverage from `inventory`

If inventory covers pending client demand for the affected product categories, expected loss and severity are reduced. If inventory is insufficient, uncovered client demand drives higher expected loss.

## Setup

Create or verify all schemas:

```bash
python -m src.ingestion.init_tables
```

Seed demo data:

```bash
python -m src.ingestion.seed_data
```

Verify table existence and wiring:

```bash
python -m src.ingestion.verify_tables
```

## Key Schemas

### `pending_orders`

Client/customer orders placed with the business.

```text
id STRING
business_id STRING
client_id STRING
product_category STRING
quantity INTEGER
order_value_usd FLOAT
required_by_date DATE
status STRING
```

Read by:

- `src.ingestion.bq_client.query_pending_orders`
- `src.agent.tools.get_pending_orders`
- `src.exposure.calculator.calculate_impact`

### `shipment_timetable`

Inbound supplier shipments headed to the business.

```text
id STRING
business_id STRING
supplier_id STRING
product_category STRING
quantity INTEGER
shipment_value_usd FLOAT
origin_port STRING
destination_port STRING
dispatched_date DATE
expected_arrival_date DATE
status STRING
```

Read by:

- `src.ingestion.bq_client.query_supplier_timetable`
- `src.ingestion.bq_client.query_shipments_at_risk`
- `src.prediction.utils.fetch_shipment_schedule`
- `src.detection.disruption_detector.detect_disruptions`
- `src.exposure.calculator.calculate_impact`

### `inventory`

On-hand inventory buffer by product category.

```text
id STRING
business_id STRING
product_category STRING
inventory_value_usd FLOAT
updated_at TIMESTAMP
```

Read by:

- `src.ingestion.bq_client.query_inventory`
- `src.agent.tools.get_inventory`
- `src.exposure.calculator.calculate_impact`

## Data Flow

```text
Disruption/weather/port/tariff signals
        |
        v
detect_disruptions()
        |
        v
affected supplier IDs
        |
        v
shipment_timetable -> inbound supply at risk
pending_orders      -> client demand to fulfill
inventory           -> coverage buffer
        |
        v
calculate_impact()
        |
        v
agent alert, owner email, and mitigation recommendation
```

## Credential Note

Use `GOOGLE_APPLICATION_CREDENTIALS` or `gcp-key.json` for a valid local service-account key. Do not commit service-account private keys to the repo, and rotate any key that has been pasted into chat or shared outside a secret manager.

## Troubleshooting

If a table is missing:

```bash
python -m src.ingestion.init_tables
```

If demo data is missing:

```bash
python -m src.ingestion.seed_data
```

If wiring is unclear:

```bash
python -m src.ingestion.verify_tables
```
