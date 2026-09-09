from unittest.mock import patch

from app.config.database import get_connection
from app.services.geniuspay import GeniusPayError


def test_get_order_by_id_returns_order_details(client):
    response = client.get("/orders/1")

    assert response.status_code == 200
    body = response.get_json()
    assert body["order_id"] == 1
    assert body["customer_neighborhood"] == "Akwa"
    assert body["delivery_status"] == "Pending"
    assert body["external_ref"] == "ECM-00001"


def test_get_order_by_id_returns_404_for_missing_order(client):
    response = client.get("/orders/999")

    assert response.status_code == 404


def test_get_order_by_external_ref_returns_order_details(client):
    response = client.get("/orders/ECM-00001")

    assert response.status_code == 200
    body = response.get_json()
    assert body["order_id"] == 1
    assert body["external_ref"] == "ECM-00001"


def test_get_order_by_unknown_external_ref_returns_404(client):
    response = client.get("/orders/ECM-99999")

    assert response.status_code == 404


def test_get_order_by_transaction_reference_returns_order_details(client, app):
    """A payment's own external_transaction_id -- e.g. the reference a
    GeniusPay checkout or a MoMo/Orange callback hands back -- must
    resolve to the order it was recorded against, distinct from both the
    numeric order_id and the "ECM-" external_ref.
    """
    conn = get_connection(app.config["DATABASE_PATH"])
    conn.execute(
        "INSERT INTO payments (order_id, provider, external_transaction_id, amount_fcfa, status) "
        "VALUES (1, 'geniuspay', 'MTX-A1B2C3D4E5', 12000, 'Successful')"
    )
    conn.commit()

    response = client.get("/orders/MTX-A1B2C3D4E5")

    assert response.status_code == 200
    body = response.get_json()
    assert body["order_id"] == 1
    assert body["external_ref"] == "ECM-00001"


def test_get_order_by_unknown_transaction_reference_returns_404(client):
    response = client.get("/orders/MTX-UNKNOWN-REF")

    assert response.status_code == 404


def test_list_orders_filters_by_neighborhood_and_status(client):
    response = client.get("/orders?neighborhood=Akwa&status=Delayed")

    assert response.status_code == 200
    body = response.get_json()
    assert [o["external_ref"] for o in body["data"]] == ["ECM-00002"]


def test_list_orders_without_filters_returns_all_orders(client):
    response = client.get("/orders")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["pagination"] == {
        "page": 1,
        "per_page": 20,
        "total_records": 2,
        "total_pages": 1,
    }


def test_list_orders_paginates_to_second_page(client):
    """conftest seeds exactly 2 orders (order_id 1 then 2, ORDER BY order_id):
    per_page=1 forces two one-item pages, so page=2 must return only the
    second order -- proving OFFSET actually skips the first page's row
    rather than just truncating LIMIT from the start every time.
    """
    response = client.get("/orders?page=2&per_page=1")

    assert response.status_code == 200
    body = response.get_json()
    assert [o["external_ref"] for o in body["data"]] == ["ECM-00002"]
    assert body["pagination"] == {
        "page": 2,
        "per_page": 1,
        "total_records": 2,
        "total_pages": 2,
    }


@patch("app.routes.orders.initiate_geniuspay_payment")
def test_checkout_returns_checkout_url_and_transaction_reference_on_success(mock_initiate, client):
    mock_initiate.return_value = {
        "checkout_url": "https://geniuspay.ci/pay/abc123",
        "transaction_reference": "GPAY-REF-001",
    }

    response = client.post("/orders/1/checkout")

    assert response.status_code == 200
    assert response.get_json() == {
        "checkout_url": "https://geniuspay.ci/pay/abc123",
        "transaction_reference": "GPAY-REF-001",
    }
    mock_initiate.assert_called_once_with(
        1, 0, customer_phone="+237690000001", customer_name="Amina Njoya"
    )


