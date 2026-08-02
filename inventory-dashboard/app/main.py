import pandas as pd
import plotly.express as px
import streamlit as st
from psycopg2.extras import RealDictCursor

from database import connect_to_db
from queries import (
    add_product,
    get_all_products,
    get_categories,
    get_category_stock_value,
    get_daily_value_trend,
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

all_categories = get_categories(cursor)
all_supplier_names = [s["supplier_name"] for s in get_suppliers(cursor)]

if page == "Overview":
    with st.expander("Filters", expanded=False):
        col1, col2 = st.columns(2)
        selected_categories = col1.multiselect("Category", all_categories)
        selected_suppliers = col2.multiselect("Supplier", all_supplier_names)
    categories_filter = selected_categories or None
    suppliers_filter = selected_suppliers or None

    st.header("Headline Metrics")
    metrics = get_headline_metrics(cursor)
    labels = list(metrics.keys())

    cols = st.columns(3)
    for i, label in enumerate(labels[:3]):
        cols[i].metric(label=label, value=metrics[label])

    cols = st.columns(3)
    for i, label in enumerate(labels[3:6]):
        cols[i].metric(label=label, value=metrics[label])

    st.caption("Headline metrics are portfolio-wide; the tables and charts below respect the filters above.")
    st.divider()

    st.subheader("Sales & Restock Value Trend (Last 90 Days)")
    trend_rows = get_daily_value_trend(cursor)
    if trend_rows:
        trend_df = pd.DataFrame(trend_rows).astype({"value": "float"})
        fig = px.line(
            trend_df,
            x="date",
            y="value",
            color="change_type",
            title=None,
            labels={"date": "Date", "value": "Value (£)", "change_type": ""},
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No stock movement in the last 90 days.")

    st.subheader("Stock Value by Category")
    category_rows = get_category_stock_value(cursor, categories_filter, suppliers_filter)
    if category_rows:
        category_df = pd.DataFrame(category_rows).astype({"stock_value": "float"})
        fig = px.pie(category_df, names="category", values="stock_value", hole=0.4)
        fig.update_traces(textinfo="label+percent")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No products match the current filter.")

    st.subheader("Supplier Contacts")
    st.dataframe(pd.DataFrame(get_supplier_metrics(cursor)))

    st.subheader("Stock by Product and Supplier")
    st.dataframe(pd.DataFrame(get_restock_metrics(cursor, categories_filter, suppliers_filter)))

    st.subheader("Products Needing Reorder")
    needing_reorder = get_products_needing_reorder(cursor, categories_filter, suppliers_filter)
    if needing_reorder:
        st.dataframe(pd.DataFrame(needing_reorder))
    else:
        st.info("Nothing below reorder level for the current filter.")

elif page == "Reorder & Supplier Analytics":
    with st.expander("Filters", expanded=False):
        col1, col2 = st.columns(2)
        selected_categories = col1.multiselect("Category", all_categories, key="analytics_category")
        selected_suppliers = col2.multiselect("Supplier", all_supplier_names, key="analytics_supplier")
    categories_filter = selected_categories or None
    suppliers_filter = selected_suppliers or None

    st.header("Dynamic Reorder Points")
    st.caption(
        "Reorder point computed from actual sales velocity and each supplier's real "
        "lead time, at a 95% service level — compared against the static reorder_level "
        "someone set once. Large gaps are worth revisiting."
    )
    reorder_df = pd.DataFrame(get_dynamic_reorder_points(cursor, categories_filter, suppliers_filter))
    st.dataframe(reorder_df, width="stretch")

    if not reorder_df.empty:
        top_n = st.slider("Show top N products by gap size", 3, min(20, len(reorder_df)), min(10, len(reorder_df)))
        chart_df = reorder_df.head(top_n).astype(
            {"static_reorder_level": "float", "dynamic_reorder_point": "float"}
        )
        melted = chart_df.melt(
            id_vars="product_name",
            value_vars=["static_reorder_level", "dynamic_reorder_point"],
            var_name="metric",
            value_name="units",
        )
        fig = px.bar(
            melted,
            x="product_name",
            y="units",
            color="metric",
            barmode="group",
            title="Static vs. Dynamic Reorder Point",
            labels={"product_name": "Product", "units": "Reorder point (units)", "metric": ""},
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, width="stretch")

    st.divider()

    st.header("Supplier Performance")
    st.caption(
        "Actual average lead time and on-time delivery rate per supplier, computed from "
        "completed reorders (reorder date to received date) against each supplier's SLA."
    )
    perf_df = pd.DataFrame(get_supplier_performance(cursor))
    st.dataframe(perf_df, width="stretch")

    if not perf_df.empty and perf_df["on_time_rate_pct"].notna().any():
        # psycopg2 returns NUMERIC columns as Decimal; Plotly/pandas need
        # float, not Decimal, for a proper quantitative axis.
        chart_df = perf_df.astype(
            {"on_time_rate_pct": "float", "avg_lead_time_days": "float", "sla_days": "float"}
        )
        fig = px.bar(
            chart_df,
            x="supplier_name",
            y="on_time_rate_pct",
            color="on_time_rate_pct",
            color_continuous_scale="RdYlGn",
            range_color=[0, 100],
            hover_data={
                "avg_lead_time_days": True,
                "sla_days": True,
                "completed_reorders": True,
                "on_time_rate_pct": ":.1f",
            },
            title="On-Time Delivery Rate by Supplier",
            labels={"supplier_name": "Supplier", "on_time_rate_pct": "On-time rate (%)"},
        )
        fig.add_hline(y=80, line_dash="dot", annotation_text="80% target", annotation_position="top left")
        st.plotly_chart(fig, width="stretch")

        st.subheader("Lead Time vs. Reliability")
        st.caption(
            "Each point is a supplier: how fast they deliver (x) vs how often they hit "
            "their own SLA (y). Bubble size is order volume — the suppliers worth the most "
            "scrutiny are large bubbles that are slow, unreliable, or both."
        )
        scatter_df = chart_df.dropna(subset=["on_time_rate_pct"])
        if not scatter_df.empty:
            fig2 = px.scatter(
                scatter_df,
                x="avg_lead_time_days",
                y="on_time_rate_pct",
                size="completed_reorders",
                color="supplier_name",
                text="supplier_name",
                labels={
                    "avg_lead_time_days": "Avg lead time (days)",
                    "on_time_rate_pct": "On-time rate (%)",
                    "completed_reorders": "Completed reorders",
                },
            )
            fig2.update_traces(textposition="top center")
            fig2.update_yaxes(range=[0, 105])
            st.plotly_chart(fig2, width="stretch")

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
                history_df = pd.DataFrame(history).sort_values("record_date")
                fig = px.line(
                    history_df,
                    x="record_date",
                    y="running_balance",
                    markers=True,
                    title=f"Stock Balance Over Time — {selected_name}",
                    labels={"record_date": "Date", "running_balance": "Stock on hand"},
                )
                sales = history_df[history_df["change_type"] == "Sale"]
                restocks = history_df[history_df["change_type"] == "Restock"]
                fig.add_scatter(
                    x=sales["record_date"], y=sales["running_balance"],
                    mode="markers", marker=dict(color="crimson", size=8, symbol="triangle-down"),
                    name="Sale",
                )
                fig.add_scatter(
                    x=restocks["record_date"], y=restocks["running_balance"],
                    mode="markers", marker=dict(color="seagreen", size=8, symbol="triangle-up"),
                    name="Restock",
                )
                st.plotly_chart(fig, width="stretch")

                st.dataframe(history_df.sort_values("record_date", ascending=False), width="stretch")
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
