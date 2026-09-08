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
    assert [o["external_ref"] for o in body] == ["ECM-00002"]


def test_list_orders_without_filters_returns_all_orders(client):
    response = client.get("/orders")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 2
