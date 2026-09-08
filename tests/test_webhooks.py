import hashlib
import hmac
import json

from app.database import get_connection


def momo_payload(**overrides):
    payload = {
        "provider": "MTN MoMo",
        "order_id": 1,
        "external_transaction_id": "MOMO-TX-0001",
        "amount_fcfa": 15000,
        "status": "SUCCESSFUL",
    }
    payload.update(overrides)
    return payload


def sign(secret, raw_body):
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def post_momo(client, secret, payload, signature=None):
    raw_body = json.dumps(payload).encode()
    if signature is None:
        signature = sign(secret, raw_body)
    return client.post(
        "/webhook/momo",
        data=raw_body,
        content_type="application/json",
        headers={"X-Momo-Signature": signature},
    )


def test_momo_webhook_rejects_request_with_missing_signature(client, app):
    raw_body = json.dumps(momo_payload()).encode()

    response = client.post("/webhook/momo", data=raw_body, content_type="application/json")

    assert response.status_code == 401
    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
    assert count == 0


def test_momo_webhook_rejects_request_with_wrong_secret_signature(client, app):
    response = post_momo(client, "wrong-secret", momo_payload())

    assert response.status_code == 401
    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
    assert count == 0


def test_momo_webhook_rejects_tampered_payload_even_with_valid_looking_signature(client, app):
    """A signature computed over one payload must not validate a different,
    tampered payload -- proves this is a real HMAC-over-body check, not a
    bare shared-secret compare that ignores body integrity.
    """
    secret = app.config["MOMO_WEBHOOK_SECRET"]
    original_body = json.dumps(momo_payload(amount_fcfa=15000)).encode()
    signature = sign(secret, original_body)
    tampered_body = json.dumps(momo_payload(amount_fcfa=999999999)).encode()

    response = client.post(
        "/webhook/momo",
        data=tampered_body,
        content_type="application/json",
        headers={"X-Momo-Signature": signature},
    )

    assert response.status_code == 401


def test_momo_webhook_processes_valid_callback_and_marks_order_paid(client, app):
    response = post_momo(client, app.config["MOMO_WEBHOOK_SECRET"], momo_payload())

    assert response.status_code == 200
    assert response.get_json()["status"] == "processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    payment = conn.execute("SELECT * FROM payments").fetchone()
    assert payment["external_transaction_id"] == "MOMO-TX-0001"
    assert payment["status"] == "Successful"
    order = conn.execute("SELECT payment_status FROM orders WHERE order_id = 1").fetchone()
    assert order["payment_status"] == "Paid"


def test_momo_webhook_does_not_double_process_retried_callback(client, app):
    """Simulates a Douala/Yaounde 3G timeout: MTN retries the same callback
    (identical external_transaction_id) after not receiving our ack in time.
    """
    secret = app.config["MOMO_WEBHOOK_SECRET"]
    payload = momo_payload()
    first = post_momo(client, secret, payload)
    second = post_momo(client, secret, payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()["status"] == "already_processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
    assert count == 1


def test_momo_webhook_returns_404_for_unknown_order(client, app):
    response = post_momo(
        client,
        app.config["MOMO_WEBHOOK_SECRET"],
        momo_payload(order_id=999, external_transaction_id="MOMO-TX-UNKNOWN"),
    )

    assert response.status_code == 404
