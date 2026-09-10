from unittest.mock import patch

from app.config.database import get_connection
from app.services.geniuspay import GeniusPayError


def test_get_order_by_order_id_returns_order_details(client):
    response = client.get("/orders/ECM-00001")

    assert response.status_code == 200
    body = response.get_json()
    assert body["order_id"] == "ECM-00001"
    assert body["neighborhood"] == "Akwa"
    assert body["delivery_status"] == "Pending"


def test_get_order_by_unknown_order_id_returns_404(client):
    response = client.get("/orders/ECM-99999")

    assert response.status_code == 404


def test_get_order_by_transaction_reference_returns_order_details(client, app):
    """A payment's own external_transaction_id -- e.g. the reference a
    GeniusPay checkout or a MoMo/Orange callback hands back -- must
    resolve to the order it was recorded against, distinct from the
    order's own "ECM-" order_id.
    """
    conn = get_connection(app.config["DATABASE_PATH"])
    conn.execute(
        "INSERT INTO payments (order_id, provider, external_transaction_id, amount_fcfa, status) "
        "VALUES ('ECM-00001', 'geniuspay', 'MTX-A1B2C3D4E5', 12000, 'completed')"
    )
    conn.commit()

    response = client.get("/orders/MTX-A1B2C3D4E5")

    assert response.status_code == 200
    body = response.get_json()
    assert body["order_id"] == "ECM-00001"


def test_get_order_by_unknown_transaction_reference_returns_404(client):
    response = client.get("/orders/MTX-UNKNOWN-REF")

    assert response.status_code == 404


def test_list_orders_filters_by_neighborhood_and_status(client):
    response = client.get("/orders?neighborhood=Akwa&status=Shipped")

    assert response.status_code == 200
    body = response.get_json()
    assert [o["order_id"] for o in body["data"]] == ["ECM-00002"]


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
    """conftest seeds exactly 2 orders (ECM-00001 then ECM-00002, ORDER BY
    order_id): per_page=1 forces two one-item pages, so page=2 must return
    only the second order -- proving OFFSET actually skips the first
    page's row rather than just truncating LIMIT from the start every time.
    """
    response = client.get("/orders?page=2&per_page=1")

    assert response.status_code == 200
    body = response.get_json()
    assert [o["order_id"] for o in body["data"]] == ["ECM-00002"]
    assert body["pagination"] == {
        "page": 2,
        "per_page": 1,
        "total_records": 2,
        "total_pages": 2,
    }


def _seed_extra_orders(app, count, start_at=3):
    """Inserts `count` additional orders (ECM-000{start_at}..) against the
    customer/address/product conftest already seeded, so pagination tests
    can exercise per_page values above the base 2 orders.
    """
    conn = get_connection(app.config["DATABASE_PATH"])
    for i in range(start_at, start_at + count):
        conn.execute(
            "INSERT INTO orders (order_id, customer_id, address_id, product_id, quantity, "
            "unit_price_fcfa, delivery_status, payment_status) "
            "VALUES (?, 1, 1, 1, 1, 75000, 'Pending', 'Unpaid')",
            (f"ECM-{i:05d}",),
        )
    conn.commit()


def test_list_orders_respects_explicit_per_page_of_five(client, app):
    """Regression test: per_page must be honored as given, not silently
    replaced by the default of 20.
    """
    _seed_extra_orders(app, count=4)  # 2 seeded + 4 = 6 total orders

    response = client.get("/orders?page=1&per_page=5")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 5
    assert body["pagination"] == {
        "page": 1,
        "per_page": 5,
        "total_records": 6,
        "total_pages": 2,
    }


def test_list_orders_per_page_zero_is_clamped_to_one_not_reset_to_default(client):
    """per_page=0 must be clamped to the minimum of 1, not silently swapped
    for the default of 20 (the falsy-zero `x or default` bug).
    """
    response = client.get("/orders?per_page=0")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 1
    assert body["pagination"]["per_page"] == 1


def test_list_orders_per_page_above_max_is_clamped_to_one_hundred(client, app):
    _seed_extra_orders(app, count=150)  # 2 seeded + 150 = 152 total orders

    response = client.get("/orders?per_page=500")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 100
    assert body["pagination"]["per_page"] == 100


@patch("app.routes.orders.initiate_geniuspay_payment")
def test_checkout_returns_checkout_url_and_transaction_reference_on_success(mock_initiate, client):
    mock_initiate.return_value = {
        "checkout_url": "https://geniuspay.ci/pay/abc123",
        "transaction_reference": "GPAY-REF-001",
    }

    response = client.post("/orders/ECM-00001/checkout")

    assert response.status_code == 200
    assert response.get_json() == {
        "checkout_url": "https://geniuspay.ci/pay/abc123",
        "transaction_reference": "GPAY-REF-001",
    }
    mock_initiate.assert_called_once_with(
        "ECM-00001", 75000, customer_phone="+237690000001", customer_name="Amina Njoya"
    )


