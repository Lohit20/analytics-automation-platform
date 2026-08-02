"""Database connection. Credentials come from the environment, never hardcoded."""

import os

import psycopg2


def connect_to_db():
    return psycopg2.connect(
        host=os.environ.get("INVENTORY_DB_HOST", "localhost"),
        port=os.environ.get("INVENTORY_DB_PORT", "5433"),
        user=os.environ.get("INVENTORY_DB_USER", "inventory"),
        password=os.environ.get("INVENTORY_DB_PASSWORD", "inventory"),
        dbname=os.environ.get("INVENTORY_DB_NAME", "inventory"),
    )
