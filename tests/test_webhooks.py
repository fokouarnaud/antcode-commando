import hashlib
import hmac
import json

from app.config.database import get_connection


def momo_payload(**overrides):
    payload = {
        "provider": "MTN MoMo",
        "order_id": "ECM-00001",
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
        "order_id": "ECM-00002",
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
    assert payment["status"] == "completed"
    order = conn.execute(
        "SELECT payment_status FROM orders WHERE order_id = ?", ("ECM-00001",)
    ).fetchone()
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
        momo_payload(order_id="ECM-99999", external_transaction_id="MOMO-TX-UNKNOWN"),
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
    assert payment["status"] == "completed"
    order = conn.execute(
        "SELECT payment_status FROM orders WHERE order_id = ?", ("ECM-00002",)
    ).fetchone()
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
        momo_payload(order_id="ECM-00001", external_transaction_id=shared_id),
    )
    orange_response = post_orange(
        client,
        app.config["ORANGE_WEBHOOK_SECRET"],
        orange_payload(order_id="ECM-00002", external_transaction_id=shared_id),
    )

    assert momo_response.get_json()["status"] == "processed"
    assert orange_response.get_json()["status"] == "processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM payments WHERE external_transaction_id = ?",
        (shared_id,),
    ).fetchone()["n"]
    assert count == 2


def campay_payload(**overrides):
    payload = {
        "order_id": "ECM-00001",
        "external_transaction_id": "CAMPAY-TX-0001",
        "amount_fcfa": 5000,
        "status": "SUCCESSFUL",
    }
    payload.update(overrides)
    return payload


def post_provider(client, provider, secret, payload, header, signature=None):
    raw_body = json.dumps(payload).encode()
    if signature is None:
        signature = sign(secret, raw_body)
    return client.post(
        f"/webhook/{provider}",
        data=raw_body,
        content_type="application/json",
        headers={header: signature},
    )