@patch("app.routes.orders.initiate_geniuspay_payment")
def test_checkout_returns_404_for_missing_order(mock_initiate, client):
    response = client.post("/orders/999/checkout")

    assert response.status_code == 404
    mock_initiate.assert_not_called()


@patch("app.routes.orders.initiate_geniuspay_payment")
def test_checkout_returns_502_when_geniuspay_fails(mock_initiate, client):
    mock_initiate.side_effect = GeniusPayError("GeniusPay payment initiation failed")

    response = client.post("/orders/1/checkout")

    assert response.status_code == 502
    assert response.get_json() == {"error": "payment initiation failed"}


def sync_batch(**overrides):
    order = {
        "external_ref": "OFFLINE-0001",
        "customer_name": "Jean Foka",
        "customer_phone": "+237699999901",
        "neighborhood": "Bonapriso",
    }
    order.update(overrides)
    return [order]


def test_sync_inserts_new_orders_and_reports_counts(client, app):
    payload = [
        sync_batch()[0],
        {
            "external_ref": "OFFLINE-0002",
            "customer_name": "Marie Ekwalla",
            "customer_phone": "+237699999902",
            "neighborhood": "Deido",
        },
    ]

    response = client.post("/orders/sync", json=payload)

    assert response.status_code == 200
    assert response.get_json() == {"synced": 2, "skipped": 0}

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE external_ref IN ('OFFLINE-0001', 'OFFLINE-0002')"
    ).fetchone()["n"]
    assert count == 2
    order = conn.execute(
        "SELECT delivery_status, payment_status FROM orders WHERE external_ref = 'OFFLINE-0001'"
    ).fetchone()
    assert order["delivery_status"] == "Pending"
    assert order["payment_status"] == "Pending"


def test_sync_is_idempotent_on_replayed_batch(client, app):
    """Simulates a field agent's app retrying the same sync after an
    internet blackout swallowed the first response -- the second POST of
    the identical batch must skip every already-synced order rather than
    inserting duplicates or splitting them into a second bucket.
    """
    payload = sync_batch(external_ref="OFFLINE-0003", customer_phone="+237699999903")

    first = client.post("/orders/sync", json=payload)
    second = client.post("/orders/sync", json=payload)

    assert first.status_code == 200
    assert first.get_json() == {"synced": 1, "skipped": 0}
    assert second.status_code == 200
    assert second.get_json() == {"synced": 0, "skipped": 1}

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE external_ref = 'OFFLINE-0003'"
    ).fetchone()["n"]
    assert count == 1
    customer_count = conn.execute(
        "SELECT COUNT(*) AS n FROM customers WHERE phone_number = '+237699999903'"
    ).fetchone()["n"]
    assert customer_count == 1


def test_sync_reuses_existing_customer_and_address_across_orders(client, app):
    """Two orders from the same returning customer/neighborhood must not
    create a second customer or address row -- get_or_create semantics.
    """
    payload = [
        {
            "external_ref": "OFFLINE-0004",
            "customer_name": "Paul Biya Jr",
            "customer_phone": "+237699999904",
            "neighborhood": "Akwa",
        },
        {
            "external_ref": "OFFLINE-0005",
            "customer_name": "Paul Biya Jr",
            "customer_phone": "+237699999904",
            "neighborhood": "Akwa",
        },
    ]

    response = client.post("/orders/sync", json=payload)

    assert response.get_json() == {"synced": 2, "skipped": 0}

    conn = get_connection(app.config["DATABASE_PATH"])
    customer_count = conn.execute(
        "SELECT COUNT(*) AS n FROM customers WHERE phone_number = '+237699999904'"
    ).fetchone()["n"]
    assert customer_count == 1


def test_sync_returns_400_for_non_array_payload(client):
    response = client.post("/orders/sync", json={"not": "a list"})

    assert response.status_code == 400


def test_sync_returns_400_for_order_missing_required_field(client):
    response = client.post("/orders/sync", json=[{"external_ref": "OFFLINE-0006"}])

    assert response.status_code == 400
