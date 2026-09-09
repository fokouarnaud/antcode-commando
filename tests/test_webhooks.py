import hashlib
import hmac
import json

from app.config.database import get_connection


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


def orange_payload(**overrides):
    payload = {
        "order_id": 2,
        "external_transaction_id": "ORANGE-TX-0001",
        "amount_fcfa": 8000,
        "status": "SUCCESSFUL",
    }
    payload.update(overrides)
    return payload


def post_orange(client, secret, payload, signature=None):
    raw_body = json.dumps(payload).encode()
    if signature is None:
        signature = sign(secret, raw_body)
    return client.post(
        "/webhook/orange",
        data=raw_body,
        content_type="application/json",
        headers={"X-Orange-Signature": signature},
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


def test_orange_webhook_rejects_tampered_payload_even_with_valid_looking_signature(client, app):
    secret = app.config["ORANGE_WEBHOOK_SECRET"]
    original_body = json.dumps(orange_payload(amount_fcfa=8000)).encode()
    signature = sign(secret, original_body)
    tampered_body = json.dumps(orange_payload(amount_fcfa=1)).encode()

    response = client.post(
        "/webhook/orange",
        data=tampered_body,
        content_type="application/json",
        headers={"X-Orange-Signature": signature},
    )

    assert response.status_code == 401


def test_orange_webhook_processes_valid_callback_and_marks_order_paid(client, app):
    response = post_orange(client, app.config["ORANGE_WEBHOOK_SECRET"], orange_payload())

    assert response.status_code == 200
    assert response.get_json()["status"] == "processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    payment = conn.execute(
        "SELECT * FROM payments WHERE external_transaction_id = 'ORANGE-TX-0001'"
    ).fetchone()
    assert payment["provider"] == "orange"
    assert payment["status"] == "Successful"
    order = conn.execute("SELECT payment_status FROM orders WHERE order_id = 2").fetchone()
    assert order["payment_status"] == "Paid"


def test_momo_webhook_rejects_orange_signature_for_the_momo_route(client, app):
    """A signature computed with Orange's secret must not authenticate a
    request against /webhook/momo -- the two providers' secrets aren't
    interchangeable just because both endpoints share the same helper.
    """
    orange_secret = app.config["ORANGE_WEBHOOK_SECRET"]
    response = post_momo(client, orange_secret, momo_payload())

    assert response.status_code == 401


def test_momo_and_orange_callbacks_reusing_the_same_transaction_id_are_independent(client, app):
    """MTN and Orange transaction id formats could theoretically collide.
    The idempotency lock is keyed on (provider, external_transaction_id), so
    a shared string across the two providers must not be treated as a replay
    of one another -- each is its own payment against its own order.
    """
    shared_id = "SHARED-TX-COLLISION"

    momo_response = post_momo(
        client,
        app.config["MOMO_WEBHOOK_SECRET"],
        momo_payload(order_id=1, external_transaction_id=shared_id),
    )
    orange_response = post_orange(
        client,
        app.config["ORANGE_WEBHOOK_SECRET"],
        orange_payload(order_id=2, external_transaction_id=shared_id),
    )

    assert momo_response.get_json()["status"] == "processed"
    assert orange_response.get_json()["status"] == "processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM payments WHERE external_transaction_id = ?",
        (shared_id,),
    ).fetchone()["n"]
    assert count == 2