@patch("app.routes.orders.initiate_geniuspay_payment")
def test_checkout_returns_404_for_missing_order(mock_initiate, client):
    response = client.post("/orders/ECM-99999/checkout")

    assert response.status_code == 404
    mock_initiate.assert_not_called()


@patch("app.routes.orders.initiate_geniuspay_payment")
def test_checkout_returns_502_when_geniuspay_fails(mock_initiate, client):
    mock_initiate.side_effect = GeniusPayError("GeniusPay payment initiation failed")

    response = client.post("/orders/ECM-00001/checkout")

    assert response.status_code == 502
    assert response.get_json() == {"error": "payment initiation failed"}


def sync_batch(**overrides):
    order = {
        "order_id": "OFFLINE-0001",
        "customer_name": "Jean Foka",
        "customer_phone": "+237699999901",
        "neighborhood": "Bonapriso",
        "product_name": "Smartphone Tecno Spark",
        "category": "Electronics",
        "unit_price_fcfa": 75000,
        "quantity": 1,
    }
    order.update(overrides)
    return [order]


def test_sync_inserts_new_orders_and_reports_counts(client, app):
    payload = [
        sync_batch()[0],
        {
            "order_id": "OFFLINE-0002",
            "customer_name": "Marie Ekwalla",
            "customer_phone": "+237699999902",
            "neighborhood": "Deido",
            "product_name": "Smartphone Tecno Spark",
            "category": "Electronics",
            "unit_price_fcfa": 75000,
            "quantity": 1,
        },
    ]

    response = client.post("/orders/sync", json=payload)

    assert response.status_code == 200
    assert response.get_json() == {"synced": 2, "skipped": 0}

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE order_id IN ('OFFLINE-0001', 'OFFLINE-0002')"
    ).fetchone()["n"]
    assert count == 2
    order = conn.execute(
        "SELECT delivery_status, payment_status FROM orders WHERE order_id = 'OFFLINE-0001'"
    ).fetchone()
    assert order["delivery_status"] == "Pending"
    assert order["payment_status"] == "Unpaid"


def test_sync_is_idempotent_on_replayed_batch(client, app):
    """Simulates a field agent's app retrying the same sync after an
    internet blackout swallowed the first response -- the second POST of
    the identical batch must skip every already-synced order rather than
    inserting duplicates or splitting them into a second bucket.
    """
    payload = sync_batch(order_id="OFFLINE-0003", customer_phone="+237699999903")

    first = client.post("/orders/sync", json=payload)
    second = client.post("/orders/sync", json=payload)

    assert first.status_code == 200
    assert first.get_json() == {"synced": 1, "skipped": 0}
    assert second.status_code == 200
    assert second.get_json() == {"synced": 0, "skipped": 1}

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE order_id = 'OFFLINE-0003'"
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
            "order_id": "OFFLINE-0004",
            "customer_name": "Paul Biya Jr",
            "customer_phone": "+237699999904",
            "neighborhood": "Akwa",
            "product_name": "Smartphone Tecno Spark",
            "category": "Electronics",
            "unit_price_fcfa": 75000,
            "quantity": 1,
        },
        {
            "order_id": "OFFLINE-0005",
            "customer_name": "Paul Biya Jr",
            "customer_phone": "+237699999904",
            "neighborhood": "Akwa",
            "product_name": "Smartphone Tecno Spark",
            "category": "Electronics",
            "unit_price_fcfa": 75000,
            "quantity": 1,
        },
    ]

    response = client.post("/orders/sync", json=payload)

    assert response.get_json() == {"synced": 2, "skipped": 0}

    conn = get_connection(app.config["DATABASE_PATH"])
    customer_count = conn.execute(
        "SELECT COUNT(*) AS n FROM customers WHERE phone_number = '+237699999904'"
    ).fetchone()["n"]
    assert customer_count == 1


