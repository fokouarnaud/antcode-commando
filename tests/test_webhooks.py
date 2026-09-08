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


def test_momo_webhook_rejects_request_with_invalid_token(client, app):
    response = client.post(
        "/webhook/momo",
        json=momo_payload(),
        headers={"X-Webhook-Token": "wrong-secret"},
    )

    assert response.status_code == 401
    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
    assert count == 0


def test_momo_webhook_processes_valid_callback_and_marks_order_paid(client, app):
    response = client.post(
        "/webhook/momo",
        json=momo_payload(),
        headers={"X-Webhook-Token": app.config["MOMO_WEBHOOK_SECRET"]},
    )

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
    token = app.config["MOMO_WEBHOOK_SECRET"]
    first = client.post("/webhook/momo", json=momo_payload(), headers={"X-Webhook-Token": token})
    second = client.post("/webhook/momo", json=momo_payload(), headers={"X-Webhook-Token": token})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()["status"] == "already_processed"

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
    assert count == 1


def test_momo_webhook_returns_404_for_unknown_order(client, app):
    response = client.post(
        "/webhook/momo",
        json=momo_payload(order_id=999, external_transaction_id="MOMO-TX-UNKNOWN"),
        headers={"X-Webhook-Token": app.config["MOMO_WEBHOOK_SECRET"]},
    )

    assert response.status_code == 404
