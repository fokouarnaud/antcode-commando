from app.config.database import format_query, get_last_row_id

_DEFAULT_CITY = "Douala"
_ORDER_ID_PREFIX = "ECM-"

_VALID_DELIVERY_STATUSES = {"Pending", "Shipped", "Delivered"}
_VALID_PAYMENT_STATUSES = {"Paid", "Unpaid"}

_ORDER_DETAIL_COLUMNS = (
    "o.order_id, o.customer_id, o.address_id, o.product_id, o.quantity, "
    "o.unit_price_fcfa, o.delivery_status, o.payment_status, o.created_at, o.updated_at, "
    "c.full_name AS customer_name, c.phone_number AS customer_phone, "
    "a.neighborhood, a.city, p.name AS product_name"
)

_ORDER_DETAIL_JOIN = (
    "FROM orders o "
    "JOIN customers c ON c.customer_id = o.customer_id "
    "JOIN addresses a ON a.address_id = o.address_id "
    "JOIN products p ON p.product_id = o.product_id"
)


class OrderValidationError(Exception):
    pass


def _select_order_by(conn, column, value):
    return conn.execute(
        format_query(f"SELECT {_ORDER_DETAIL_COLUMNS} {_ORDER_DETAIL_JOIN} WHERE o.{column} = ?"),
        (value,),
    ).fetchone()


def get_order_by_id(conn, order_id):
    """order_id is the business identifier itself (e.g. "ECM-00795"),
    not a surrogate integer -- the schema's own PRIMARY KEY.
    """
    return _select_order_by(conn, "order_id", order_id)


def get_order_by_transaction_reference(conn, external_transaction_id):
    """Looks up an order by a payment's transaction reference (e.g. a
    GeniusPay/MoMo/Orange external_transaction_id), rather than the
    order's own order_id -- this is the identifier a payment
    confirmation actually hands back, not the order's own business id.
    external_transaction_id is only UNIQUE per (provider,
    external_transaction_id), so two different providers could in
    principle share the same string against two different orders (see
    test_momo_and_orange_callbacks_reusing_the_same_transaction_id_are_independent);
    ordering by payment_id DESC picks the most recently recorded match.
    """
    row = conn.execute(
        format_query(
            "SELECT order_id FROM payments WHERE external_transaction_id = ? "
            "ORDER BY payment_id DESC LIMIT 1"
        ),
        (external_transaction_id,),
    ).fetchone()
    if row is None:
        return None
    return get_order_by_id(conn, row["order_id"])


def get_order_checkout_details(conn, order_id):
    """Everything initiate_geniuspay_payment() needs, in one place. The
    order's own quantity/unit_price_fcfa (snapshotted at order creation)
    is the amount -- no separate line-items table to sum.
    """
    order = conn.execute(
        format_query(
            "SELECT o.order_id, o.quantity, o.unit_price_fcfa, c.full_name, c.phone_number "
            "FROM orders o JOIN customers c ON c.customer_id = o.customer_id "
            "WHERE o.order_id = ?"
        ),
        (order_id,),
    ).fetchone()
    if order is None:
        return None

    return {
        "order_id": order["order_id"],
        "customer_name": order["full_name"],
        "customer_phone": order["phone_number"],
        "amount_fcfa": order["quantity"] * order["unit_price_fcfa"],
    }


def _get_or_create_customer(conn, full_name, phone_number):
    row = conn.execute(
        format_query("SELECT customer_id FROM customers WHERE phone_number = ?"),
        (phone_number,),
    ).fetchone()
    if row:
        return row["customer_id"]
    cursor = conn.execute(
        format_query("INSERT INTO customers (full_name, phone_number) VALUES (?, ?)"),
        (full_name, phone_number),
    )
    return get_last_row_id(cursor, "customers", "customer_id")


