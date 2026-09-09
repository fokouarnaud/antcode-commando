from app.config.database import get_connection
from scripts.generate_mock_transactions import (
    clean_row,
    ensure_import_table,
    insert_orders,
)


def test_clean_row_strips_whitespace_and_converts_nan_to_none():
    dirty = {
        "customer_neighborhood": "  Bonapriso  ",
        "quantity": float("nan"),
        "payment_status": "Paid",
    }

    cleaned = clean_row(dirty)

    assert cleaned == {
        "customer_neighborhood": "Bonapriso",
        "quantity": None,
        "payment_status": "Paid",
    }


def test_insert_orders_stores_cleaned_rows_in_database():
    conn = get_connection(":memory:")
    ensure_import_table(conn)
    rows = [{
        "order_id": "ECM-00001",
        "customer_neighborhood": "  Akwa  ",
        "order_date": "2025-03-01",
        "product_category": "Electronics",
        "quantity": 2,
        "unit_price_fcfa": float("nan"),
        "payment_method": "MTN MoMo",
        "payment_status": "Paid",
        "delivery_status": "Delivered",
        "delivery_date": "2025-03-02",
        "delivery_duration_hours": 24.5,
        "driver_id": "DRV-001",
        "distance_km": 5.2,
    }]

    inserted = insert_orders(conn, rows)

    assert inserted == 1
    row = conn.execute(
        "SELECT customer_neighborhood, unit_price_fcfa FROM ecommerce_orders_raw"
    ).fetchone()
    assert row["customer_neighborhood"] == "Akwa"
    assert row["unit_price_fcfa"] is None


def test_ensure_import_table_uses_postgres_ddl_when_engine_is_postgresql(monkeypatch):
    monkeypatch.setenv("DB_ENGINE", "postgresql")
    calls = []

    class FakeConn:
        def execute(self, sql):
            calls.append(sql)

    ensure_import_table(FakeConn())

    assert len(calls) == 1
    assert "SERIAL PRIMARY KEY" in calls[0]
    assert "AUTOINCREMENT" not in calls[0]
