# Inventory and Supply Chain Management Dashboard

A PostgreSQL-backed dashboard that flags low-stock products and automates the
reorder-to-receipt workflow, replacing manual, error-prone reorder tracking
with a self-serve tool stakeholders can use directly.

**Stack:** Python · SQL (PostgreSQL) · Streamlit · Plotly

## The problem

Reorder tracking done manually (spreadsheets, memory, ad-hoc queries) breaks
down in two predictable ways: nobody notices a product has dropped below its
reorder point until it's too late, and a reorder that gets marked "received"
twice silently double-counts stock. Both are data-integrity problems, not UI
problems, so the fix lives in the database layer, not just the frontend.

## What it does

- **Flags low stock automatically** — a query surfaces every product below
  its reorder level that doesn't already have a pending reorder, so nothing
  gets missed or double-ordered.
- **Automates the reorder-to-receipt workflow** — placing a reorder and
  receiving it are stored procedures (`place_reorder`, `mark_reorder_as_received`),
  not ad-hoc UI logic, so the same rules apply everywhere.
- **Exception handling for pending vs. received reorders** — `mark_reorder_as_received`
  checks the reorder's current status before touching stock. Trying to receive
  an already-received reorder raises an error instead of silently double-adding
  stock. This is the core rule that actually prevents stockouts/overstock
  drift: without it, a double-click or a retried job would corrupt the balance.
- **Self-serve supplier and restock metrics** — supplier contacts, stock by
  product/supplier, and products needing reorder are all queryable from the
  dashboard directly, so stakeholders don't need to query the database.
- **Full audit trail** — every stock movement (sale or restock) is logged in
  `stock_entries`; `product_inventory_history` is a view with a running
  balance per product, so any point-in-time stock level is reconstructable.
- **Dynamic reorder points** — `reorder_level` is normally a number someone
  set once and forgot about. `dynamic_reorder_point` instead computes it from
  actual sales velocity (60-day trailing average and variability) times each
  supplier's real lead time, plus a safety-stock buffer sized for a 95%
  service level. The dashboard shows this next to the static value so the
  biggest gaps — the products most likely to be mis-configured — surface
  first.
- **Supplier performance scoring** — average lead time and on-time delivery
  rate per supplier, computed from completed reorders (`reorder_date` to
  `received_date` in `shipments`) against each supplier's contracted
  `sla_days`. Turns "trust the supplier's word" into a number backed by
  actual delivery history.

## Reorder & Supplier Analytics

A dedicated dashboard page built on two views:

- `dynamic_reorder_point` — per product: current stock, static reorder level,
  average daily sales, effective lead time, and the computed dynamic reorder
  point, sorted by how far it diverges from the static value. A grouped bar
  chart compares static vs. dynamic side by side for the biggest gaps
  (adjustable via a slider).
- `supplier_performance` — per supplier: average lead time, completed
  reorder count, and on-time rate against SLA, as a colour-scaled bar chart
  with an 80% target line, plus a lead-time-vs-reliability scatter (bubble
  size = order volume) that surfaces which suppliers are worth the most
  scrutiny at a glance.

## Interactivity

- **Filters** — category and supplier multiselect filters on Overview and
  Analytics pages drive every table and chart on the page.
- **Charts, not just tables** — Plotly powers a sales/restock value trend
  line, a stock-value-by-category donut, the reorder-point comparison and
  on-time-rate bar charts, and the lead-time-vs-reliability scatter — all
  with hover tooltips.
- **Product drill-down** — selecting a product under Operational Tasks →
  Product History renders its full stock-balance history as an interactive
  line chart (not just a table), with sale and restock events marked
  separately, so a stock dip or restock spike is visible at a glance instead
  of having to read rows.

## Running it locally

Requires Docker (for Postgres) and Python 3.

```bash
# 1. Start Postgres (schema + stored procedures load automatically)
docker compose up -d db

# 2. Install dependencies
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 3. Seed synthetic data (suppliers, products, ~4 months of stock movement)
./.venv/bin/python scripts/seed_data.py

# 4. Run the dashboard
./.venv/bin/streamlit run app/main.py
```

Connection settings come from environment variables (see `.env.example`),
not hardcoded credentials — copy it to `.env` and adjust if needed, or rely
on the defaults which match `docker-compose.yml`.

## Project structure

```
inventory-dashboard/
├── docker-compose.yml       # local Postgres for dev/testing
├── db/
│   ├── schema.sql           # tables, constraints, indexes, history view
│   ├── procedures.sql       # add_product, place_reorder, mark_reorder_as_received
│   └── analytics_views.sql  # dynamic_reorder_point, supplier_performance
├── scripts/
│   └── seed_data.py         # synthetic suppliers/products/stock-movement generator
├── app/
│   ├── database.py          # connection (env-based config)
│   ├── queries.py           # business-logic query functions
│   └── main.py               # Streamlit UI (Overview, Analytics, Operational Tasks)
└── requirements.txt
```

## Design notes

- **Business logic lives in stored procedures, not the app.** The reorder
  workflow and the "already received" guard are enforced in the database via
  `CALL`, so any client (this dashboard, a future scheduled job, a plain SQL
  session) gets the same guarantees instead of re-implementing the rule.
- **Credentials are environment-based**, not hardcoded, so the same code
  works against local Docker Postgres or a real instance without code changes.
- Verified end-to-end against a real Postgres container: schema/procedures
  load cleanly, seed data loads, headline metrics and reorder queries return
  correct results, and the double-receive guard was tested directly — a
  second `mark_reorder_as_received` call on an already-received reorder
  raises rather than double-counting stock.
- The analytics page was verified with Streamlit's `AppTest` framework
  (programmatically switching pages and checking for exceptions) as well as
  a manual HTTP/health check, against real seeded data with a realistic
  spread of supplier lead times so on-time rates actually differ (16.7% to
  100% in the seeded dataset) rather than being uniformly perfect.
- `avg_daily_sales` and `stddev_daily_sales` in `product_sales_velocity` are
  computed over a full calendar spine (`generate_series`), not just days
  with a recorded sale — otherwise slow-moving products would look busier
  than they are and the safety-stock buffer would be under-sized.
- **`Decimal` vs. chart libraries**: `psycopg2` returns `NUMERIC` columns as
  Python `Decimal`. Both Altair (Streamlit's default chart backend) and
  Plotly need `float` to infer a quantitative axis — handing them a `Decimal`
  column silently produces a nonsensical chart (this bit us once during
  testing: an inverted, mis-scaled axis) rather than an error. Every chart
  in this app explicitly casts `Decimal` columns to `float` first.