def _get_or_create_address(conn, neighborhood, city):
    """Addresses reached through this path are shared logistics reference
    points (e.g. "Akwa, Douala"), not owned by any one customer -- keyed
    and deduped purely on (neighborhood, city) so every customer/order
    that ships to the same zone reuses the same row instead of each
    minting its own near-duplicate. (Contrast with a customer's own
    registered address in app/services/customers.py, which legitimately
    belongs to that customer.) Inserted rows get customer_id = NULL.
    """
    row = conn.execute(
        format_query("SELECT address_id FROM addresses WHERE neighborhood = ? AND city = ?"),
        (neighborhood, city),
    ).fetchone()
    if row:
        return row["address_id"]
    cursor = conn.execute(
        format_query("INSERT INTO addresses (neighborhood, city) VALUES (?, ?)"),
        (neighborhood, city),
    )
    return get_last_row_id(cursor, "addresses", "address_id")


def _get_or_create_product(conn, name, category, unit_price_fcfa):
    row = conn.execute(
        format_query("SELECT product_id, unit_price_fcfa FROM products WHERE name = ?"),
        (name,),
    ).fetchone()
    if row:
        return row["product_id"], row["unit_price_fcfa"]
    cursor = conn.execute(
        format_query("INSERT INTO products (name, category, unit_price_fcfa) VALUES (?, ?, ?)"),
        (name, category, int(unit_price_fcfa)),
    )
    return get_last_row_id(cursor, "products", "product_id"), int(unit_price_fcfa)


def generate_next_order_id(conn):
    row = conn.execute(
        format_query(
            f"SELECT order_id FROM orders WHERE order_id LIKE '{_ORDER_ID_PREFIX}%' "
            "ORDER BY order_id DESC LIMIT 1"
        )
    ).fetchone()
    next_n = 1
    if row:
        next_n = int(row["order_id"][len(_ORDER_ID_PREFIX):]) + 1
    return f"{_ORDER_ID_PREFIX}{next_n:05d}"


def create_order(conn, order):
    """Creates a single order, resolving (or creating) its customer,
    address, and product the same way sync_offline_orders() does for
    bulk offline ingestion. `order` accepts either `customer_id` or
    `customer_name`+`customer_phone`+`neighborhood`(+`city`), and either
    `product_id` or `product_name`+`category`+`unit_price_fcfa`.
    """
    if order.get("customer_id"):
        customer_id = order["customer_id"]
    else:
        customer_id = _get_or_create_customer(
            conn, order["customer_name"], order["customer_phone"]
        )

    neighborhood = order.get("neighborhood")
    if order.get("address_id"):
        address_id = order["address_id"]
    elif neighborhood:
        address_id = _get_or_create_address(
            conn, neighborhood, order.get("city", _DEFAULT_CITY)
        )
    else:
        raise OrderValidationError("missing required field: 'address_id' or 'neighborhood'")

    if order.get("product_id"):
        product_id = order["product_id"]
        unit_price_fcfa = order.get("unit_price_fcfa")
        if unit_price_fcfa is None:
            product = conn.execute(
                format_query("SELECT unit_price_fcfa FROM products WHERE product_id = ?"),
                (product_id,),
            ).fetchone()
            if product is None:
                raise OrderValidationError(f"unknown product_id: {product_id}")
            unit_price_fcfa = product["unit_price_fcfa"]
    else:
        product_id, unit_price_fcfa = _get_or_create_product(
            conn, order["product_name"], order.get("category", "General"),
            order["unit_price_fcfa"],
        )

    quantity = order.get("quantity", 1)
    if not isinstance(quantity, int) or quantity <= 0:
        raise OrderValidationError("'quantity' must be a positive integer")

    delivery_status = order.get("delivery_status", "Pending")
    if delivery_status not in _VALID_DELIVERY_STATUSES:
        raise OrderValidationError(f"invalid delivery_status: {delivery_status}")

    order_id = order.get("order_id") or generate_next_order_id(conn)

    conn.execute(
        format_query(
            "INSERT INTO orders (order_id, customer_id, address_id, product_id, quantity, "
            "unit_price_fcfa, delivery_status) VALUES (?, ?, ?, ?, ?, ?, ?)"
        ),
        (order_id, customer_id, address_id, product_id, quantity, unit_price_fcfa, delivery_status),
    )
    conn.commit()

    return get_order_by_id(conn, order_id)


