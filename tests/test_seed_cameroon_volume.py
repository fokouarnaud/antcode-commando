import re

from app.config.database import get_connection, init_db
from scripts.seed_cameroon_volume import NEIGHBORHOOD_CITY, PRODUCTS, build_customer_pool, seed

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


def test_seed_inserts_exactly_500_customers_addresses_and_orders(tmp_path):
    conn = _seeded_conn(tmp_path)

    result = seed(conn, count=500)

    assert result["customers"] == 500
    assert result["addresses"] == 500
    assert result["orders"] == 500
    assert result["products"] == len(PRODUCTS)

    for table in ("customers", "addresses", "orders"):
        count = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        assert count == 500


def test_seed_products_span_expected_categories(tmp_path):
    conn = _seeded_conn(tmp_path)

    seed(conn, count=10)

    categories = {row["category"] for row in conn.execute("SELECT DISTINCT category FROM products")}
    assert categories == {"Electronics", "Phones", "Fashion"}


def test_seed_customers_have_valid_unique_cameroonian_phone_numbers(tmp_path):
    conn = _seeded_conn(tmp_path)

    seed(conn, count=200)

    phones = [row["phone_number"] for row in conn.execute("SELECT phone_number FROM customers")]
    assert len(phones) == len(set(phones))
    assert all(_PHONE_PATTERN.match(phone) for phone in phones)


def test_seed_addresses_use_known_neighborhoods_and_correct_cities(tmp_path):
    conn = _seeded_conn(tmp_path)

    seed(conn, count=200)

    rows = conn.execute("SELECT neighborhood, city FROM addresses").fetchall()
    assert len(rows) == 200
    for row in rows:
        assert row["neighborhood"] in NEIGHBORHOOD_CITY
        assert row["city"] == NEIGHBORHOOD_CITY[row["neighborhood"]]


def test_seed_orders_have_valid_tracking_states_and_unique_order_ids(tmp_path):
    conn = _seeded_conn(tmp_path)

    seed(conn, count=200)

    rows = conn.execute("SELECT order_id, delivery_status FROM orders").fetchall()
    order_ids = [row["order_id"] for row in rows]
    assert len(order_ids) == len(set(order_ids))
    assert all(order_id.startswith("ECM-") for order_id in order_ids)
    assert all(row["delivery_status"] in {"Pending", "Shipped", "Delivered"} for row in rows)


def test_seed_continues_order_id_sequence_when_orders_already_exist(tmp_path):
    conn = _seeded_conn(tmp_path)
    conn.execute(
        "INSERT INTO customers (full_name, phone_number) VALUES ('Existing', '+237690000099')"
    )
    conn.execute("INSERT INTO addresses (customer_id, neighborhood, city) VALUES (1, 'Akwa', 'Douala')")
    conn.execute(
        "INSERT INTO products (name, category, unit_price_fcfa) VALUES ('Existing Product', 'Electronics', 1000)"
    )
    conn.execute(
        "INSERT INTO orders (order_id, customer_id, address_id, product_id, quantity, unit_price_fcfa) "
        "VALUES ('ECM-00007', 1, 1, 1, 1, 1000)"
    )
    conn.commit()

    seed(conn, count=5)

    order_ids = sorted(row["order_id"] for row in conn.execute("SELECT order_id FROM orders"))
    assert order_ids[0] == "ECM-00007"
    assert order_ids[-1] == "ECM-00012"
