-- Business logic lives in stored procedures so every entry point (the
-- Streamlit app, ad-hoc SQL, a future scheduled job) goes through the
-- same rules instead of re-implementing them client-side.

CREATE OR REPLACE PROCEDURE add_product(
    p_name          TEXT,
    p_category      TEXT,
    p_price         NUMERIC,
    p_stock         INTEGER,
    p_reorder_level INTEGER,
    p_supplier_id   INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO products (product_name, category, price, stock_quantity, reorder_level, supplier_id)
    VALUES (p_name, p_category, p_price, p_stock, p_reorder_level, p_supplier_id);
END;
$$;

CREATE OR REPLACE PROCEDURE place_reorder(
    p_product_id INTEGER,
    p_quantity   INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Reorder quantity must be positive, got %', p_quantity;
    END IF;

    INSERT INTO reorders (product_id, reorder_quantity, reorder_date, status)
    VALUES (p_product_id, p_quantity, CURRENT_DATE, 'Pending');
END;
$$;

-- The core exception-handling rule: a reorder can only be received once.
-- Without this guard, double-clicking "receive" (or replaying a queued
-- job) would silently double-count stock and corrupt the balance instead
-- of preventing the stockout it was meant to fix.
CREATE OR REPLACE PROCEDURE mark_reorder_as_received(
    p_reorder_id INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_status     TEXT;
    v_product_id INTEGER;
    v_quantity   INTEGER;
BEGIN
    SELECT status, product_id, reorder_quantity
    INTO v_status, v_product_id, v_quantity
    FROM reorders
    WHERE reorder_id = p_reorder_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Reorder % does not exist', p_reorder_id;
    END IF;

    IF v_status = 'Received' THEN
        RAISE EXCEPTION 'Reorder % has already been received; refusing to double-count stock', p_reorder_id;
    END IF;

    UPDATE reorders SET status = 'Received' WHERE reorder_id = p_reorder_id;

    INSERT INTO stock_entries (product_id, change_type, change_quantity, entry_date)
    VALUES (v_product_id, 'Restock', v_quantity, CURRENT_DATE);

    UPDATE products
    SET stock_quantity = stock_quantity + v_quantity
    WHERE product_id = v_product_id;

    INSERT INTO shipments (reorder_id, shipped_date, received_date)
    VALUES (p_reorder_id, CURRENT_DATE - 3, CURRENT_DATE);
END;
$$;
