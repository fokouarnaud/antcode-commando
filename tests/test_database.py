import sqlite3

import pytest

from app.database import get_connection, init_db


def test_get_connection_returns_usable_sqlite_connection():
    conn = get_connection(":memory:")

    row = conn.execute("SELECT 1 AS result").fetchone()

    assert row["result"] == 1


def test_init_db_creates_all_six_tables():
    conn = get_connection(":memory:")

    init_db(conn)

    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    assert tables == {
        "customers",
        "addresses",
        "products",
        "orders",
        "order_items",
        "payments",
    }


def test_init_db_enforces_foreign_keys():
    conn = get_connection(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO customers (full_name, phone_number) VALUES (?, ?)",
        ("Amina Njoya", "+237690000001"),
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO addresses (customer_id, neighborhood, city, street_details) "
            "VALUES (?, ?, ?, ?)",
            (999, "Bonapriso", "Douala", "Rue 1234"),
        )


def test_init_db_creates_composite_neighborhood_index():
    conn = get_connection(":memory:")

    init_db(conn)

    index_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA index_info(idx_addresses_neighborhood_city)"
        ).fetchall()
    }
    assert index_columns == {"neighborhood", "city"}


def test_orders_table_has_neighborhood_and_delivery_status_columns():
    conn = get_connection(":memory:")

    init_db(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}
    assert {"customer_neighborhood", "delivery_status", "external_ref"} <= columns


def test_init_db_creates_orders_neighborhood_status_index():
    conn = get_connection(":memory:")

    init_db(conn)

    index_columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA index_info(idx_orders_neighborhood_status)"
        ).fetchall()
    ]
    assert index_columns == ["customer_neighborhood", "delivery_status"]