def test_webhook_route_processes_campay_callback_via_its_own_provider_secret(client, app):
    """campay is just another entry in _PROVIDER_CONFIG -- /webhook/campay
    must resolve CAMPAY_WEBHOOK_SECRET/X-Campay-Signature directly from the
    URL, with no DEFAULT_AGGREGATOR indirection involved.
    """
    response = post_provider(
        client,
        "campay",
        app.config["CAMPAY_WEBHOOK_SECRET"],
        campay_payload(),
        "X-Campay-Signature",
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    payment = conn.execute(
        "SELECT * FROM payments WHERE external_transaction_id = 'CAMPAY-TX-0001'"
    ).fetchone()
    assert payment["provider"] == "campay"


def test_webhook_route_processes_smobilpay_callback_via_its_own_provider_secret(client, app):
    response = post_provider(
        client,
        "smobilpay",
        app.config["SMOBILPAY_WEBHOOK_SECRET"],
        campay_payload(order_id="ECM-00002", external_transaction_id="SMOBIL-TX-0001"),
        "X-Smobilpay-Signature",
    )

    assert response.status_code == 200

    conn = get_connection(app.config["DATABASE_PATH"])
    payment = conn.execute(
        "SELECT * FROM payments WHERE external_transaction_id = 'SMOBIL-TX-0001'"
    ).fetchone()
    assert payment["provider"] == "smobilpay"


def test_webhook_route_returns_500_for_unknown_provider(client):
    response = client.post(
        "/webhook/unknown-provider", data=b"{}", content_type="application/json"
    )

    assert response.status_code == 500


def geniuspay_payload(order_id="ECM-00001", transaction_id="GENIUSPAY-TX-0001", amount=12000):
    """Flat data shape (reference/amount/metadata directly under data),
    verified against a real captured GeniusPay sandbox webhook -- not the
    data.transaction.* nesting the written API doc's webhook example
    (incorrectly) showed.
    """
    return {
        "data": {
            "reference": transaction_id,
            "amount": amount,
            "metadata": {"order_id": order_id},
        },
    }


def sign_geniuspay(secret, timestamp, raw_body_string):
    """GeniusPay signs f"{timestamp}.{raw_body}" -- verified by recomputing
    this HMAC against a real captured sandbox webhook and matching the
    X-Webhook-Signature it actually sent, byte for byte.
    """
    message = f"{timestamp}.{raw_body_string}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def post_geniuspay(client, secret, payload, event="payment.success", timestamp="1700000000", signature=None):
    raw_body_string = json.dumps(payload)
    if signature is None:
        signature = sign_geniuspay(secret, timestamp, raw_body_string)
    return client.post(
        "/webhook/geniuspay",
        data=raw_body_string.encode(),
        content_type="application/json",
        headers={
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Event": event,
        },
    )


def test_geniuspay_webhook_rejects_request_with_missing_signature(client, app):
    raw_body_string = json.dumps(geniuspay_payload())

    response = client.post(
        "/webhook/geniuspay",
        data=raw_body_string.encode(),
        content_type="application/json",
        headers={"X-Webhook-Timestamp": "1700000000", "X-Webhook-Event": "payment.success"},
    )

    assert response.status_code == 401


def test_geniuspay_webhook_rejects_tampered_body_even_with_valid_looking_signature(client, app):
    """The signed message is f"{timestamp}.{raw_body}" -- proves the body,
    not just the timestamp, is covered by the signature.
    """
    secret = app.config["GENIUSPAY_WEBHOOK_SECRET"]
    timestamp = "1700000000"
    original_body = json.dumps(geniuspay_payload(amount=12000))
    signature = sign_geniuspay(secret, timestamp, original_body)
    tampered_body = json.dumps(geniuspay_payload(amount=999999999))

    response = client.post(
        "/webhook/geniuspay",
        data=tampered_body.encode(),
        content_type="application/json",
        headers={
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Event": "payment.success",
        },
    )

    assert response.status_code == 401


def test_geniuspay_webhook_rejects_mismatched_timestamp_even_with_valid_body_signature(client, app):
    """The timestamp is part of the signed message too -- replaying a valid
    body+signature pair under a different X-Webhook-Timestamp must fail.
    """
    secret = app.config["GENIUSPAY_WEBHOOK_SECRET"]
    payload = geniuspay_payload()
    raw_body_string = json.dumps(payload)
    signature = sign_geniuspay(secret, "1700000000", raw_body_string)

    response = post_geniuspay(
        client, secret, payload, timestamp="1700000999", signature=signature
    )

    assert response.status_code == 401


def test_geniuspay_webhook_coerces_decimal_string_amount(client, app):
    """GeniusPay's sandbox sends amount as a decimal string (e.g.
    "285000.00"), verified against a real webhook capture -- it must land
    in amount_fcfa as a plain integer, not the raw string.
    """
    secret = app.config["GENIUSPAY_WEBHOOK_SECRET"]
    payload = geniuspay_payload(transaction_id="GENIUSPAY-TX-DECIMAL", amount="285000.00")

    response = post_geniuspay(client, secret, payload)

    assert response.status_code == 200
    conn = get_connection(app.config["DATABASE_PATH"])
    payment = conn.execute(
        "SELECT amount_fcfa FROM payments WHERE external_transaction_id = 'GENIUSPAY-TX-DECIMAL'"
    ).fetchone()
    assert payment["amount_fcfa"] == 285000


def test_geniuspay_webhook_processes_payment_success_event_and_marks_order_paid(client, app):
    response = post_geniuspay(client, app.config["GENIUSPAY_WEBHOOK_SECRET"], geniuspay_payload())

    assert response.status_code == 200
    assert response.get_json()["status"] == "processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    payment = conn.execute(
        "SELECT * FROM payments WHERE external_transaction_id = 'GENIUSPAY-TX-0001'"
    ).fetchone()
    assert payment["provider"] == "geniuspay"
    assert payment["amount_fcfa"] == 12000
    assert payment["status"] == "completed"
    order = conn.execute(
        "SELECT payment_status FROM orders WHERE order_id = ?", ("ECM-00001",)
    ).fetchone()
    assert order["payment_status"] == "Paid"


def test_geniuspay_webhook_does_not_mark_order_paid_for_non_success_event(client, app):
    response = post_geniuspay(
        client,
        app.config["GENIUSPAY_WEBHOOK_SECRET"],
        geniuspay_payload(transaction_id="GENIUSPAY-TX-0002"),
        event="payment.failed",
    )

    assert response.status_code == 200

    conn = get_connection(app.config["DATABASE_PATH"])
    order = conn.execute(
        "SELECT payment_status FROM orders WHERE order_id = ?", ("ECM-00001",)
    ).fetchone()
    assert order["payment_status"] == "Unpaid"


def test_geniuspay_webhook_does_not_double_process_retried_callback(client, app):
    secret = app.config["GENIUSPAY_WEBHOOK_SECRET"]
    payload = geniuspay_payload()
    first = post_geniuspay(client, secret, payload)
    second = post_geniuspay(client, secret, payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()["status"] == "already_processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM payments WHERE external_transaction_id = 'GENIUSPAY-TX-0001'"
    ).fetchone()["n"]
    assert count == 1


