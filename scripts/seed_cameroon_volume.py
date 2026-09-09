"""Seeds the normalized relational schema (customers, addresses, products,
orders) with 500 realistic Cameroonian e-commerce transaction logs, inserted
directly through the polymorphic get_connection()/format_query() layers --
no intermediate raw import table, no ETL step.

Insertion order matters for referential integrity: products first (orders
reference product_id), then customers, then their addresses (orders
reference both), then orders themselves.
"""

import os
import pathlib
import random
import sys

REPO_ROOT = pathlib.Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.config.database import format_query, get_connection, get_last_row_id, init_db  # noqa: E402
from app.services.orders import _get_or_create_product, generate_next_order_id  # noqa: E402

DB_PATH = pathlib.Path(
    os.environ.get("DATABASE_PATH", str(REPO_ROOT / "data" / "ecommerce.db"))
)

SEED_COUNT = 500

PRODUCTS = [
    ("Smartphone Tecno Spark", "Electronics", 95000),
    ("Samsung Galaxy A15", "Phones", 145000),
    ("Infinix Hot 40", "Phones", 89000),
    ("Bluetooth Earbuds", "Electronics", 15000),
    ("LED Television 32-inch", "Electronics", 120000),
    ("Wax Print Fabric (6 yards)", "Fashion", 25000),
    ("Men's Sneakers", "Fashion", 30000),
    ("Women's Handbag", "Fashion", 18000),
    ("Power Bank 20000mAh", "Electronics", 12000),
    ("Kids School Backpack", "Fashion", 9000),
]

FIRST_NAMES = [
    "Jean", "Marie", "Paul", "Aminatou", "Blaise", "Solange", "Yannick",
    "Carine", "Achille", "Brenda", "Cedric", "Larissa", "Steve", "Divine",
    "Arnaud", "Vanessa", "Serge", "Nadege", "Franck", "Aurelie", "Patrick",
    "Chantal", "Herve", "Sandrine", "Christian", "Pauline", "Junior", "Grace",
]
LAST_NAMES = [
    "Njoya", "Foka", "Mballa", "Ekwalla", "Fotso", "Ngassa", "Tchoumi",
    "Kamga", "Mvondo", "Biya", "Talla", "Ateba", "Nkodo", "Wandji", "Essomba",
    "Nguema", "Kenfack", "Owona", "Simo", "Amougou",
]

NEIGHBORHOOD_CITY = {
    "Akwa": "Douala",
    "Bonapriso": "Douala",
    "Bastos": "Yaounde",
    "Mendong": "Yaounde",
    "Biyem-Assi": "Yaounde",
}

DELIVERY_STATUSES = ["Pending", "Shipped", "Delivered"]


def build_customer_pool(n, seed=None):
    """Generates n distinct (full_name, phone_number) pairs. phone_number
    follows the +2376XXXXXXXX Cameroonian mobile format and is guaranteed
    unique within the returned pool.
    """
    rng = random.Random(seed)
    seen_phones = set()
    pool = []
    while len(pool) < n:
        phone = f"+2376{rng.randint(0, 99999999):08d}"
        if phone in seen_phones:
            continue
        seen_phones.add(phone)
        full_name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        pool.append((full_name, phone))
    return pool


def seed(conn, count=SEED_COUNT, seed_value=42):
    rng = random.Random(seed_value)
    counts = {"products": 0, "customers": 0, "addresses": 0, "orders": 0}

    product_ids = []
    for name, category, unit_price_fcfa in PRODUCTS:
        product_id, _ = _get_or_create_product(conn, name, category, unit_price_fcfa)
        product_ids.append(product_id)
        counts["products"] += 1

    customer_pool = build_customer_pool(count, seed=seed_value)

    for full_name, phone_number in customer_pool:
        cursor = conn.execute(
            format_query("INSERT INTO customers (full_name, phone_number) VALUES (?, ?)"),
            (full_name, phone_number),
        )
        customer_id = get_last_row_id(cursor, "customers", "customer_id")
        counts["customers"] += 1

        neighborhood = rng.choice(list(NEIGHBORHOOD_CITY))
        city = NEIGHBORHOOD_CITY[neighborhood]
        cursor = conn.execute(
            format_query("INSERT INTO addresses (customer_id, neighborhood, city) VALUES (?, ?, ?)"),
            (customer_id, neighborhood, city),
        )
        address_id = get_last_row_id(cursor, "addresses", "address_id")
        counts["addresses"] += 1

        product_id = rng.choice(product_ids)
        unit_price_fcfa = conn.execute(
            format_query("SELECT unit_price_fcfa FROM products WHERE product_id = ?"), (product_id,)
        ).fetchone()["unit_price_fcfa"]
        quantity = rng.randint(1, 5)
        delivery_status = rng.choice(DELIVERY_STATUSES)
        order_id = generate_next_order_id(conn)

        conn.execute(
            format_query(
                "INSERT INTO orders (order_id, customer_id, address_id, product_id, quantity, "
                "unit_price_fcfa, delivery_status) VALUES (?, ?, ?, ?, ?, ?, ?)"
            ),
            (order_id, customer_id, address_id, product_id, quantity, unit_price_fcfa, delivery_status),
        )
        counts["orders"] += 1

    conn.commit()
    return counts


def main():
    conn = get_connection(str(DB_PATH))
    existing_tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "orders" not in existing_tables:
        init_db(conn)

    result = seed(conn, SEED_COUNT)
    conn.close()
    print(f"Seeded {DB_PATH} with Cameroonian volume logs: {result}")


if __name__ == "__main__":
    main()
