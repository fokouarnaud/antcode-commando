"""Transforms ecommerce_orders_raw into the 6 normalized tables.

The raw table is a flat logistics export with no real customer or product
identity (no name/phone, no SKU) -- only a neighborhood, a product category,
and a per-row price. This pipeline treats each valid raw row as one order
from one synthetic customer (deterministically derived from the raw
order_id, since that's the only stable identity the source data offers),
dedupes products by category, and maps known Douala/Yaounde neighborhoods
to their city so addresses.city can stay NOT NULL and correct.
"""

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


def _get_or_create_customer(conn, external_ref):
    row = conn.execute(
        "SELECT customer_id FROM customers WHERE full_name = ?",
        (f"Customer {external_ref}",),
    ).fetchone()
    if row:
        return row["customer_id"], False
    cursor = conn.execute(
        "INSERT INTO customers (full_name, phone_number) VALUES (?, ?)",
        (f"Customer {external_ref}", f"+237-SYN-{external_ref}"),
    )
    return cursor.lastrowid, True


def _get_or_create_address(conn, customer_id, neighborhood):
    row = conn.execute(
        "SELECT address_id FROM addresses WHERE customer_id = ? AND neighborhood = ?",
        (customer_id, neighborhood),
    ).fetchone()
    if row:
        return row["address_id"], False
    city = NEIGHBORHOOD_CITY.get(neighborhood, DEFAULT_CITY)
    cursor = conn.execute(
        "INSERT INTO addresses (customer_id, neighborhood, city) VALUES (?, ?, ?)",
        (customer_id, neighborhood, city),
    )
    return cursor.lastrowid, True


def _get_or_create_product(conn, category, unit_price_fcfa):
    row = conn.execute(
        "SELECT product_id FROM products WHERE name = ?",
        (category,),
    ).fetchone()
    if row:
        return row["product_id"], False
    cursor = conn.execute(
        "INSERT INTO products (name, category, unit_price_fcfa) VALUES (?, ?, ?)",
        (category, category, int(unit_price_fcfa)),
    )
    return cursor.lastrowid, True


def load_structured_data(conn):
    counts = {
        "customers": 0,
        "addresses": 0,
        "products": 0,
        "orders": 0,
        "order_items": 0,
        "skipped": 0,
    }

    rows = conn.execute("SELECT * FROM ecommerce_orders_raw").fetchall()
    seen_external_refs = set()

    for row in rows:
        row = dict(row)
        external_ref = row.get("order_id")

        if not _is_valid_row(row) or external_ref in seen_external_refs:
            counts["skipped"] += 1
            continue
        seen_external_refs.add(external_ref)

        existing = conn.execute(
            "SELECT order_id FROM orders WHERE external_ref = ?",
            (external_ref,),
        ).fetchone()
        if existing:
            counts["skipped"] += 1
            continue

        neighborhood = normalize_neighborhood(row["customer_neighborhood"])
        delivery_status = normalize_neighborhood(row.get("delivery_status")) or "Pending"
        payment_status = normalize_neighborhood(row.get("payment_status")) or "Pending"

        customer_id, created = _get_or_create_customer(conn, external_ref)
        counts["customers"] += created

        address_id, created = _get_or_create_address(conn, customer_id, neighborhood)
        counts["addresses"] += created

        product_id, created = _get_or_create_product(
            conn, row["product_category"], row["unit_price_fcfa"]
        )
        counts["products"] += created

        cursor = conn.execute(
            "INSERT INTO orders ("
            "customer_id, address_id, customer_neighborhood, delivery_status, "
            "payment_status, external_ref"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (customer_id, address_id, neighborhood, delivery_status, payment_status, external_ref),
        )
        order_id = cursor.lastrowid
        counts["orders"] += 1

        conn.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price_fcfa) "
            "VALUES (?, ?, ?, ?)",
            (order_id, product_id, int(row["quantity"]), int(row["unit_price_fcfa"])),
        )
        counts["order_items"] += 1

    conn.commit()
    return counts
