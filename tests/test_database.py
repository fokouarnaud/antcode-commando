import sys
import sqlite3
import types

import pytest

from app.config.database import format_query, get_connection, get_engine, get_last_row_id, init_db


def test_get_connection_returns_usable_sqlite_connection():
    conn = get_connection(":memory:")

    row = conn.execute("SELECT 1 AS result").fetchone()

    assert row["result"] == 1


def test_init_db_creates_all_five_tables():
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


def test_init_db_creates_orders_address_id_index():
    """orders.address_id has no automatic index just for being a FOREIGN
    KEY -- without one, filtering orders by their address's neighborhood
    (a JOIN on address_id) forces a full table scan of orders instead of
    seeking via idx_addresses_neighborhood_city then probing orders.
    """
    conn = get_connection(":memory:")

    init_db(conn)

    index_columns = [
        row["name"]
        for row in conn.execute("PRAGMA index_info(idx_orders_address_id)").fetchall()
    ]
    assert index_columns == ["address_id"]


def test_orders_table_has_product_and_delivery_status_columns():
    conn = get_connection(":memory:")

    init_db(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}
    assert {"order_id", "product_id", "quantity", "delivery_status"} <= columns


def test_init_db_creates_orders_delivery_status_index():
    conn = get_connection(":memory:")

    init_db(conn)

    index_columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA index_info(idx_orders_delivery_status)"
        ).fetchall()
    ]
    assert index_columns == ["delivery_status"]


def test_get_engine_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DB_ENGINE", raising=False)

    assert get_engine() == "sqlite"


def test_get_engine_reads_db_engine_env_var(monkeypatch):
    monkeypatch.setenv("DB_ENGINE", "postgresql")

    assert get_engine() == "postgresql"


def test_format_query_leaves_placeholders_unchanged_for_sqlite(monkeypatch):
    monkeypatch.delenv("DB_ENGINE", raising=False)

    assert format_query("SELECT * FROM orders WHERE order_id = ?") == (
        "SELECT * FROM orders WHERE order_id = ?"
    )


def test_format_query_converts_placeholders_for_postgres(monkeypatch):
    monkeypatch.setenv("DB_ENGINE", "postgresql")

    assert format_query("SELECT * FROM orders WHERE order_id = ? AND status = ?") == (
        "SELECT * FROM orders WHERE order_id = %s AND status = %s"
    )


def test_get_connection_uses_psycopg2_for_postgresql_engine(monkeypatch):
    monkeypatch.setenv("DB_ENGINE", "postgresql")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/dbname")

    calls = []
    fake_connection = object()
    fake_psycopg2 = types.SimpleNamespace(
        connect=lambda dsn: calls.append(dsn) or fake_connection
    )
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)

    result = get_connection("ignored-for-postgres.db")

    assert calls == ["postgresql://user:pw@host/dbname"]
    assert result is fake_connection


def test_get_last_row_id_returns_cursor_lastrowid_for_sqlite(monkeypatch):
    monkeypatch.delenv("DB_ENGINE", raising=False)
    conn = get_connection(":memory:")
    init_db(conn)
    cursor = conn.execute(
        "INSERT INTO customers (full_name, phone_number) VALUES (?, ?)",
        ("Amina Njoya", "+237690000001"),
    )

    assert get_last_row_id(cursor, "customers", "customer_id") == cursor.lastrowid


def test_get_last_row_id_queries_currval_for_postgresql(monkeypatch):
    monkeypatch.setenv("DB_ENGINE", "postgresql")

    class FakeCursor:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))

        def fetchone(self):
            return (42,)

    cursor = FakeCursor()

    result = get_last_row_id(cursor, "customers", "customer_id")

    assert result == 42
    assert len(cursor.calls) == 1
    sql, params = cursor.calls[0]
    assert "pg_get_serial_sequence" in sql
    assert params == ("customers", "customer_id")
