import sqlite3

import pytest

from app.config.database import get_connection, init_db
from app.services.pipeline import load_structured_data, normalize_neighborhood
from scripts.generate_mock_transactions import ensure_import_table, insert_orders


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  akwa  ", "Akwa"),
        ("BONAPRISO", "Bonapriso"),
        ("new bell", "New Bell"),
        ("biyem-assi", "Biyem-Assi"),
        ("MENDONG", "Mendong"),
    ],
)
def test_normalize_neighborhood_capitalizes_names(raw, expected):
    assert normalize_neighborhood(raw) == expected


def test_normalize_neighborhood_returns_none_for_blank_input():
    assert normalize_neighborhood(None) is None
    assert normalize_neighborhood("   ") is None


def test_normalize_neighborhood_collapses_hyphen_space_variant_to_canonical_name():
    assert normalize_neighborhood("Biyem Assi") == "Biyem-Assi"
    assert normalize_neighborhood("biyem assi") == "Biyem-Assi"
    assert normalize_neighborhood("BIYEM-ASSI") == "Biyem-Assi"


def raw_row(**overrides):
    row = {
        "order_id": "ECM-00001",
        "customer_neighborhood": "akwa",
        "order_date": "2025-03-01",
        "product_category": "Electronics",
        "quantity": 2,
        "unit_price_fcfa": 15000,
        "payment_method": "MTN MoMo",
        "payment_status": "paid",
        "delivery_status": "delivered",
        "delivery_date": "2025-03-02",
        "delivery_duration_hours": 24.5,
        "driver_id": "DRV-001",
        "distance_km": 5.2,
    }
    row.update(overrides)
    return row


def make_conn_with_raw_rows(rows):
    conn = get_connection(":memory:")
    init_db(conn)
    ensure_import_table(conn)
    insert_orders(conn, rows)
    return conn


def test_load_structured_data_creates_customer_address_product_and_order():
    conn = make_conn_with_raw_rows([raw_row()])

    result = load_structured_data(conn)

    assert result == {
        "customers": 1,
        "addresses": 1,
        "products": 1,
        "orders": 1,
        "order_items": 1,
        "skipped": 0,
    }

    order = conn.execute(
        "SELECT customer_neighborhood, delivery_status, payment_status, external_ref "
        "FROM orders"
    ).fetchone()
    assert order["customer_neighborhood"] == "Akwa"
    assert order["delivery_status"] == "Delivered"
    assert order["payment_status"] == "Paid"
    assert order["external_ref"] == "ECM-00001"

    address = conn.execute("SELECT neighborhood, city FROM addresses").fetchone()
    assert address["neighborhood"] == "Akwa"
    assert address["city"] == "Douala"


def test_load_structured_data_dedupes_products_by_category():
    conn = make_conn_with_raw_rows([
        raw_row(order_id="ECM-00001", product_category="Electronics"),
        raw_row(order_id="ECM-00002", product_category="Electronics"),
    ])

    result = load_structured_data(conn)

    assert result["products"] == 1
    assert result["orders"] == 2
    assert result["order_items"] == 2


def test_load_structured_data_skips_rows_with_invalid_quantity_or_price():
    conn = make_conn_with_raw_rows([
        raw_row(order_id="ECM-00001", quantity=-3),
        raw_row(order_id="ECM-00002", unit_price_fcfa=None),
        raw_row(order_id="ECM-00003", customer_neighborhood=None),
    ])

    result = load_structured_data(conn)

    assert result["orders"] == 0
    assert result["skipped"] == 3


def test_load_structured_data_deduplicates_repeated_raw_order_ids():
    conn = make_conn_with_raw_rows([
        raw_row(order_id="ECM-00001"),
        raw_row(order_id="ECM-00001"),
    ])

    result = load_structured_data(conn)

    assert result["orders"] == 1
    assert result["skipped"] == 1


def test_load_structured_data_is_idempotent_across_reruns():
    conn = make_conn_with_raw_rows([raw_row(order_id="ECM-00001")])
    load_structured_data(conn)

    second_run = load_structured_data(conn)

    assert second_run["orders"] == 0
    total_orders = conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"]
    assert total_orders == 1