def test_geniuspay_webhook_acknowledges_test_event_without_touching_orders(client, app):
    """GeniusPay's dashboard 'send test event' button fires event=webhook.test
    with an empty body (no data/metadata block) -- this must not crash with
    KeyError: 'metadata' or attempt any order lookup/payment insert.
    """
    response = post_geniuspay(
        client, app.config["GENIUSPAY_WEBHOOK_SECRET"], {}, event="webhook.test"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "test_success",
        "message": "Test webhook acknowledged",
    }

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
    assert count == 0


def test_geniuspay_webhook_returns_404_for_unknown_order(client, app):
    response = post_geniuspay(
        client,
        app.config["GENIUSPAY_WEBHOOK_SECRET"],
        geniuspay_payload(order_id="ECM-99999", transaction_id="GENIUSPAY-TX-UNKNOWN"),
    )

    assert response.status_code == 404


def test_simulate_carrier_webhook_404s_when_debug_disabled(client):
    """The dev-only simulation route must not be reachable unless the app
    was explicitly started with debug=True -- proves the safety gate.
    """
    response = client.post(
        "/webhook/simulate-carrier",
        json={
            "provider": "momo",
            "order_id": "ECM-00001",
            "external_transaction_id": "SIM-TX-00",
            "amount": 5000,
        },
    )

    assert response.status_code == 404


def test_simulate_carrier_webhook_processes_momo_callback_when_debug_enabled(app):
    app.config["DEBUG"] = True
    client = app.test_client()

    response = client.post(
        "/webhook/simulate-carrier",
        json={
            "provider": "momo",
            "order_id": "ECM-00001",
            "external_transaction_id": "SIM-TX-01",
            "amount": 5000,
            "phone": "+237690000009",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    payment = conn.execute(
        "SELECT * FROM payments WHERE external_transaction_id = 'SIM-TX-01'"
    ).fetchone()
    assert payment["provider"] == "momo"
    assert payment["status"] == "completed"
    order = conn.execute(
        "SELECT payment_status FROM orders WHERE order_id = ?", ("ECM-00001",)
    ).fetchone()
    assert order["payment_status"] == "Paid"


def test_simulate_carrier_webhook_processes_orange_callback_when_debug_enabled(app):
    app.config["DEBUG"] = True
    client = app.test_client()

    response = client.post(
        "/webhook/simulate-carrier",
        json={
            "provider": "orange",
            "order_id": "ECM-00002",
            "external_transaction_id": "SIM-TX-02",
            "amount": 8000,
        },
    )

    assert response.status_code == 200

    conn = get_connection(app.config["DATABASE_PATH"])
    payment = conn.execute(
        "SELECT * FROM payments WHERE external_transaction_id = 'SIM-TX-02'"
    ).fetchone()
    assert payment["provider"] == "orange"


def test_simulate_carrier_webhook_rejects_unsupported_provider_when_debug_enabled(app):
    app.config["DEBUG"] = True
    client = app.test_client()

    response = client.post(
        "/webhook/simulate-carrier",
        json={
            "provider": "geniuspay",
            "order_id": "ECM-00001",
            "external_transaction_id": "SIM-TX-BAD",
            "amount": 1000,
        },
    )

    assert response.status_code == 400


def test_simulate_carrier_webhook_returns_404_for_unknown_order_when_debug_enabled(app):
    app.config["DEBUG"] = True
    client = app.test_client()

    response = client.post(
        "/webhook/simulate-carrier",
        json={
            "provider": "momo",
            "order_id": "ECM-99999",
            "external_transaction_id": "SIM-TX-03",
            "amount": 1000,
        },
    )

    assert response.status_code == 404


def test_simulate_carrier_webhook_is_idempotent_on_replay_when_debug_enabled(app):
    """Reproduces the double-entry replay scenario documented in the
    README: submitting the identical transaction ID a second time must
    return already_processed and leave exactly one payment row behind.
    """
    app.config["DEBUG"] = True
    client = app.test_client()
    body = {
        "provider": "momo",
        "order_id": "ECM-00001",
        "external_transaction_id": "SIM-TX-04",
        "amount": 3000,
    }

    first = client.post("/webhook/simulate-carrier", json=body)
    second = client.post("/webhook/simulate-carrier", json=body)

    assert first.status_code == 200
    assert first.get_json()["status"] == "processed"
    assert second.status_code == 200
    assert second.get_json()["status"] == "already_processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM payments WHERE external_transaction_id = 'SIM-TX-04'"
    ).fetchone()["n"]
    assert count == 1
