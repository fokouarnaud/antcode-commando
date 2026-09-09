"""Seeds the normalized relational schema (customers, addresses, products,
orders) with realistic Cameroonian e-commerce transaction logs, inserted
directly through the polymorphic get_connection()/format_query() layers --
no intermediate raw import table, no ETL step.

Three separate, non-overlapping phases -- each pool is fully populated
before the next reads from it:
1. Reference data: products and a fixed, unique pool of logistics addresses
   (one row per NEIGHBORHOOD_CITY neighborhood/city pair). Neither is owned
   by a customer or an order; both are shared catalogs.
2. A pool of distinct customers (no address of their own -- see
   app/services/orders.py::_get_or_create_address's docstring for why
   orders' delivery addresses are a separate, shared concept from a
   customer's own registered address in app/services/customers.py).
3. Orders: each one picks an *existing* customer_id, address_id, and
   product_id at random from the pools above. Customers place multiple
   orders and share canonical delivery addresses -- exactly the realistic
   access pattern this schema models -- with no new customer/address rows
   minted per order.
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
from app.services.orders import (  # noqa: E402
    _get_or_create_address,
    _get_or_create_product,
    generate_next_order_id,
)

DB_PATH = pathlib.Path(
    os.environ.get("DATABASE_PATH", str(REPO_ROOT / "data" / "ecommerce.db"))
)

CUSTOMER_COUNT = 100
ORDER_COUNT = 500

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

# Tables in child-before-parent order, so DROP never trips a FK RESTRICT.
_TABLES_CHILD_FIRST = ("payments", "orders", "customers", "addresses", "products")


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


def insert_products(conn):
    """Get-or-creates every catalog product, returning their ids."""
    product_ids = []
    for name, category, unit_price_fcfa in PRODUCTS:
        product_id, _ = _get_or_create_product(conn, name, category, unit_price_fcfa)
        product_ids.append(product_id)
    conn.commit()
    return product_ids


def insert_reference_addresses(conn):
    """Get-or-creates exactly one shared address per NEIGHBORHOOD_CITY
    entry -- the fixed logistics reference pool every order picks from.
    """
    address_ids = []
    for neighborhood, city in NEIGHBORHOOD_CITY.items():
        address_ids.append(_get_or_create_address(conn, neighborhood, city))
    conn.commit()
    return address_ids


def insert_customers(conn, count, seed_value):
    """Inserts `count` brand-new, distinct customers. No address of their
    own is assigned here -- customers and addresses are independent pools
    until an order links a specific pair together.
    """
    customer_ids = []
    for full_name, phone_number in build_customer_pool(count, seed=seed_value):
        cursor = conn.execute(
            format_query("INSERT INTO customers (full_name, phone_number) VALUES (?, ?)"),
            (full_name, phone_number),
        )
        customer_ids.append(get_last_row_id(cursor, "customers", "customer_id"))
    conn.commit()
    return customer_ids


def insert_orders(conn, customer_ids, address_ids, product_ids, count, seed_value):
    """Creates `count` orders, each referencing a randomly chosen existing
    customer_id/address_id/product_id -- never a newly minted one.
    """
    rng = random.Random(seed_value)
    created = 0
    for _ in range(count):
        customer_id = rng.choice(customer_ids)
        address_id = rng.choice(address_ids)
        product_id = rng.choice(product_ids)
        unit_price_fcfa = conn.execute(
            format_query("SELECT unit_price_fcfa FROM products WHERE product_id = ?"),
            (product_id,),
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
        created += 1

    conn.commit()
    return created


def seed(conn, order_count=ORDER_COUNT, customer_count=CUSTOMER_COUNT, seed_value=42):
    product_ids = insert_products(conn)
    address_ids = insert_reference_addresses(conn)
    customer_ids = insert_customers(conn, customer_count, seed_value)
    orders_created = insert_orders(
        conn, customer_ids, address_ids, product_ids, order_count, seed_value
    )

    return {
        "products": len(product_ids),
        "addresses": len(address_ids),
        "customers": len(customer_ids),
        "orders": orders_created,
    }


def reset_database(conn):
    """Drops every table (child-before-parent, so no FK RESTRICT trips)
    and recreates the schema from scratch via init_db() -- a pristine
    slate before each seeding run, regardless of what the database
    previously held.
    """
    for table in _TABLES_CHILD_FIRST:
        conn.execute(format_query(f"DROP TABLE IF EXISTS {table}"))
    conn.commit()
    init_db(conn)


def main():
    conn = get_connection(str(DB_PATH))
    reset_database(conn)
    result = seed(conn)
    conn.close()
    print(f"Seeded {DB_PATH} with Cameroonian volume logs: {result}")


if __name__ == "__main__":
    main()
