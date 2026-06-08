# Supply Chain Disruption Intelligence Agent

## Overview
This project implements a **Supply‑Chain Disruption Intelligence Agent** that continuously monitors a variety of signals that can affect a business’s supply chain and automatically generates alerts, response plans, and procurement actions.

The agent ingests data from several sources:

* **Disruption events** – news, geopolitical incidents, infrastructure failures.
* **Weather alerts** – hurricanes, storms, extreme conditions.
* **Port activity** – strikes, congestion, vessel delays.
* **Tariff updates** – new duties that impact product cost.

By cross‑referencing these signals with a business’s supplier list and active shipments, the system identifies which suppliers are at risk, suggests alternative suppliers, drafts an email summary for the business owner, and can even generate a purchase order for the most reliable alternative.

The solution is built as a modular Python code‑base with a lightweight React dashboard for visualising alerts.

---

## Repository Structure

```
src/
├─ actions/                 # Helper actions (e.g., PO generation)
├─ agent/                   # Core agent orchestration
│   ├─ main.py              # Entry point – validates env vars, sets up tracing
│   ├─ loop.py              # Periodic execution loop
│   └─ tools.py             # Utility functions used by the agent
├─ dashboard/               # Simple React UI for monitoring alerts
│   └─ frontend/            # Vite‑based frontend source
├─ detection/               # Multi‑signal disruption detection logic
│   └─ disruption_detector.py
├─ exposure/                # Calculates financial exposure per supplier
│   └─ calculator.py
├─ ingestion/               # BigQuery client and data‑seeding utilities
│   ├─ bq_client.py
│   ├─ init_tables.py
│   └─ seed_data.py
├─ prediction/              # Shipment‑location prediction & matching helpers
│   └─ utils.py
└─ suppliers/               # Supplier scoring and ranking logic
    └─ scorer.py
```

Configuration files live under `config/` (environment settings, supplier seed data, etc.).

---

## Key Components

### 1. Detection (`src/detection/disruption_detector.py`)
* Pulls recent events, weather alerts, port status, and tariff updates via the BigQuery client.
* Builds lookup maps for fast matching against business suppliers.
* Cross‑references active shipments (via `src/prediction/utils.py`) to determine which suppliers are affected by:
  * Weather alerts at the predicted port
  * Port strikes or congestion
  * News mentioning the port or supplier location
  * New tariffs that increase product cost
* Returns a structured list of affected suppliers with signal details and estimated cost impact.

### 2. Exposure Calculator (`src/exposure/calculator.py`)
Aggregates the financial impact of all detected signals for each supplier, providing a risk score used for ranking alternatives.

### 3. Supplier Scorer (`src/suppliers/scorer.py`)
Ranks suppliers based on reliability, historical performance, cost, and current exposure. The top‑ranked alternative is used for PO generation.

### 4. Google ADK Agent System (`src/agent`)
The application is a native Google ADK multi-agent system:

* `SupplyChainIntelligenceAgent` is the root coordinator.
* `DisruptionDetectionAgent` analyzes disruption, weather, port, and tariff signals.
* `SupplierRiskAgent` calculates exposure and ranks alternatives.
* `ProcurementAgent` drafts purchase orders and owner communications.
* `CalibrationAgent` applies historical calibration.
* ADK `Runner`, sessions, task-mode delegation, function tools, callbacks, and
  MCP toolsets replace the former custom Gemini loop.

### 5. Dashboard (`src/dashboard/frontend`)
A minimal React/Vite UI that displays current alerts, affected suppliers, and suggested actions.

---

## Setup & Installation

### Prerequisites
* Python 3.10+
* Node.js (for the dashboard UI)
* A Google Cloud project with BigQuery access
* API keys for **Gemini** and **Arize Phoenix** (observability)

### Steps
1. **Clone the repository**
   ```bash
   git clone https://github.com/akshxnsh/Supply-Chain-Intelligence-System.git
   cd Supply-Chain-Intelligence-System
   ```
2. **Create a virtual environment and install Python dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Install frontend dependencies**
   ```bash
   cd src/dashboard/frontend
   npm install   # or yarn/pnpm
   ```
4. **Configure environment variables** – copy the example and fill in your keys:
   ```bash
   cp .env.example .env
   # edit .env with GEMINI_API_KEY, PHOENIX_API_KEY, etc.
   ```
5. **Run the dashboard** (optional, for visual monitoring)
   ```bash
   npm run dev   # starts Vite dev server at http://localhost:5173
   ```
6. **Start the ADK agent**
   ```bash
   python run.py once
   ```

The application maps the existing `GEMINI_API_KEY` to ADK's
`GOOGLE_API_KEY` automatically.

## ADK Runtime Configuration

The default session service is ADK's `InMemorySessionService`, which preserves
the original process-local behavior. To use persistent ADK sessions, configure:

```bash
ADK_SESSION_DB_URL=sqlite+aiosqlite:///./supply_chain_sessions.db
```

The root agent is available in `src/agent/agent.py` for ADK discovery:

```bash
adk web
```

Historical recommendation calibration remains in BigQuery because it is
durable business/evaluation data rather than conversational memory. No custom
conversation history is maintained by application code.

## Fivetran MCP

Fivetran is exposed to the root agent as a native ADK `McpToolset`. Configure
either Streamable HTTP:

```bash
FIVETRAN_MCP_URL=https://your-fivetran-mcp-endpoint
FIVETRAN_MCP_TOKEN=your-token
```

or a stdio server:

```bash
FIVETRAN_MCP_COMMAND="your-fivetran-mcp-command --flag"
```

The toolset admits only:

* `check_connector_status`
* `get_last_sync_time`
* `list_connectors`
* `trigger_sync`
* `monitor_sync`

When Fivetran MCP is not configured, the rest of the ADK application runs
normally without placeholder sync behavior.

## Phoenix Tracing

Phoenix registration is retained through `phoenix.otel`. The
`openinference-instrumentation-google-adk` instrumentor captures ADK agent,
model, and tool execution, while explicit cycle spans retain the existing
business and session attributes.

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

---

## Usage

The core workflow is:
1. **Ingestion** – `src/ingestion/bq_client.py` provides helper functions to query recent events, weather alerts, port status, tariff updates, and pending orders.
2. **Detection** – `detect_disruptions` aggregates signals and matches them to suppliers.
3. **Scoring** – `src/suppliers/scorer.py` ranks suppliers based on the aggregated exposure.
4. **Alerting** – The agent creates a JSON alert, drafts an email (via a simple template), and can generate a PO for the top alternative.
5. **Dashboard** – Real‑time view of alerts and supplier scores.

You can customize the detection horizon (e.g., `hours=24` for events) by editing the constants in `disruption_detector.py`.

---

## Extending the Project

* **Add new signal sources** – Implement additional query functions in `src/ingestion/bq_client.py` and extend the lookup maps in `disruption_detector.py`.
* **Custom scoring** – Modify `src/suppliers/scorer.py` to incorporate new business‑specific metrics.
* **Different output channels** – Replace the email template with Slack, Teams, or SMS notifications.

---

## License
This project is licensed under the **MIT License** – see the `LICENSE` file for details.

---

## Acknowledgements
* **Gemini** – Large language model used for generating natural‑language summaries.
* **Arize Phoenix** – Observability platform for tracing model calls.
* **Google Cloud BigQuery** – Data warehouse for signal ingestion.

---


