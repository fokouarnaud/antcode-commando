from app.config.database import format_query


def get_order_by_id(conn, order_id):
    return conn.execute(
        format_query(
            "SELECT order_id, customer_id, address_id, customer_neighborhood, delivery_status, "
            "payment_status, external_ref, created_at, updated_at FROM orders WHERE order_id = ?"
        ),
        (order_id,),
    ).fetchone()


def list_orders(conn, neighborhood=None, status=None):
    """Filters orders by customer_neighborhood and/or delivery_status -- the
    exact leading-column and composite lookups idx_orders_neighborhood_status
    was built to serve.
    """
    query = (
        "SELECT order_id, customer_neighborhood, delivery_status, payment_status, "
        "external_ref FROM orders WHERE 1=1"
    )
    params = []
    if neighborhood:
        query += " AND customer_neighborhood = ?"
        params.append(neighborhood)
    if status:
        query += " AND delivery_status = ?"
        params.append(status)
    query += " ORDER BY order_id"
    return conn.execute(format_query(query), params).fetchall()
