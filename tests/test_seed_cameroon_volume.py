import re

from app.config.database import get_connection, init_db
from scripts.seed_cameroon_volume import (
    NEIGHBORHOOD_CITY,
    PRODUCTS,
    build_customer_pool,
    insert_customers,
    insert_orders,
    insert_products,
    insert_reference_addresses,
    reset_database,
    seed,
)

_PHONE_PATTERN = re.compile(r"^\+2376\d{8}$")


def _seeded_conn(tmp_path):
    conn = get_connection(str(tmp_path / "seed-test.db"))
    init_db(conn)
    return conn


def test_build_customer_pool_returns_n_unique_phones():
    pool = build_customer_pool(500, seed=1)

    phones = [phone for _, phone in pool]
    assert len(pool) == 500
    assert len(set(phones)) == 500
    assert all(_PHONE_PATTERN.match(phone) for phone in phones)


def test_seed_creates_fixed_reference_pools_and_500_orders(tmp_path):
    conn = _seeded_conn(tmp_path)

    result = seed(conn, order_count=500, customer_count=100)

    assert result == {
        "products": len(PRODUCTS),
        "addresses": len(NEIGHBORHOOD_CITY),
        "customers": 100,
        "orders": 500,
    }
    assert conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == len(PRODUCTS)
    assert conn.execute("SELECT COUNT(*) AS n FROM addresses").fetchone()["n"] == len(NEIGHBORHOOD_CITY)
    assert conn.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"] == 100
    assert conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 500


def test_insert_reference_addresses_creates_exactly_one_row_per_neighborhood(tmp_path):
    conn = _seeded_conn(tmp_path)

    address_ids = insert_reference_addresses(conn)

    assert len(address_ids) == len(NEIGHBORHOOD_CITY)
    rows = conn.execute("SELECT neighborhood, city, customer_id FROM addresses").fetchall()
    assert {row["neighborhood"] for row in rows} == set(NEIGHBORHOOD_CITY)
    for row in rows:
        assert row["city"] == NEIGHBORHOOD_CITY[row["neighborhood"]]
        # Reference addresses are a shared logistics pool, owned by no customer.
        assert row["customer_id"] is None


def test_insert_reference_addresses_is_idempotent(tmp_path):
    """Calling it twice must not create duplicate rows -- get-or-create
    keyed on (neighborhood, city), not a fresh insert every call.
    """
    conn = _seeded_conn(tmp_path)

    first = insert_reference_addresses(conn)
    second = insert_reference_addresses(conn)

    assert sorted(first) == sorted(second)
    assert conn.execute("SELECT COUNT(*) AS n FROM addresses").fetchone()["n"] == len(NEIGHBORHOOD_CITY)


def test_insert_products_is_idempotent(tmp_path):
    conn = _seeded_conn(tmp_path)

    first = insert_products(conn)
    second = insert_products(conn)

    assert sorted(first) == sorted(second)
    assert conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == len(PRODUCTS)


def test_insert_customers_creates_distinct_unique_phone_customers(tmp_path):
    conn = _seeded_conn(tmp_path)

    customer_ids = insert_customers(conn, 50, seed_value=7)

    assert len(customer_ids) == 50
    assert len(set(customer_ids)) == 50
    phones = [row["phone_number"] for row in conn.execute("SELECT phone_number FROM customers")]
    assert len(phones) == len(set(phones))
    assert all(_PHONE_PATTERN.match(phone) for phone in phones)


def test_orders_reuse_existing_customers_and_addresses_without_creating_duplicates(tmp_path):
    """The core reusability property: generating orders must never mint a
    new customer or address row -- only pick from the pre-populated pools.
    """
    conn = _seeded_conn(tmp_path)
    product_ids = insert_products(conn)
    address_ids = insert_reference_addresses(conn)
    customer_ids = insert_customers(conn, 10, seed_value=3)

    created = insert_orders(conn, customer_ids, address_ids, product_ids, count=500, seed_value=3)

    assert created == 500
    assert conn.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"] == 10
    assert conn.execute("SELECT COUNT(*) AS n FROM addresses").fetchone()["n"] == len(NEIGHBORHOOD_CITY)
    assert conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 500

    order_customer_ids = {
        row["customer_id"] for row in conn.execute("SELECT DISTINCT customer_id FROM orders")
    }
    order_address_ids = {
        row["address_id"] for row in conn.execute("SELECT DISTINCT address_id FROM orders")
    }
    assert order_customer_ids <= set(customer_ids)
    assert order_address_ids <= set(address_ids)
    # With 500 orders spread across only 10 customers, reuse is forced --
    # every seeded customer places multiple orders.
    assert order_customer_ids == set(customer_ids)


def test_seed_orders_have_valid_tracking_states_and_unique_order_ids(tmp_path):
    conn = _seeded_conn(tmp_path)

    seed(conn, order_count=200, customer_count=20)

    rows = conn.execute("SELECT order_id, delivery_status FROM orders").fetchall()
    order_ids = [row["order_id"] for row in rows]
    assert len(order_ids) == len(set(order_ids))
    assert all(order_id.startswith("ECM-") for order_id in order_ids)
    assert all(row["delivery_status"] in {"Pending", "Shipped", "Delivered"} for row in rows)


def test_seed_products_span_expected_categories(tmp_path):
    conn = _seeded_conn(tmp_path)

    seed(conn, order_count=10, customer_count=5)

    categories = {row["category"] for row in conn.execute("SELECT DISTINCT category FROM products")}
    assert categories == {"Electronics", "Phones", "Fashion"}


def test_reset_database_wipes_prior_data_before_reseeding(tmp_path):
    conn = _seeded_conn(tmp_path)
    seed(conn, order_count=50, customer_count=10)
    assert conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 50

    reset_database(conn)

    assert conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM addresses").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 0

    result = seed(conn, order_count=50, customer_count=10)

    assert result["orders"] == 50
    assert result["customers"] == 10
    assert conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 50
