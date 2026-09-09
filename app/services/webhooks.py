"""Processes MTN MoMo / Orange Money / aggregator / GeniusPay payment callbacks.

Idempotency is state-gated on the (provider, external_transaction_id) pair
(UNIQUE composite key in the schema): a callback whose provider+transaction
id already has a payment row is a replay -- most commonly MTN retrying after
a 3G timeout in Douala/Yaounde dropped our acknowledgement -- and is
reported back as already_processed without inserting a second payment or
re-applying the order update. The pair, not the transaction id alone, is
what's checked: MTN and Orange mint their ids independently, so nothing
prevents the two operators from ever producing the same string, and treating
that coincidence as a replay would silently drop a real payment.
"""

from app.config.database import format_query, get_last_row_id


class OrderNotFoundError(Exception):
    pass


_STATUS_MAP = {
    "SUCCESSFUL": ("Successful", "Paid"),
    "FAILED": ("Failed", "Failed"),
}

_GENIUSPAY_EVENT_STATUS = {
    "payment.success": "SUCCESSFUL",
    "payment.failed": "FAILED",
}


def _extract_fields(payload):
    """GeniusPay nests everything under data/metadata and signals outcome
    via the X-Webhook-Event header (mirrored into payload["event"] by the
    route) rather than a flat status field like the other providers.

    GeniusPay's dashboard "send test event" button (event webhook.test)
    fires with no data/metadata block at all, so every lookup here is
    defensive: order_id falls back to None rather than raising KeyError,
    and process_momo_callback() short-circuits on that event before it
    would otherwise be treated as a malformed real payment.
    """
    if payload.get("provider") == "geniuspay":
        data = payload.get("data") or {}
        metadata = data.get("metadata") or {}
        return (
            metadata.get("order_id"),
            data.get("transaction_id"),
            data.get("amount"),
            _GENIUSPAY_EVENT_STATUS.get(payload.get("event"), "PENDING"),
        )
    return (
        payload["order_id"],
        payload["external_transaction_id"],
        payload["amount_fcfa"],
        payload["status"].upper(),
    )


def process_momo_callback(conn, payload):
    if payload.get("event") == "webhook.test":
        return {"status": "test_success", "message": "Test webhook acknowledged"}

    provider = payload.get("provider", "Unknown")
    order_id, external_transaction_id, amount_fcfa, status_raw = _extract_fields(payload)

    existing = conn.execute(
        format_query(
            "SELECT payment_id FROM payments WHERE provider = ? AND external_transaction_id = ?"
        ),
        (provider, external_transaction_id),
    ).fetchone()
    if existing:
        return {"status": "already_processed", "payment_id": existing["payment_id"]}

    order = conn.execute(
        format_query("SELECT order_id FROM orders WHERE order_id = ?"), (order_id,)
    ).fetchone()
    if order is None:
        raise OrderNotFoundError(order_id)

    payment_status, order_payment_status = _STATUS_MAP.get(status_raw, ("Pending", "Pending"))

    cursor = conn.execute(
        format_query(
            "INSERT INTO payments (order_id, provider, external_transaction_id, amount_fcfa, status) "
            "VALUES (?, ?, ?, ?, ?)"
        ),
        (
            order_id,
            provider,
            external_transaction_id,
            amount_fcfa,
            payment_status,
        ),
    )
    conn.execute(
        format_query("UPDATE orders SET payment_status = ? WHERE order_id = ?"),
        (order_payment_status, order_id),
    )
    conn.commit()

    return {"status": "processed", "payment_id": get_last_row_id(cursor, "payments", "payment_id")}
