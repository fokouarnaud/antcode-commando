"""Transforms ecommerce_orders_raw into the 6 normalized tables.

The raw table is a flat logistics export with no real customer or product
identity (no name/phone, no SKU) -- only a neighborhood, a product category,
and a per-row price. This pipeline treats each valid raw row as one order
from one synthetic customer (deterministically derived from the raw
order_id, since that's the only stable identity the source data offers),
dedupes products by category, and maps known Douala/Yaounde neighborhoods
to their city so addresses.city can stay NOT NULL and correct.
"""

from app.config.database import format_query, get_last_row_id

NEIGHBORHOOD_CITY = {
    "Akwa": "Douala",
    "Bonapriso": "Douala",
    "Bonamoussadi": "Douala",
    "Deido": "Douala",
    "New Bell": "Douala",
    "Bastos": "Yaounde",
    "Mendong": "Yaounde",
    "Nlongkak": "Yaounde",
    "Biyem-Assi": "Yaounde",
    "Ngousso": "Yaounde",
}
DEFAULT_CITY = "Douala"


def _canon_key(value):
    return value.replace("-", "").replace(" ", "").lower()


_CANONICAL_NEIGHBORHOODS = {_canon_key(name): name for name in NEIGHBORHOOD_CITY}


def normalize_neighborhood(value):
    """Title-cases and, for known Douala/Yaounde neighborhoods, also collapses
    hyphen/space spelling variants (e.g. "Biyem Assi" vs "Biyem-Assi") onto one
    canonical name -- otherwise the two spellings would count as different
    neighborhoods for indexing and dedup purposes.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    canonical = _CANONICAL_NEIGHBORHOODS.get(_canon_key(stripped))
    return canonical or stripped.title()


def _is_valid_row(row):
    if not row.get("order_id"):
        return False
    if normalize_neighborhood(row.get("customer_neighborhood")) is None:
        return False
    quantity = row.get("quantity")
    if quantity is None or quantity <= 0:
        return False
    price = row.get("unit_price_fcfa")
    if price is None or price <= 0:
        return False
    return True


def _get_or_create_customer(conn, order_id):
    row = conn.execute(
        format_query("SELECT customer_id FROM customers WHERE full_name = ?"),
        (f"Customer {order_id}",),
    ).fetchone()
    if row:
        return row["customer_id"], False
    cursor = conn.execute(
        format_query("INSERT INTO customers (full_name, phone_number) VALUES (?, ?)"),
        (f"Customer {order_id}", f"+237-SYN-{order_id}"),
    )
    return get_last_row_id(cursor, "customers", "customer_id"), True


def _get_or_create_address(conn, customer_id, neighborhood):
    row = conn.execute(
        format_query("SELECT address_id FROM addresses WHERE customer_id = ? AND neighborhood = ?"),
        (customer_id, neighborhood),
    ).fetchone()
    if row:
        return row["address_id"], False
    city = NEIGHBORHOOD_CITY.get(neighborhood, DEFAULT_CITY)
    cursor = conn.execute(
        format_query("INSERT INTO addresses (customer_id, neighborhood, city) VALUES (?, ?, ?)"),
        (customer_id, neighborhood, city),
    )
    return get_last_row_id(cursor, "addresses", "address_id"), True


def _get_or_create_product(conn, category, unit_price_fcfa):
    row = conn.execute(
        format_query("SELECT product_id FROM products WHERE name = ?"),
        (category,),
    ).fetchone()
    if row:
        return row["product_id"], False
    cursor = conn.execute(
        format_query("INSERT INTO products (name, category, unit_price_fcfa) VALUES (?, ?, ?)"),
        (category, category, int(unit_price_fcfa)),
    )
    return get_last_row_id(cursor, "products", "product_id"), True


def load_structured_data(conn):
    counts = {
        "customers": 0,
        "addresses": 0,
        "products": 0,
        "orders": 0,
        "order_items": 0,
        "skipped": 0,
    }

    rows = conn.execute(format_query("SELECT * FROM ecommerce_orders_raw")).fetchall()
    seen_order_ids = set()

    for row in rows:
        row = dict(row)
        order_id = row.get("order_id")

        if not _is_valid_row(row) or order_id in seen_order_ids:
            counts["skipped"] += 1
            continue
        seen_order_ids.add(order_id)

        existing = conn.execute(
            format_query("SELECT order_id FROM orders WHERE order_id = ?"),
            (order_id,),
        ).fetchone()
        if existing:
            counts["skipped"] += 1
            continue

        neighborhood = normalize_neighborhood(row["customer_neighborhood"])
        delivery_status = normalize_neighborhood(row.get("delivery_status")) or "Pending"
        payment_status = normalize_neighborhood(row.get("payment_status")) or "Pending"

        customer_id, created = _get_or_create_customer(conn, order_id)
        counts["customers"] += created

        address_id, created = _get_or_create_address(conn, customer_id, neighborhood)
        counts["addresses"] += created

        product_id, created = _get_or_create_product(
            conn, row["product_category"], row["unit_price_fcfa"]
        )
        counts["products"] += created

        conn.execute(
            format_query(
                "INSERT INTO orders ("
                "order_id, customer_id, address_id, customer_neighborhood, delivery_status, "
                "payment_status"
                ") VALUES (?, ?, ?, ?, ?, ?)"
            ),
            (order_id, customer_id, address_id, neighborhood, delivery_status, payment_status),
        )
        counts["orders"] += 1

        conn.execute(
            format_query(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price_fcfa) "
                "VALUES (?, ?, ?, ?)"
            ),
            (order_id, product_id, int(row["quantity"]), int(row["unit_price_fcfa"])),
        )
        counts["order_items"] += 1

    conn.commit()
    return counts