def test_sync_reuses_shared_address_across_different_customers_in_same_neighborhood(client, app):
    """Two DIFFERENT customers ordering to the same neighborhood must reuse
    one shared address row (a logistics reference point, not owned by a
    single customer), not each mint their own copy of it -- the anti-pattern
    this fix removes. conftest already seeds an Akwa/Douala address, so this
    proves the sync path finds and reuses that same row.
    """
    payload = [
        {
            "order_id": "OFFLINE-0010",
            "customer_name": "Grace Fotso",
            "customer_phone": "+237699999910",
            "neighborhood": "Akwa",
            "city": "Douala",
            "product_name": "Smartphone Tecno Spark",
            "category": "Electronics",
            "unit_price_fcfa": 75000,
            "quantity": 1,
        },
        {
            "order_id": "OFFLINE-0011",
            "customer_name": "Herve Talla",
            "customer_phone": "+237699999911",
            "neighborhood": "Akwa",
            "city": "Douala",
            "product_name": "Smartphone Tecno Spark",
            "category": "Electronics",
            "unit_price_fcfa": 75000,
            "quantity": 1,
        },
    ]

    response = client.post("/orders/sync", json=payload)

    assert response.get_json() == {"synced": 2, "skipped": 0}

    conn = get_connection(app.config["DATABASE_PATH"])
    address_count = conn.execute(
        "SELECT COUNT(*) AS n FROM addresses WHERE neighborhood = 'Akwa'"
    ).fetchone()["n"]
    assert address_count == 1

    address_ids = {
        row["address_id"]
        for row in conn.execute(
            "SELECT address_id FROM orders WHERE order_id IN ('OFFLINE-0010', 'OFFLINE-0011')"
        )
    }
    assert address_ids == {1}


def test_sync_returns_400_for_non_array_payload(client):
    response = client.post("/orders/sync", json={"not": "a list"})

    assert response.status_code == 400


def test_sync_returns_400_for_order_missing_required_field(client):
    response = client.post("/orders/sync", json=[{"order_id": "OFFLINE-0006"}])

    assert response.status_code == 400


def test_create_order_with_existing_customer_and_product_returns_201(client, app):
    response = client.post("/orders", json={
        "customer_id": 1,
        "address_id": 1,
        "product_id": 1,
        "quantity": 2,
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body["order_id"] == "ECM-00003"
    assert body["quantity"] == 2
    assert body["unit_price_fcfa"] == 75000
    assert body["delivery_status"] == "Pending"

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE order_id = 'ECM-00003'"
    ).fetchone()["n"]
    assert count == 1


def test_create_order_with_new_customer_and_new_product_returns_201(client):
    response = client.post("/orders", json={
        "customer_name": "Divine Talla",
        "customer_phone": "+237677000001",
        "neighborhood": "Bastos",
        "city": "Yaounde",
        "product_name": "LED Television 32-inch",
        "category": "Electronics",
        "unit_price_fcfa": 120000,
        "quantity": 1,
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body["customer_name"] == "Divine Talla"
    assert body["neighborhood"] == "Bastos"
    assert body["product_name"] == "LED Television 32-inch"


def test_create_order_returns_400_for_invalid_quantity(client):
    response = client.post("/orders", json={
        "customer_id": 1,
        "address_id": 1,
        "product_id": 1,
        "quantity": 0,
    })

    assert response.status_code == 400


def test_create_order_returns_400_for_missing_field(client):
    response = client.post("/orders", json={"customer_id": 1, "address_id": 1})

    assert response.status_code == 400


def test_update_order_tracking_updates_delivery_status(client, app):
    response = client.put("/orders/ECM-00001", json={"delivery_status": "Delivered"})

    assert response.status_code == 200
    assert response.get_json()["delivery_status"] == "Delivered"

    conn = get_connection(app.config["DATABASE_PATH"])
    order = conn.execute(
        "SELECT delivery_status FROM orders WHERE order_id = 'ECM-00001'"
    ).fetchone()
    assert order["delivery_status"] == "Delivered"


def test_update_order_tracking_returns_400_for_invalid_status(client):
    response = client.put("/orders/ECM-00001", json={"delivery_status": "InTransit"})

    assert response.status_code == 400


def test_update_order_tracking_returns_404_for_unknown_order(client):
    response = client.put("/orders/ECM-99999", json={"delivery_status": "Shipped"})

    assert response.status_code == 404


def test_delete_order_removes_it(client, app):
    response = client.delete("/orders/ECM-00002")

    assert response.status_code == 204

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE order_id = 'ECM-00002'"
    ).fetchone()["n"]
    assert count == 0


def test_delete_order_returns_404_for_unknown_order(client):
    response = client.delete("/orders/ECM-99999")

    assert response.status_code == 404


def test_delete_order_returns_409_when_payments_exist(client, app):
    conn = get_connection(app.config["DATABASE_PATH"])
    conn.execute(
        "INSERT INTO payments (order_id, provider, external_transaction_id, amount_fcfa, status) "
        "VALUES ('ECM-00001', 'geniuspay', 'MTX-DEL-001', 75000, 'Successful')"
    )
    conn.commit()

    response = client.delete("/orders/ECM-00001")

    assert response.status_code == 409

    count = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE order_id = 'ECM-00001'"
    ).fetchone()["n"]
    assert count == 1
