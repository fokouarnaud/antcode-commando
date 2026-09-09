from unittest.mock import patch

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
def test_checkout_returns_checkout_url_on_success(mock_initiate, client):
    mock_initiate.return_value = "https://geniuspay.ci/pay/abc123"

    response = client.post("/orders/1/checkout")

    assert response.status_code == 200
    assert response.get_json() == {"checkout_url": "https://geniuspay.ci/pay/abc123"}
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