def update_order_tracking(conn, order_id, delivery_status=None, payment_status=None):
    """Updates only the mutable tracking fields on an existing order.
    Returns the updated order, or None if order_id doesn't exist.
    Raises OrderValidationError for an unrecognized status value.
    """
    existing = get_order_by_id(conn, order_id)
    if existing is None:
        return None

    if delivery_status is not None and delivery_status not in _VALID_DELIVERY_STATUSES:
        raise OrderValidationError(f"invalid delivery_status: {delivery_status}")
    if payment_status is not None and payment_status not in _VALID_PAYMENT_STATUSES:
        raise OrderValidationError(f"invalid payment_status: {payment_status}")

    new_delivery_status = delivery_status or existing["delivery_status"]
    new_payment_status = payment_status or existing["payment_status"]

    conn.execute(
        format_query(
            "UPDATE orders SET delivery_status = ?, payment_status = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE order_id = ?"
        ),
        (new_delivery_status, new_payment_status, order_id),
    )
    conn.commit()

    return get_order_by_id(conn, order_id)


def delete_order(conn, order_id):
    """Deletes an order. Returns True if a row was deleted, False if
    order_id didn't exist. Lets sqlite3.IntegrityError/
    psycopg2.IntegrityError bubble up when payments still reference this
    order -- the route translates that into a 409.
    """
    cursor = conn.execute(format_query("DELETE FROM orders WHERE order_id = ?"), (order_id,))
    conn.commit()
    return cursor.rowcount > 0


def sync_offline_orders(conn, orders):
    """Bulk-ingests orders a field agent's app captured while offline, once
    connectivity returns. Idempotent on order_id (the schema's own PRIMARY
    KEY, e.g. "ECM-00795"): replaying the same batch after a blackout (e.g.
    the app retrying because it never saw the first sync's ack) skips every
    order already synced instead of double-inserting it.
    """
    synced = 0
    skipped = 0

    for order in orders:
        order_id = order["order_id"]
        existing = conn.execute(
            format_query("SELECT order_id FROM orders WHERE order_id = ?"),
            (order_id,),
        ).fetchone()
        if existing:
            skipped += 1
            continue

        neighborhood = order["neighborhood"]
        customer_id = _get_or_create_customer(conn, order["customer_name"], order["customer_phone"])
        address_id = _get_or_create_address(
            conn, neighborhood, order.get("city", _DEFAULT_CITY)
        )
        product_id, unit_price_fcfa = _get_or_create_product(
            conn,
            order["product_name"],
            order.get("category", "General"),
            order["unit_price_fcfa"],
        )

        conn.execute(
            format_query(
                "INSERT INTO orders (order_id, customer_id, address_id, product_id, quantity, "
                "unit_price_fcfa, delivery_status, payment_status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                order_id,
                customer_id,
                address_id,
                product_id,
                order.get("quantity", 1),
                unit_price_fcfa,
                order.get("delivery_status", "Pending"),
                order.get("payment_status", "Unpaid"),
            ),
        )
        synced += 1

    conn.commit()
    return {"synced": synced, "skipped": skipped}


def list_orders(conn, neighborhood=None, status=None, page=1, per_page=20):
    """Filters orders by the customer's address neighborhood and/or
    delivery_status. Returns (rows, total_records) for the requested page,
    total_records being the filtered count before LIMIT/OFFSET is applied.
    """
    join_clause = "FROM orders o JOIN addresses a ON a.address_id = o.address_id"
    where_clause = " WHERE 1=1"
    params = []
    if neighborhood:
        where_clause += " AND a.neighborhood = ?"
        params.append(neighborhood)
    if status:
        where_clause += " AND o.delivery_status = ?"
        params.append(status)

    total_records = conn.execute(
        format_query(f"SELECT COUNT(*) AS n {join_clause}{where_clause}"), params
    ).fetchone()["n"]

    query = (
        "SELECT o.order_id, o.customer_id, o.product_id, o.quantity, o.unit_price_fcfa, "
        "a.neighborhood, a.city, o.delivery_status, o.payment_status "
        f"{join_clause}{where_clause} ORDER BY o.order_id LIMIT ? OFFSET ?"
    )
    offset = (page - 1) * per_page
    rows = conn.execute(format_query(query), params + [per_page, offset]).fetchall()

    return rows, total_records
