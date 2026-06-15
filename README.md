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


Build an asset dashboard app named “Asset Dashboard” with the exact structure, behavior. The app is a single productivity dashboard focused on Kharkhoda plant stock monitoring from an uploaded spreadsheet. It must feel like a clean internal operations tool, not a marketing site.

Core app purpose:

Monitor category-wise stock for the Kharkhoda plant from the data source created 
Show category cards based only on Kharkhoda rows.
Let the user search by asset code and open a dedicated asset detail page.

Required routes:

/ → main dashboard
/asset/:assetCode → asset detail page
/category/:categoryName → category detail page
* → not found page

Design direction:

Refined internal dashboard.
Light mode default with warm neutral surfaces and green/amber emphasis.
Theme must use customized CSS variables, not default gray shadcn values.
Primary color: muted emerald/green.
Accent color: warm amber/gold.
Soft warm background and sidebar token family, even if no sidebar is visible.
Rounded corners are prominent: many containers use rounded-2xl or rounded-3xl.
Cards have borders and light shadows.
Typography is functional, medium-density, sans-serif, no oversized hero text.
No footer, no login button, no profile menu.
No decorative gradients or marketing sections.

Exact theme feel:

Light background: warm off-white.
Foreground: dark olive/neutral text.
Card/popover: slightly brighter than background.
Primary: green used for icon chips, rings, charts.
Accent: amber used for highlighted information boxes.
Secondary/muted: warm beige panels.
Dark mode tokens should also be defined consistently even if not emphasized in preview.

Dashboard page / layout:

Main container is a vertical stack with 3 major sections:
Hero/control section
Summary cards row
Two-column section with asset search and category stock cards

Hero/control section:

A large rounded card with border and shadow.
On large screens, 2-column layout around 1.6fr 1fr.
Left side:
Small rounded Badge with text: Live spreadsheet dashboard
Hidden file input accepting .xlsx,.csv
Outline button, small size, with upload icon or spinning loader icon:
text when idle: Upload workbook
text while importing: Refreshing data
Heading: Kharkhoda plant stock dashboard
Supporting paragraph:
“Monitor category-wise stock from the latest uploaded asset sheet and jump directly to a dedicated asset record screen using the asset code search.”
Secondary info panel with rounded corners and bg-secondary text-secondary-foreground:
Explain that counts are filtered to Kharkhoda plant rows only, using Asset Store values Kharkhoda Store and Kharkhoda New Asset Store.
Explain that the main number on each category card represents only assets marked In Stock (STK).
If a file has been imported in the current session, show:
Latest imported workbook: {fileName}
Right side:
Small card-like operator context panel with border, bg-background, shadow.
Header row with user icon and label Operator context
Show current user full name
Show current user principal name/email
Show helper sentence:
“Dashboard values refresh whenever the uploaded Excel-backed dataset is replaced.”
Summary cards section:

3 cards in a responsive grid (md:grid-cols-3).
Each card shows:
CardDescription label
Colored square icon chip using bg-primary text-primary-foreground
Large numeric value
Small muted description text
The 3 cards are:
Kharkhoda in stock
value = total of all category inStockCount
description = only Kharkhoda rows with asset usage In Stock (STK)
icon = warehouse
Tracked categories
value = distinct filtered categories count
description = distinct asset categories visible after Kharkhoda plant filtering
icon = boxes
Kharkhoda rows
value = total filtered rows including non-STK usage values
description = all Kharkhoda plant rows, including non-STK usage values
icon = package search
Dashboard lower two-column section:

Two cards in grid lg:grid-cols-[1.1fr_1.4fr]
Left card: Asset code search

Title: Asset code search
Description: Enter an asset code to open the full record on a separate detail page.
Search input with search icon inside left.
Placeholder: Enter asset code
Button text: Open asset
Pressing Enter or clicking button navigates to /asset/{normalizedCode}
Normalization should trim and standardize asset code before navigation.
Bottom highlighted accent panel with bg-accent text-accent-foreground
Heading: Readable full-record layout
Body: asset details open in their own screen so long finance, warranty, location, and user fields stay easy to scan.
Right card: Category stock in Kharkhoda plant

Title: Category stock in Kharkhoda plant
Description explains:
cards show only In Stock (STK) counts
clicking a card reveals other usage-value counts
Loading state:
grid of 6 skeleton blocks, h-24 rounded-2xl, aria-hidden="true"
Empty state:
Empty compound component
icon media with warehouse icon
title: No Kharkhoda stock found
description instructing the user to upload or replace spreadsheet with Asset Store values matching Kharkhoda Store or Kharkhoda New Asset Store
extra small text saying the base dashboard only shows Kharkhoda category stock cards and asset-code search
Non-empty state:
responsive grid sm:grid-cols-2 xl:grid-cols-3
each category is a clickable button
button style:
rounded-2xl
border
bg-background text-foreground
shadow-sm
hover changes to bg-accent hover:text-accent-foreground
content of each category card:
category name
outline badge saying Click for more
large main number = in-stock count
sentence In Stock (STK) units in Kharkhoda plant.
bottom inline row with View other usage counts and chevron-right icon
click navigates to /category/{categoryName}
Filtering and business logic:

Source data comes from asset records.
Only rows matching Kharkhoda plant should appear in dashboard summaries and category section.
Matching rule: Asset Store values must represent either Kharkhoda Store or Kharkhoda New Asset Store.
Each asset row has fields including at least:
assetCode
categoryName
assetUsage
additional spreadsheet-derived fields for details
Use utility helpers similar to:
normalizeAssetValue
normalizeUsageKey
matchesKharkhodaStore
sortByCategoryName
formatAssetValue
Normalize blank/missing values gracefully.
Uncategorized rows should display as Uncategorized.
In Stock (STK) is the primary usage bucket.
Other usage buckets are pre-defined by ordered keys in a constant like OTHER_USAGE_ORDER.
Asset usage labels should map usage keys to readable labels.
Home page data derivation:

kharkhodaAssets = all assets filtered by matchesKharkhodaStore, sorted by category.
categorySummary:
aggregate by normalized category name
count total assets in category
count only STK assets in inStockCount
maintain ordered counts for all non-STK usage buckets
sort categories by descending inStockCount, then alphabetical category
summaryCards derived from category summaries and filtered assets.
Asset detail page /asset/:assetCode:

Use useParams.
Decode assetCode from URL.
Load asset list with same hook.
Find matching record by normalized asset code, case-insensitive.
Layout:
top row with back button and optional category badge on the right
back button is outline variant with arrow-left icon and text Back to dashboard
small muted label: Asset detail screen
large heading showing decoded asset code or Asset lookup
Loading state:
grid of 8 skeleton cards h-28 rounded-2xl
Empty state:
Empty card with package-search icon
title Asset code not found
description No asset record matches {code} in the current uploaded dataset.
button Return to dashboard
Success state:
single bordered card
title is formatted asset code
description Full asset record from the uploaded spreadsheet, grouped for quick reading.
content is a grid md:grid-cols-2 xl:grid-cols-3
map over a constant field list like assetDetailFields
each field cell:
rounded-2xl border bg-background shadow-sm
small uppercase muted label with tracking
main value below using formatAssetValue
The category badge on top uses Badge variant="secondary" and displays formatted category name if asset exists.
Category detail page /category/:categoryName:

Use useParams.
Decode category name.
Load asset list.
Filter to rows that both:
match Kharkhoda store
have normalized category name equal to decoded category, case-insensitive
Compute:
inStockCount = number of STK rows
usageSummary = ordered non-STK bucket counts only
Layout:
top row with back button and right-side badge
back button same as asset detail page
muted label Category usage detail
heading = category name or Category detail
muted paragraph: Other usage counts for this category in Kharkhoda plant.
right badge text: In Stock (STK): {count}
Loading state:
8 skeleton blocks in grid md:grid-cols-2 xl:grid-cols-4
Empty state:
Empty with boxes icon
title No category rows found
description No Kharkhoda plant rows match {category} in the current dataset.
button Return to dashboard
Success state:
bordered card
title = decoded category name
description:
These counts exclude In Stock (STK) because the dashboard card already represents the STK total.
content grid md:grid-cols-2 xl:grid-cols-4
each usage bucket card:
rounded-2xl border bg-background shadow-sm
usage label
large count
muted text Kharkhoda rows in this independent usage bucket.
Exact visual behavior notes:

Main page content begins immediately; no top nav bar.
Every page container uses centered width and similar spacing.
Many surfaces are rounded and softly bordered.
Use shadow-sm frequently, but keep the feel restrained.
Use semantic token classes only.
Use text-muted-foreground only on background/card-compatible surfaces.
No hardcoded palette classes.
No footers or extra panels.
No extra features beyond upload, summaries, search, and drilldown.

Primary business rule

All dashboard counts and category summaries must be filtered to Kharkhoda plant rows only.
Kharkhoda rows are defined as rows whose Asset Store value matches either:
Kharkhoda Store
Kharkhoda New Asset Store


Category values come dynamically from the spreadsheet field categoryName.
Each category card represents one distinct normalized category value found in filtered Kharkhoda rows.
Blank or missing categories must display as:
Uncategorized
Known asset usage values The app clearly treats one usage as the primary stock bucket and others as non-stock buckets.

Required usage logic:

Primary usage bucket:
In Stock (STK)
Internal comparison key for in-stock bucket:
STK
The dashboard category card main number must count only assets whose normalized asset usage maps to:
In Stock (STK)
Other asset usage values

The app also supports multiple non-STK usage buckets.
These are driven from an ordered constant such as OTHER_USAGE_ORDER.
Their human-readable labels come from a mapping such as assetUsageLabels.
The exact list of non-STK usage labels is not visible in the route files alone, so create the app with:
one primary usage bucket: In Stock (STK)
an ordered list of other usage buckets maintained in constants
each non-STK bucket shown on the category detail page
labels rendered from a usage-label map


