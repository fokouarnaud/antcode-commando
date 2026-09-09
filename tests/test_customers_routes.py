from app.config.database import get_connection


def test_create_customer_returns_201_with_address(client):
    response = client.post("/customers", json={
        "full_name": "Steve Ateba",
        "phone_number": "+237677123456",
        "neighborhood": "Bonapriso",
        "city": "Douala",
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body["full_name"] == "Steve Ateba"
    assert len(body["addresses"]) == 1
    assert body["addresses"][0]["neighborhood"] == "Bonapriso"


def test_create_customer_returns_400_for_invalid_phone_format(client):
    response = client.post("/customers", json={
        "full_name": "Bad Phone",
        "phone_number": "0677123456",
        "neighborhood": "Bonapriso",
        "city": "Douala",
    })

    assert response.status_code == 400


def test_create_customer_returns_409_for_duplicate_phone(client):
    payload = {
        "full_name": "First Customer",
        "phone_number": "+237677999999",
        "neighborhood": "Akwa",
        "city": "Douala",
    }
    client.post("/customers", json=payload)

    response = client.post("/customers", json={**payload, "full_name": "Second Customer"})

    assert response.status_code == 409


def test_get_customer_returns_customer_with_addresses(client):
    response = client.get("/customers/1")

    assert response.status_code == 200
    body = response.get_json()
    assert body["customer_id"] == 1
    assert body["phone_number"] == "+237690000001"
    assert body["addresses"][0]["neighborhood"] == "Akwa"


def test_get_customer_returns_404_for_unknown_id(client):
    response = client.get("/customers/9999")

    assert response.status_code == 404


def test_update_customer_changes_name_and_address(client):
    response = client.put("/customers/1", json={
        "full_name": "Amina Njoya Kamdem",
        "neighborhood": "Bastos",
        "city": "Yaounde",
    })

    assert response.status_code == 200
    body = response.get_json()
    assert body["full_name"] == "Amina Njoya Kamdem"
    assert body["addresses"][0]["neighborhood"] == "Bastos"


def test_update_customer_returns_409_for_phone_taken_by_another_customer(client):
    client.post("/customers", json={
        "full_name": "Other Customer",
        "phone_number": "+237677888888",
        "neighborhood": "Akwa",
        "city": "Douala",
    })

    response = client.put("/customers/1", json={"phone_number": "+237677888888"})

    assert response.status_code == 409


def test_update_customer_returns_404_for_unknown_id(client):
    response = client.put("/customers/9999", json={"full_name": "Doesn't matter"})

    assert response.status_code == 404


def test_delete_customer_returns_409_when_customer_has_orders(client, app):
    response = client.delete("/customers/1")

    assert response.status_code == 409

    conn = get_connection(app.config["DATABASE_PATH"])
    count = conn.execute("SELECT COUNT(*) AS n FROM customers WHERE customer_id = 1").fetchone()["n"]
    assert count == 1


def test_delete_customer_removes_customer_without_orders(client):
    created = client.post("/customers", json={
        "full_name": "No Orders Yet",
        "phone_number": "+237677777777",
        "neighborhood": "Akwa",
        "city": "Douala",
    }).get_json()

    response = client.delete(f"/customers/{created['customer_id']}")

    assert response.status_code == 204


def test_delete_customer_returns_404_for_unknown_id(client):
    response = client.delete("/customers/9999")

    assert response.status_code == 404
