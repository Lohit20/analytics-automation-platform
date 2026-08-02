"""Generate synthetic suppliers/products/stock-movement data and load it into Postgres.

Run after the database is up (docker compose up -d db):
    python scripts/seed_data.py
"""

import datetime as dt
import os
import random

import psycopg2

random.seed(7)

DB_DSN = dict(
    host=os.environ.get("INVENTORY_DB_HOST", "localhost"),
    port=os.environ.get("INVENTORY_DB_PORT", "5433"),
    user=os.environ.get("INVENTORY_DB_USER", "inventory"),
    password=os.environ.get("INVENTORY_DB_PASSWORD", "inventory"),
    dbname=os.environ.get("INVENTORY_DB_NAME", "inventory"),
)

SUPPLIERS = [
    ("Northwind Components", "Priya Shah", "priya@northwindcomp.example", "+44 20 7946 0011"),
    ("Atlas Hardware Co.", "Tom Reilly", "tom@atlashardware.example", "+44 161 496 0022"),
    ("Meridian Supplies", "Elena Petrova", "elena@meridiansupplies.example", "+44 131 496 0033"),
    ("Brightline Parts", "Sam Osei", "sam@brightlineparts.example", "+44 117 496 0044"),
]

# sla_days is the contracted delivery time; (mean_lead, std_lead) is the
# supplier's *actual* delivery behaviour used to generate believable
# history -- some suppliers beat their SLA, some don't, so on-time rate
# actually differentiates them instead of being uniformly 100%.
SUPPLIER_SLA_DAYS = [7, 5, 10, 6]
SUPPLIER_LEAD_PROFILE = [(5, 1.5), (7, 2.5), (8, 1.0), (6, 2.0)]

CATEGORIES = {
    "Electronics": ["USB-C Cable 1m", "Wireless Mouse", "27in Monitor", "Mechanical Keyboard", "Webcam 1080p"],
    "Office Supplies": ["A4 Paper Ream", "Stapler", "Whiteboard Markers", "Desk Organiser", "Sticky Notes Pack"],
    "Packaging": ["Corrugated Box M", "Bubble Wrap Roll", "Packing Tape", "Pallet Wrap", "Shipping Labels"],
    "Furniture": ["Office Chair", "Standing Desk", "Filing Cabinet", "Bookshelf", "Monitor Arm"],
}


def build_products():
    products = []
    for category, names in CATEGORIES.items():
        for name in names:
            price = round(random.uniform(5, 400), 2)
            stock = random.randint(0, 120)
            reorder_level = random.randint(15, 40)
            supplier_id = random.randint(1, len(SUPPLIERS))
            products.append((name, category, price, stock, reorder_level, supplier_id))
    return products


def build_historical_reorders(product_supplier, n_per_supplier=6):
    """Completed reorders with realistic lead times, so supplier_performance
    has enough history to compute a meaningful on-time rate per supplier."""
    today = dt.date.today()
    by_supplier = {}
    for product_id, supplier_id in product_supplier:
        by_supplier.setdefault(supplier_id, []).append(product_id)

    rows = []  # (product_id, quantity, reorder_date, shipped_date, received_date)
    for supplier_id, product_ids in by_supplier.items():
        mean_lead, std_lead = SUPPLIER_LEAD_PROFILE[supplier_id - 1]
        for _ in range(n_per_supplier):
            product_id = random.choice(product_ids)
            lead_time = max(1, round(random.gauss(mean_lead, std_lead)))
            reorder_date = today - dt.timedelta(days=random.randint(lead_time + 5, 100))
            received_date = reorder_date + dt.timedelta(days=lead_time)
            shipped_date = reorder_date + dt.timedelta(days=max(1, lead_time - 2))
            qty = random.randint(30, 80)
            rows.append((product_id, qty, reorder_date, shipped_date, received_date))
    return rows


def build_stock_entries(product_ids, days=120):
    """Simulate ~4 months of daily sales with periodic restocks."""
    entries = []
    today = dt.date.today()
    for product_id in product_ids:
        running_stock = random.randint(20, 100)
        for offset in range(days, 0, -1):
            entry_date = today - dt.timedelta(days=offset)
            if random.random() < 0.35:
                sale_qty = -random.randint(1, 6)
                entries.append((product_id, "Sale", sale_qty, entry_date))
                running_stock += sale_qty
            if running_stock < 15 and random.random() < 0.5:
                restock_qty = random.randint(30, 80)
                entries.append((product_id, "Restock", restock_qty, entry_date))
                running_stock += restock_qty
    return entries


def main():
    conn = psycopg2.connect(**DB_DSN)
    cur = conn.cursor()

    print("Seeding suppliers...")
    for supplier, sla_days in zip(SUPPLIERS, SUPPLIER_SLA_DAYS):
        cur.execute(
            "INSERT INTO suppliers (supplier_name, contact_name, email, phone, sla_days) VALUES (%s, %s, %s, %s, %s)",
            supplier + (sla_days,),
        )

    print("Seeding products...")
    products = build_products()
    product_ids = []
    product_supplier = []
    for product in products:
        cur.execute(
            """INSERT INTO products (product_name, category, price, stock_quantity, reorder_level, supplier_id)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING product_id""",
            product,
        )
        product_id = cur.fetchone()[0]
        product_ids.append(product_id)
        product_supplier.append((product_id, product[-1]))

    print("Seeding stock movement history...")
    entries = build_stock_entries(product_ids)
    cur.executemany(
        "INSERT INTO stock_entries (product_id, change_type, change_quantity, entry_date) VALUES (%s, %s, %s, %s)",
        entries,
    )

    print("Seeding historical completed reorders (for supplier lead-time history)...")
    historical = build_historical_reorders(product_supplier)
    for product_id, qty, reorder_date, shipped_date, received_date in historical:
        cur.execute(
            """INSERT INTO reorders (product_id, reorder_quantity, reorder_date, status)
               VALUES (%s, %s, %s, 'Received') RETURNING reorder_id""",
            (product_id, qty, reorder_date),
        )
        reorder_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO shipments (reorder_id, shipped_date, received_date) VALUES (%s, %s, %s)",
            (reorder_id, shipped_date, received_date),
        )

    print("Seeding a few pending reorders for the operational demo...")
    pending_products = random.sample(product_ids, k=min(4, len(product_ids)))
    for product_id in pending_products:
        qty = random.randint(30, 80)
        cur.execute(
            "INSERT INTO reorders (product_id, reorder_quantity, reorder_date, status) VALUES (%s, %s, %s, 'Pending')",
            (product_id, qty, dt.date.today() - dt.timedelta(days=random.randint(1, 5))),
        )

    conn.commit()
    cur.close()
    conn.close()
    print(f"Done. Seeded {len(SUPPLIERS)} suppliers, {len(products)} products, "
          f"{len(entries)} stock entries, {len(historical)} historical reorders, "
          f"{len(pending_products)} pending reorders.")


if __name__ == "__main__":
    main()
