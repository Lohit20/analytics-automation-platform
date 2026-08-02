"""Business-logic queries backing the dashboard: stock health, supplier metrics, reorder workflow."""

from decimal import Decimal


def _to_jsonable(value):
    return float(value) if isinstance(value, Decimal) else value


def get_headline_metrics(cursor) -> dict:
    queries = {
        "Total Suppliers": "SELECT COUNT(*) FROM suppliers",
        "Total Products": "SELECT COUNT(*) FROM products",
        "Categories": "SELECT COUNT(DISTINCT category) FROM products",
        "Sales Value (Last 90 Days)": """
            SELECT ROUND(SUM(ABS(se.change_quantity) * p.price)::numeric, 2)
            FROM stock_entries se JOIN products p ON p.product_id = se.product_id
            WHERE se.change_type = 'Sale' AND se.entry_date >= CURRENT_DATE - INTERVAL '90 days'
        """,
        "Restock Value (Last 90 Days)": """
            SELECT ROUND(SUM(ABS(se.change_quantity) * p.price)::numeric, 2)
            FROM stock_entries se JOIN products p ON p.product_id = se.product_id
            WHERE se.change_type = 'Restock' AND se.entry_date >= CURRENT_DATE - INTERVAL '90 days'
        """,
        "Below Reorder & No Pending Reorder": """
            SELECT COUNT(*) FROM products p
            WHERE p.stock_quantity < p.reorder_level
              AND p.product_id NOT IN (SELECT product_id FROM reorders WHERE status = 'Pending')
        """,
    }
    results = {}
    for label, sql in queries.items():
        cursor.execute(sql)
        row = cursor.fetchone()
        value = row[0] if not isinstance(row, dict) else next(iter(row.values()))
        results[label] = _to_jsonable(value)
    return results


def get_supplier_metrics(cursor):
    cursor.execute("""
        SELECT supplier_name, contact_name, email, phone
        FROM suppliers ORDER BY supplier_name
    """)
    return cursor.fetchall()


def get_restock_metrics(cursor, categories=None, supplier_names=None):
    sql = """
        SELECT p.product_name, p.category, s.supplier_name, p.stock_quantity, p.reorder_level
        FROM products p JOIN suppliers s ON p.supplier_id = s.supplier_id
        WHERE (%(categories)s IS NULL OR p.category = ANY(%(categories)s))
          AND (%(suppliers)s IS NULL OR s.supplier_name = ANY(%(suppliers)s))
        ORDER BY p.product_name
    """
    cursor.execute(sql, {"categories": categories, "suppliers": supplier_names})
    return cursor.fetchall()


def get_dynamic_reorder_points(cursor, categories=None, supplier_names=None):
    """Products where sales-velocity-driven reorder point diverges from the
    static reorder_level someone set once -- the ones worth revisiting."""
    sql = """
        SELECT product_name, category, supplier_name, stock_quantity, static_reorder_level,
               avg_daily_sales, lead_time_days, dynamic_reorder_point,
               (dynamic_reorder_point - static_reorder_level) AS delta
        FROM dynamic_reorder_point
        WHERE (%(categories)s IS NULL OR category = ANY(%(categories)s))
          AND (%(suppliers)s IS NULL OR supplier_name = ANY(%(suppliers)s))
        ORDER BY ABS(dynamic_reorder_point - static_reorder_level) DESC
    """
    cursor.execute(sql, {"categories": categories, "suppliers": supplier_names})
    return cursor.fetchall()


def get_supplier_performance(cursor):
    cursor.execute("SELECT * FROM supplier_performance")
    return cursor.fetchall()


def get_products_needing_reorder(cursor, categories=None, supplier_names=None):
    sql = """
        SELECT p.product_name, p.category, s.supplier_name, p.stock_quantity, p.reorder_level
        FROM products p JOIN suppliers s ON p.supplier_id = s.supplier_id
        WHERE p.stock_quantity <= p.reorder_level
          AND (%(categories)s IS NULL OR p.category = ANY(%(categories)s))
          AND (%(suppliers)s IS NULL OR s.supplier_name = ANY(%(suppliers)s))
        ORDER BY (p.reorder_level - p.stock_quantity) DESC
    """
    cursor.execute(sql, {"categories": categories, "suppliers": supplier_names})
    return cursor.fetchall()


def get_categories(cursor):
    cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
    return [row["category"] for row in cursor.fetchall()]


def get_suppliers(cursor):
    cursor.execute("SELECT supplier_id, supplier_name FROM suppliers ORDER BY supplier_name")
    return cursor.fetchall()


def get_all_products(cursor):
    cursor.execute("SELECT product_id, product_name FROM products ORDER BY product_name")
    return cursor.fetchall()


def get_product_history(cursor, product_id):
    cursor.execute(
        "SELECT * FROM product_inventory_history WHERE product_id = %s ORDER BY record_date DESC",
        (product_id,),
    )
    return cursor.fetchall()


def get_pending_reorders(cursor):
    cursor.execute("""
        SELECT r.reorder_id, p.product_name, r.reorder_quantity, r.reorder_date
        FROM reorders r JOIN products p ON r.product_id = p.product_id
        WHERE r.status = 'Pending'
        ORDER BY r.reorder_date
    """)
    return cursor.fetchall()


def add_product(cursor, conn, name, category, price, stock, reorder_level, supplier_id):
    cursor.execute(
        "CALL add_product(%s, %s, %s, %s, %s, %s)",
        (name, category, price, stock, reorder_level, supplier_id),
    )
    conn.commit()


def place_reorder(cursor, conn, product_id, quantity):
    cursor.execute("CALL place_reorder(%s, %s)", (product_id, quantity))
    conn.commit()


def mark_reorder_as_received(cursor, conn, reorder_id):
    cursor.execute("CALL mark_reorder_as_received(%s)", (reorder_id,))
    conn.commit()
