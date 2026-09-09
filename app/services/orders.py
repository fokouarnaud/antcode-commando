from app.config.database import format_query, get_last_row_id

_DEFAULT_CITY = "Douala"

_ORDER_DETAIL_COLUMNS = (
    "order_id, customer_id, address_id, customer_neighborhood, delivery_status, "
    "payment_status, external_ref, created_at, updated_at"
)


def _select_order_by(conn, column, value):
    return conn.execute(
        format_query(f"SELECT {_ORDER_DETAIL_COLUMNS} FROM orders WHERE {column} = ?"),
        (value,),
    ).fetchone()


def get_order_by_id(conn, order_id):
    return _select_order_by(conn, "order_id", order_id)


def get_order_by_external_ref(conn, external_ref):
    """Looks up an order by its human-facing sequential reference (e.g.
    "ECM-00001") -- the same UNIQUE `external_ref` column list_orders()
    already surfaces, just resolved as the sole lookup key here.
    """
    return _select_order_by(conn, "external_ref", external_ref)


def get_order_by_transaction_reference(conn, external_transaction_id):
    """Looks up an order by a payment's transaction reference (e.g. a
    GeniusPay/MoMo/Orange external_transaction_id), rather than the
    order's own external_ref -- this is the identifier a payment
    confirmation actually hands back, not something set at order
    creation. external_transaction_id is only UNIQUE per (provider,
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
    """Joins in the customer's name/phone and sums order_items for the
    total, since orders carries no amount column of its own -- everything
    initiate_geniuspay_payment() needs, in one place.
    """
    order = conn.execute(
        format_query(
            "SELECT o.order_id, c.full_name, c.phone_number FROM orders o "
            "JOIN customers c ON c.customer_id = o.customer_id WHERE o.order_id = ?"
        ),
        (order_id,),
    ).fetchone()
    if order is None:
        return None

    total = conn.execute(
        format_query(
            "SELECT COALESCE(SUM(quantity * unit_price_fcfa), 0) AS total "
            "FROM order_items WHERE order_id = ?"
        ),
        (order_id,),
    ).fetchone()["total"]

    return {
        "order_id": order["order_id"],
        "customer_name": order["full_name"],
        "customer_phone": order["phone_number"],
        "amount_fcfa": total,
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


def _get_or_create_address(conn, customer_id, neighborhood, city):
    row = conn.execute(
        format_query("SELECT address_id FROM addresses WHERE customer_id = ? AND neighborhood = ?"),
        (customer_id, neighborhood),
    ).fetchone()
    if row:
        return row["address_id"]
    cursor = conn.execute(
        format_query("INSERT INTO addresses (customer_id, neighborhood, city) VALUES (?, ?, ?)"),
        (customer_id, neighborhood, city),
    )
    return get_last_row_id(cursor, "addresses", "address_id")


def sync_offline_orders(conn, orders):
    """Bulk-ingests orders a field agent's app captured while offline, once
    connectivity returns. Idempotent on external_ref (UNIQUE in the schema,
    same dual-layer guarantee -- a pre-flight lookup plus the UNIQUE
    backstop -- as the payments idempotency lock and the
    ecommerce_orders_raw ETL in pipeline.py): replaying the same batch after
    a blackout (e.g. the app retrying because it never saw the first sync's
    ack) skips every order already synced instead of double-inserting it.
    """
    synced = 0
    skipped = 0

    for order in orders:
        external_ref = order["external_ref"]
        existing = conn.execute(
            format_query("SELECT order_id FROM orders WHERE external_ref = ?"),
            (external_ref,),
        ).fetchone()
        if existing:
            skipped += 1
            continue

        neighborhood = order["neighborhood"]
        customer_id = _get_or_create_customer(conn, order["customer_name"], order["customer_phone"])
        address_id = _get_or_create_address(
            conn, customer_id, neighborhood, order.get("city", _DEFAULT_CITY)
        )

        conn.execute(
            format_query(
                "INSERT INTO orders (customer_id, address_id, customer_neighborhood, "
                "delivery_status, payment_status, external_ref) VALUES (?, ?, ?, ?, ?, ?)"
            ),
            (
                customer_id,
                address_id,
                neighborhood,
                order.get("delivery_status", "Pending"),
                order.get("payment_status", "Pending"),
                external_ref,
            ),
        )
        synced += 1

    conn.commit()
    return {"synced": synced, "skipped": skipped}


def list_orders(conn, neighborhood=None, status=None, page=1, per_page=20):
    """Filters orders by customer_neighborhood and/or delivery_status -- the
    exact leading-column and composite lookups idx_orders_neighborhood_status
    was built to serve. Returns (rows, total_records) for the requested page,
    total_records being the filtered count before LIMIT/OFFSET is applied.
    """
    where_clause = " WHERE 1=1"
    params = []
    if neighborhood:
        where_clause += " AND customer_neighborhood = ?"
        params.append(neighborhood)
    if status:
        where_clause += " AND delivery_status = ?"
        params.append(status)

    total_records = conn.execute(
        format_query("SELECT COUNT(*) AS n FROM orders" + where_clause), params
    ).fetchone()["n"]

    query = (
        "SELECT order_id, customer_neighborhood, delivery_status, payment_status, "
        "external_ref FROM orders" + where_clause + " ORDER BY order_id LIMIT ? OFFSET ?"
    )
    offset = (page - 1) * per_page
    rows = conn.execute(format_query(query), params + [per_page, offset]).fetchall()

    return rows, total_records
