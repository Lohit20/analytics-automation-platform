# Inventory and Supply Chain Management Dashboard

A PostgreSQL-backed dashboard that flags low-stock products and automates the
reorder-to-receipt workflow, replacing manual, error-prone reorder tracking
with a self-serve tool stakeholders can use directly.

**Stack:** Python · SQL (PostgreSQL) · Streamlit

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
│   └── procedures.sql       # add_product, place_reorder, mark_reorder_as_received
├── scripts/
│   └── seed_data.py         # synthetic suppliers/products/stock-movement generator
├── app/
│   ├── db.py                # connection (env-based config)
│   ├── queries.py           # business-logic query functions
│   └── main.py               # Streamlit UI (Overview + Operational Tasks)
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
