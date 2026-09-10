from app.config.database import get_connection


def create_payment(client, **overrides):
    payload = {
        "order_id": "ECM-00001",
        "provider": "geniuspay",
        "external_transaction_id": "MTX-A1B2C3D4E5",
        "amount_fcfa": 75000,
    }
    payload.update(overrides)
    return client.post("/payments", json=payload)


def test_create_payment_returns_201(client):
    response = create_payment(client)

    assert response.status_code == 201
    body = response.get_json()
    assert body["order_id"] == "ECM-00001"
    assert body["provider"] == "geniuspay"
    assert body["external_transaction_id"] == "MTX-A1B2C3D4E5"
    assert body["amount_fcfa"] == 75000
    assert body["status"] == "pending"
    assert "payment_id" in body


def test_create_payment_defaults_status_to_pending_when_omitted(client):
    response = create_payment(client)

    assert response.get_json()["status"] == "pending"


def test_create_payment_accepts_explicit_status(client):
    response = create_payment(client, status="completed")

    assert response.status_code == 201
    assert response.get_json()["status"] == "completed"


def test_create_payment_returns_400_for_missing_required_field(client):
    response = create_payment(client, provider=None)

    assert response.status_code == 400


def test_create_payment_returns_400_for_non_positive_amount(client):
    response = create_payment(client, amount_fcfa=0)

    assert response.status_code == 400


def test_create_payment_returns_400_for_invalid_status(client):
    response = create_payment(client, status="Refunded")

    assert response.status_code == 400


def test_create_payment_returns_404_for_unknown_order(client):
    response = create_payment(client, order_id="ECM-99999")

    assert response.status_code == 404


def test_create_payment_returns_409_for_duplicate_provider_and_transaction_id(client):
    create_payment(client)

    response = create_payment(client, order_id="ECM-00002")

    assert response.status_code == 409


def test_create_payment_allows_same_transaction_id_across_different_providers(client):
    """UNIQUE is on the (provider, external_transaction_id) pair, not the
    transaction id alone -- see app/services/webhooks.py's own idempotency
    docstring for why two providers must not be conflated.
    """
    first = create_payment(client, provider="momo")
    second = create_payment(client, provider="orange")

    assert first.status_code == 201
    assert second.status_code == 201


def test_list_payments_orders_newest_first_and_paginates(client, app):
    for i in range(3):
        create_payment(client, external_transaction_id=f"MTX-{i}")

    response = client.get("/payments?page=1&per_page=2")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["pagination"] == {
        "page": 1,
        "per_page": 2,
        "total_records": 3,
        "total_pages": 2,
    }
    # Newest (highest payment_id) first.
    payment_ids = [row["payment_id"] for row in body["data"]]
    assert payment_ids == sorted(payment_ids, reverse=True)
    assert payment_ids[0] == max(payment_ids)


def test_list_payments_respects_explicit_per_page_of_five(client, app):
    """Regression test: per_page must be honored as given, not silently
    replaced by the default of 20.
    """
    for i in range(6):
        create_payment(client, external_transaction_id=f"MTX-{i}")

    response = client.get("/payments?page=1&per_page=5")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 5
    assert body["pagination"] == {
        "page": 1,
        "per_page": 5,
        "total_records": 6,
        "total_pages": 2,
    }


def test_list_payments_per_page_zero_is_clamped_to_one_not_reset_to_default(client):
    """per_page=0 must be clamped to the minimum of 1, not silently swapped
    for the default of 20 (the falsy-zero `x or default` bug).
    """
    create_payment(client)

    response = client.get("/payments?per_page=0")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 1
    assert body["pagination"]["per_page"] == 1


def test_get_payment_by_transaction_id_returns_nested_order_details(client):
    create_payment(client)

    response = client.get("/payments/MTX-A1B2C3D4E5")

    assert response.status_code == 200
    body = response.get_json()
    assert body["external_transaction_id"] == "MTX-A1B2C3D4E5"
    assert body["order"]["order_id"] == "ECM-00001"
    assert body["order"]["customer_name"] == "Amina Njoya"
    assert body["order"]["customer_phone"] == "+237690000001"


def test_get_payment_by_unknown_transaction_id_returns_404(client):
    response = client.get("/payments/MTX-UNKNOWN")

    assert response.status_code == 404


def test_update_payment_changes_status(client):
    created = create_payment(client).get_json()

    response = client.put(f"/payments/{created['payment_id']}", json={"status": "completed"})

    assert response.status_code == 200
    assert response.get_json()["status"] == "completed"


def test_update_payment_changes_external_transaction_id(client):
    created = create_payment(client).get_json()

    response = client.put(
        f"/payments/{created['payment_id']}", json={"external_transaction_id": "MTX-CORRECTED"}
    )

    assert response.status_code == 200
    assert response.get_json()["external_transaction_id"] == "MTX-CORRECTED"


def test_update_payment_returns_400_for_invalid_status(client):
    created = create_payment(client).get_json()

    response = client.put(f"/payments/{created['payment_id']}", json={"status": "Refunded"})

    assert response.status_code == 400


def test_update_payment_returns_409_when_new_reference_collides_with_another_payment(client):
    first = create_payment(client, external_transaction_id="MTX-FIRST").get_json()
    create_payment(client, external_transaction_id="MTX-SECOND")

    response = client.put(
        f"/payments/{first['payment_id']}", json={"external_transaction_id": "MTX-SECOND"}
    )

    assert response.status_code == 409


def test_update_payment_returns_404_for_unknown_id(client):
    response = client.put("/payments/9999", json={"status": "completed"})

    assert response.status_code == 404


def test_update_payment_does_not_change_order_id_or_amount(client):
    """order_id, provider, and amount_fcfa are immutable business facts --
    PUT only ever touches status/external_transaction_id.
    """
    created = create_payment(client).get_json()

    response = client.put(f"/payments/{created['payment_id']}", json={
        "order_id": "ECM-00002", "amount_fcfa": 1, "provider": "orange",
    })

    assert response.status_code == 200
    body = response.get_json()
    assert body["order_id"] == "ECM-00001"
    assert body["amount_fcfa"] == 75000
    assert body["provider"] == "geniuspay"


def test_delete_payment_removes_it(client, app):
    created = create_payment(client).get_json()

    response = client.delete(f"/payments/{created['payment_id']}")

    assert response.status_code == 204

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM payments WHERE payment_id = ?", (created["payment_id"],)
    ).fetchone()["n"]
    assert count == 0


def test_delete_payment_returns_404_for_unknown_id(client):
    response = client.delete("/payments/9999")

    assert response.status_code == 404
