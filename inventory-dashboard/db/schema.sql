-- Core inventory and supply chain schema.

CREATE TABLE suppliers (
    supplier_id     SERIAL PRIMARY KEY,
    supplier_name   TEXT NOT NULL,
    contact_name    TEXT,
    email           TEXT,
    phone           TEXT,
    -- Contracted delivery time in days, used to score actual lead time
    -- against what the supplier agreed to.
    sla_days        INTEGER NOT NULL DEFAULT 7 CHECK (sla_days > 0)
);

CREATE TABLE products (
    product_id      SERIAL PRIMARY KEY,
    product_name    TEXT NOT NULL,
    category        TEXT NOT NULL,
    price           NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    stock_quantity  INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    reorder_level   INTEGER NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(supplier_id)
);

-- Every stock movement (sale or restock) is logged here, giving a full
-- audit trail per product without needing a separate history table.
CREATE TABLE stock_entries (
    entry_id        SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    change_type     TEXT NOT NULL CHECK (change_type IN ('Sale', 'Restock')),
    change_quantity INTEGER NOT NULL,
    entry_date      DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE reorders (
    reorder_id       SERIAL PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(product_id),
    reorder_quantity INTEGER NOT NULL CHECK (reorder_quantity > 0),
    reorder_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    status           TEXT NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Received'))
);

CREATE TABLE shipments (
    shipment_id     SERIAL PRIMARY KEY,
    reorder_id      INTEGER NOT NULL REFERENCES reorders(reorder_id),
    shipped_date    DATE,
    received_date   DATE
);

CREATE INDEX idx_stock_entries_product ON stock_entries(product_id);
CREATE INDEX idx_reorders_product ON reorders(product_id);
CREATE INDEX idx_reorders_status ON reorders(status);

-- Read-optimised view for the "Product History" screen: every stock
-- movement for a product, newest first, with a running balance.
CREATE VIEW product_inventory_history AS
SELECT
    se.product_id,
    p.product_name,
    se.entry_date AS record_date,
    se.change_type,
    se.change_quantity,
    SUM(se.change_quantity) OVER (
        PARTITION BY se.product_id ORDER BY se.entry_date, se.entry_id
    ) AS running_balance
FROM stock_entries se
JOIN products p ON p.product_id = se.product_id
ORDER BY se.product_id, se.entry_date DESC;
