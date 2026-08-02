import pandas as pd
import streamlit as st
from psycopg2.extras import RealDictCursor

from database import connect_to_db
from queries import (
    add_product,
    get_all_products,
    get_categories,
    get_dynamic_reorder_points,
    get_headline_metrics,
    get_pending_reorders,
    get_product_history,
    get_products_needing_reorder,
    get_restock_metrics,
    get_supplier_metrics,
    get_supplier_performance,
    get_suppliers,
    mark_reorder_as_received,
    place_reorder,
)

st.sidebar.title("Inventory Management Dashboard")
page = st.sidebar.radio("Select Option:", ["Overview", "Reorder & Supplier Analytics", "Operational Tasks"])

st.title("Inventory and Supply Chain Dashboard")

db = connect_to_db()
cursor = db.cursor(cursor_factory=RealDictCursor)

if page == "Overview":
    st.header("Headline Metrics")
    metrics = get_headline_metrics(cursor)
    labels = list(metrics.keys())

    cols = st.columns(3)
    for i, label in enumerate(labels[:3]):
        cols[i].metric(label=label, value=metrics[label])

    cols = st.columns(3)
    for i, label in enumerate(labels[3:6]):
        cols[i].metric(label=label, value=metrics[label])

    st.divider()

    st.subheader("Supplier Contacts")
    st.dataframe(pd.DataFrame(get_supplier_metrics(cursor)))

    st.subheader("Stock by Product and Supplier")
    st.dataframe(pd.DataFrame(get_restock_metrics(cursor)))

    st.subheader("Products Needing Reorder")
    needing_reorder = get_products_needing_reorder(cursor)
    if needing_reorder:
        st.dataframe(pd.DataFrame(needing_reorder))
    else:
        st.info("Nothing below reorder level right now.")

elif page == "Reorder & Supplier Analytics":
    st.header("Dynamic Reorder Points")
    st.caption(
        "Reorder point computed from actual sales velocity and each supplier's real "
        "lead time, at a 95% service level — compared against the static reorder_level "
        "someone set once. Large gaps are worth revisiting."
    )
    reorder_df = pd.DataFrame(get_dynamic_reorder_points(cursor))
    st.dataframe(reorder_df, width="stretch")

    st.divider()

    st.header("Supplier Performance")
    st.caption(
        "Actual average lead time and on-time delivery rate per supplier, computed from "
        "completed reorders (reorder date to received date) against each supplier's SLA."
    )
    perf_df = pd.DataFrame(get_supplier_performance(cursor))
    st.dataframe(perf_df, width="stretch")

    if not perf_df.empty and perf_df["on_time_rate_pct"].notna().any():
        # psycopg2 returns NUMERIC columns as Decimal; Altair can't infer a
        # quantitative axis from Decimal and silently falls back to a
        # nominal (categorical) one, producing a nonsensical chart -- cast
        # to float before handing off to the chart.
        chart_df = perf_df.assign(on_time_rate_pct=perf_df["on_time_rate_pct"].astype(float))
        st.bar_chart(chart_df.set_index("supplier_name")["on_time_rate_pct"])

elif page == "Operational Tasks":
    task = st.selectbox("Choose a task", ["Add New Product", "Product History", "Place Reorder", "Receive Reorder"])

    if task == "Add New Product":
        st.header("Add New Product")
        categories = get_categories(cursor)
        suppliers = get_suppliers(cursor)

        with st.form("add_product_form"):
            name = st.text_input("Product Name")
            category = st.selectbox("Category", categories + ["New category..."])
            if category == "New category...":
                category = st.text_input("New category name")
            price = st.number_input("Price", min_value=0.0, step=0.5)
            stock = st.number_input("Stock Quantity", min_value=0, step=1)
            reorder_level = st.number_input("Reorder Level", min_value=0, step=1)

            supplier_ids = [s["supplier_id"] for s in suppliers]
            supplier_names = [s["supplier_name"] for s in suppliers]
            supplier_id = st.selectbox(
                "Supplier", options=supplier_ids, format_func=lambda x: supplier_names[supplier_ids.index(x)]
            )

            if st.form_submit_button("Add Product"):
                if not name:
                    st.error("Please enter a product name.")
                else:
                    try:
                        add_product(cursor, db, name, category, price, stock, reorder_level, supplier_id)
                        st.success(f"Product '{name}' added.")
                    except Exception as e:
                        st.error(f"Error adding product: {e}")

    elif task == "Product History":
        st.header("Product Inventory History")
        products = get_all_products(cursor)
        product_names = [p["product_name"] for p in products]
        product_ids = [p["product_id"] for p in products]

        selected_name = st.selectbox("Select a product", options=product_names)
        if selected_name:
            product_id = product_ids[product_names.index(selected_name)]
            history = get_product_history(cursor, product_id)
            if history:
                st.dataframe(pd.DataFrame(history))
            else:
                st.info("No history for this product.")

    elif task == "Place Reorder":
        st.header("Place a Reorder")
        products = get_all_products(cursor)
        product_names = [p["product_name"] for p in products]
        product_ids = [p["product_id"] for p in products]

        selected_name = st.selectbox("Select a product", options=product_names)
        quantity = st.number_input("Reorder Quantity", min_value=1, step=1)

        if st.button("Place Reorder"):
            product_id = product_ids[product_names.index(selected_name)]
            try:
                place_reorder(cursor, db, product_id, quantity)
                st.success(f"Reorder placed for {selected_name} x{quantity}.")
            except Exception as e:
                st.error(f"Error placing reorder: {e}")

    elif task == "Receive Reorder":
        st.header("Mark Reorder as Received")
        pending = get_pending_reorders(cursor)

        if not pending:
            st.info("No pending reorders to receive.")
        else:
            reorder_ids = [r["reorder_id"] for r in pending]
            labels = [f"#{r['reorder_id']} - {r['product_name']} (qty {r['reorder_quantity']})" for r in pending]

            selected_label = st.selectbox("Select reorder to mark as received", options=labels)
            if st.button("Mark as Received"):
                reorder_id = reorder_ids[labels.index(selected_label)]
                try:
                    mark_reorder_as_received(cursor, db, reorder_id)
                    st.success(f"Reorder #{reorder_id} marked as received.")
                except Exception as e:
                    st.error(f"Error: {e}")
