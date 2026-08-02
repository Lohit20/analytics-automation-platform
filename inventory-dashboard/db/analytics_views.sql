-- Decision-support views: turn raw stock/reorder history into a dynamic
-- reorder point and supplier performance scoring, instead of relying on a
-- static reorder_level someone set once and never revisited.

-- Average and variability of daily sales per product over a trailing
-- 60-day window. Built from a full calendar spine (not just days with a
-- sale) so zero-sale days correctly pull the average and stddev down --
-- otherwise slow-moving products would look busier than they are.
CREATE OR REPLACE VIEW product_sales_velocity AS
WITH window_days AS (
    SELECT generate_series(
        CURRENT_DATE - INTERVAL '60 days', CURRENT_DATE - INTERVAL '1 day', INTERVAL '1 day'
    )::date AS sale_date
),
daily_sales AS (
    SELECT
        p.product_id,
        wd.sale_date,
        COALESCE(SUM(ABS(se.change_quantity)), 0) AS qty_sold
    FROM products p
    CROSS JOIN window_days wd
    LEFT JOIN stock_entries se
        ON se.product_id = p.product_id
       AND se.entry_date = wd.sale_date
       AND se.change_type = 'Sale'
    GROUP BY p.product_id, wd.sale_date
)
SELECT
    product_id,
    AVG(qty_sold) AS avg_daily_sales,
    STDDEV_POP(qty_sold) AS stddev_daily_sales
FROM daily_sales
GROUP BY product_id;

-- Actual historical lead time and on-time delivery rate per supplier,
-- computed from completed (received) reorders rather than assumed.
CREATE OR REPLACE VIEW supplier_lead_time AS
SELECT
    p.supplier_id,
    s.sla_days,
    AVG(sh.received_date - r.reorder_date) AS avg_lead_time_days,
    COUNT(*) AS completed_reorders,
    COUNT(*) FILTER (
        WHERE (sh.received_date - r.reorder_date) <= s.sla_days
    ) AS on_time_reorders
FROM reorders r
JOIN products p ON p.product_id = r.product_id
JOIN suppliers s ON s.supplier_id = p.supplier_id
JOIN shipments sh ON sh.reorder_id = r.reorder_id
WHERE sh.received_date IS NOT NULL
GROUP BY p.supplier_id, s.sla_days;

-- Supplier-facing summary: lead time and on-time % per supplier, for the
-- "self-serve supplier metrics" view.
CREATE OR REPLACE VIEW supplier_performance AS
SELECT
    s.supplier_id,
    s.supplier_name,
    s.sla_days,
    ROUND(lt.avg_lead_time_days, 1) AS avg_lead_time_days,
    lt.completed_reorders,
    lt.on_time_reorders,
    CASE WHEN lt.completed_reorders > 0
         THEN ROUND(100.0 * lt.on_time_reorders / lt.completed_reorders, 1)
         ELSE NULL
    END AS on_time_rate_pct
FROM suppliers s
LEFT JOIN supplier_lead_time lt ON lt.supplier_id = s.supplier_id
ORDER BY s.supplier_name;

-- Dynamic reorder point per product: expected demand over the supplier's
-- actual lead time, plus a safety-stock buffer sized off demand variability
-- (95% service level, same z-score convention used in the FX risk model).
-- Falls back to a 7-day lead time assumption when a supplier has no
-- completed-reorder history yet to compute one from.
CREATE OR REPLACE VIEW dynamic_reorder_point AS
SELECT
    p.product_id,
    p.product_name,
    p.category,
    s.supplier_name,
    p.stock_quantity,
    p.reorder_level AS static_reorder_level,
    ROUND(v.avg_daily_sales, 2) AS avg_daily_sales,
    ROUND(COALESCE(lt.avg_lead_time_days, 7), 1) AS lead_time_days,
    ROUND(
        (v.avg_daily_sales * COALESCE(lt.avg_lead_time_days, 7))
        + (1.65 * COALESCE(v.stddev_daily_sales, 0) * SQRT(COALESCE(lt.avg_lead_time_days, 7)))
    ) AS dynamic_reorder_point
FROM products p
JOIN suppliers s ON s.supplier_id = p.supplier_id
JOIN product_sales_velocity v ON v.product_id = p.product_id
LEFT JOIN supplier_lead_time lt ON lt.supplier_id = p.supplier_id;
