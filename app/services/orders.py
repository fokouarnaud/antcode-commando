from app.config.database import format_query


def get_order_by_id(conn, order_id):
    return conn.execute(
        format_query(
            "SELECT order_id, customer_id, address_id, customer_neighborhood, delivery_status, "
            "payment_status, external_ref, created_at, updated_at FROM orders WHERE order_id = ?"
        ),
        (order_id,),
    ).fetchone()


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
