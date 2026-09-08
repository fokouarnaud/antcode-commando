"""Processes MTN MoMo / Orange Money payment callbacks.

Idempotency is state-gated on payments.external_transaction_id (UNIQUE in
the schema): a callback whose transaction id already has a payment row is
a replay -- most commonly MTN retrying after a 3G timeout in Douala/Yaounde
dropped our acknowledgement -- and is reported back as already_processed
without inserting a second payment or re-applying the order update.
"""

class OrderNotFoundError(Exception):
    pass


_STATUS_MAP = {
    "SUCCESSFUL": ("Successful", "Paid"),
    "FAILED": ("Failed", "Failed"),
}


def process_momo_callback(conn, payload):
    external_transaction_id = payload["external_transaction_id"]

    existing = conn.execute(
        "SELECT payment_id FROM payments WHERE external_transaction_id = ?",
        (external_transaction_id,),
    ).fetchone()
    if existing:
        return {"status": "already_processed", "payment_id": existing["payment_id"]}

    order_id = payload["order_id"]
    order = conn.execute(
        "SELECT order_id FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    if order is None:
        raise OrderNotFoundError(order_id)

    payment_status, order_payment_status = _STATUS_MAP.get(
        payload["status"].upper(), ("Pending", "Pending")
    )

    cursor = conn.execute(
        "INSERT INTO payments (order_id, provider, external_transaction_id, amount_fcfa, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            order_id,
            payload.get("provider", "Unknown"),
            external_transaction_id,
            payload["amount_fcfa"],
            payment_status,
        ),
    )
    conn.execute(
        "UPDATE orders SET payment_status = ? WHERE order_id = ?",
        (order_payment_status, order_id),
    )
    conn.commit()

    return {"status": "processed", "payment_id": cursor.lastrowid}
