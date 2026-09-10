"""CRUD over the payments ledger -- distinct from app/services/webhooks.py,
which only ever inserts a payment as a side effect of a provider callback.
This module is for direct visibility/management of that same table: manual
reconciliation entries (offline cash, direct bank wires) and operational
lookups/corrections a dashboard or support agent would make by hand.
"""

from app.config.database import format_query, get_last_row_id
from app.services.webhooks import OrderNotFoundError

_PAYMENT_COLUMNS = (
    "payment_id, order_id, provider, external_transaction_id, amount_fcfa, status, received_at"
)

_VALID_STATUSES = {"pending", "completed", "failed"}


class PaymentValidationError(Exception):
    pass


class DuplicatePaymentError(Exception):
    pass


def list_payments(conn, page=1, per_page=20):
    """Newest-first (payment_id DESC) so a dashboard's first page always
    shows the most recent transaction activity.
    """
    total_records = conn.execute(
        format_query("SELECT COUNT(*) AS n FROM payments")
    ).fetchone()["n"]

    offset = (page - 1) * per_page
    rows = conn.execute(
        format_query(
            f"SELECT {_PAYMENT_COLUMNS} FROM payments ORDER BY payment_id DESC LIMIT ? OFFSET ?"
        ),
        (per_page, offset),
    ).fetchall()

    return rows, total_records


def get_payment_by_id(conn, payment_id):
    return conn.execute(
        format_query(f"SELECT {_PAYMENT_COLUMNS} FROM payments WHERE payment_id = ?"),
        (payment_id,),
    ).fetchone()


def get_payment_by_transaction_id(conn, external_transaction_id):
    """external_transaction_id is only UNIQUE per (provider,
    external_transaction_id) -- see app/services/orders.py::
    get_order_by_transaction_reference for why two providers could in
    principle share the same string; ORDER BY payment_id DESC LIMIT 1
    picks the most recently recorded match, same convention.

    Returns the payment with its order nested under "order" -- the
    "complete nested json details" a support agent needs without a
    second lookup.
    """
    payment = conn.execute(
        format_query(
            f"SELECT {_PAYMENT_COLUMNS} FROM payments WHERE external_transaction_id = ? "
            "ORDER BY payment_id DESC LIMIT 1"
        ),
        (external_transaction_id,),
    ).fetchone()
    if payment is None:
        return None

    order = conn.execute(
        format_query(
            "SELECT o.order_id, o.delivery_status, o.payment_status, "
            "c.full_name AS customer_name, c.phone_number AS customer_phone "
            "FROM orders o JOIN customers c ON c.customer_id = o.customer_id "
            "WHERE o.order_id = ?"
        ),
        (payment["order_id"],),
    ).fetchone()

    result = dict(payment)
    result["order"] = dict(order) if order else None
    return result


def _validate_status(status):
    if status not in _VALID_STATUSES:
        raise PaymentValidationError(f"invalid status: {status}")


def _conflicts_with_another_payment(conn, provider, external_transaction_id, exclude_payment_id=None):
    row = conn.execute(
        format_query(
            "SELECT payment_id FROM payments WHERE provider = ? AND external_transaction_id = ?"
        ),
        (provider, external_transaction_id),
    ).fetchone()
    if row is None:
        return False
    return row["payment_id"] != exclude_payment_id


def create_payment(conn, order_id, provider, external_transaction_id, amount_fcfa, status="pending"):
    if not order_id or not provider or not external_transaction_id:
        raise PaymentValidationError(
            "'order_id', 'provider', and 'external_transaction_id' are required"
        )
    if not isinstance(amount_fcfa, int) or amount_fcfa <= 0:
        raise PaymentValidationError("'amount_fcfa' must be a positive integer")
    _validate_status(status)

    order = conn.execute(
        format_query("SELECT order_id FROM orders WHERE order_id = ?"), (order_id,)
    ).fetchone()
    if order is None:
        raise OrderNotFoundError(order_id)

    if _conflicts_with_another_payment(conn, provider, external_transaction_id):
        raise DuplicatePaymentError(external_transaction_id)

    cursor = conn.execute(
        format_query(
            "INSERT INTO payments (order_id, provider, external_transaction_id, amount_fcfa, status) "
            "VALUES (?, ?, ?, ?, ?)"
        ),
        (order_id, provider, external_transaction_id, amount_fcfa, status),
    )
    conn.commit()
    payment_id = get_last_row_id(cursor, "payments", "payment_id")
    return get_payment_by_id(conn, payment_id)


def update_payment(conn, payment_id, fields):
    """Only status and external_transaction_id are mutable -- order_id,
    provider, and amount_fcfa are immutable business facts once recorded
    (mirrors app/services/orders.py::update_order_tracking only touching
    tracking fields, never customer/product/quantity).
    """
    existing = get_payment_by_id(conn, payment_id)
    if existing is None:
        return None

    updates = {}
    if "status" in fields:
        _validate_status(fields["status"])
        updates["status"] = fields["status"]
    if "external_transaction_id" in fields:
        new_reference = fields["external_transaction_id"]
        if not new_reference:
            raise PaymentValidationError("'external_transaction_id' cannot be empty")
        if _conflicts_with_another_payment(
            conn, existing["provider"], new_reference, exclude_payment_id=payment_id
        ):
            raise DuplicatePaymentError(new_reference)
        updates["external_transaction_id"] = new_reference

    if not updates:
        return existing

    set_clause = ", ".join(f"{column} = ?" for column in updates)
    conn.execute(
        format_query(f"UPDATE payments SET {set_clause} WHERE payment_id = ?"),
        list(updates.values()) + [payment_id],
    )
    conn.commit()
    return get_payment_by_id(conn, payment_id)


def delete_payment(conn, payment_id):
    """Returns True if deleted, False if payment_id didn't exist. Nothing
    references payments as a parent, so no FK RESTRICT case to translate.
    """
    cursor = conn.execute(format_query("DELETE FROM payments WHERE payment_id = ?"), (payment_id,))
    conn.commit()
    return cursor.rowcount > 0
