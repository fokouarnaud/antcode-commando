import time

from app.config.database import get_connection


def test_create_product_returns_201(client):
    response = client.post("/products", json={
        "name": "Power Bank 20000mAh",
        "category": "Electronics",
        "unit_price_fcfa": 12000,
        "stock_quantity": 50,
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body["name"] == "Power Bank 20000mAh"
    assert body["unit_price_fcfa"] == 12000
    assert body["stock_quantity"] == 50


def test_create_product_returns_400_for_missing_name(client):
    response = client.post("/products", json={"category": "Electronics", "unit_price_fcfa": 1000})

    assert response.status_code == 400


def test_create_product_returns_400_for_non_positive_price(client):
    response = client.post("/products", json={
        "name": "Broken", "category": "Electronics", "unit_price_fcfa": 0,
    })

    assert response.status_code == 400


def test_list_products_paginates(client):
    for i in range(3):
        client.post("/products", json={
            "name": f"Item {i}", "category": "Fashion", "unit_price_fcfa": 5000,
        })

    response = client.get("/products?page=1&per_page=2")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    # conftest already seeds one product, plus the 3 created above.
    assert body["pagination"]["total_records"] == 4
    assert body["pagination"]["total_pages"] == 2


def test_list_products_respects_explicit_per_page_of_five(client):
    """Regression test: per_page must be honored as given, not silently
    replaced by the default of 20.
    """
    for i in range(5):
        client.post("/products", json={
            "name": f"Item {i}", "category": "Fashion", "unit_price_fcfa": 5000,
        })
    # conftest already seeds one product, plus the 5 created above = 6 total.

    response = client.get("/products?page=1&per_page=5")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 5
    assert body["pagination"] == {
        "page": 1,
        "per_page": 5,
        "total_records": 6,
        "total_pages": 2,
    }


def test_list_products_per_page_zero_is_clamped_to_one_not_reset_to_default(client):
    """per_page=0 must be clamped to the minimum of 1, not silently swapped
    for the default of 20 (the falsy-zero `x or default` bug).
    """
    response = client.get("/products?per_page=0")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 1
    assert body["pagination"]["per_page"] == 1


def test_update_product_changes_fields(client):
    created = client.post("/products", json={
        "name": "Old Name", "category": "Fashion", "unit_price_fcfa": 5000,
    }).get_json()

    response = client.put(f"/products/{created['product_id']}", json={
        "name": "New Name", "unit_price_fcfa": 6000,
    })

    assert response.status_code == 200
    body = response.get_json()
    assert body["name"] == "New Name"
    assert body["unit_price_fcfa"] == 6000


def test_update_product_refreshes_updated_at(client):
    created = client.post("/products", json={
        "name": "Old Name", "category": "Fashion", "unit_price_fcfa": 5000,
    }).get_json()
    original_updated_at = created["updated_at"]

    # updated_at has millisecond resolution -- without this, an insert
    # immediately followed by an update can land in the same millisecond
    # and produce an identical string, hiding a real change.
    time.sleep(0.01)
    response = client.put(f"/products/{created['product_id']}", json={"stock_quantity": 3})

    assert response.status_code == 200
    body = response.get_json()
    assert body["stock_quantity"] == 3
    assert body["updated_at"] > original_updated_at


def test_update_product_returns_404_for_unknown_id(client):
    response = client.put("/products/9999", json={"name": "Doesn't matter"})

    assert response.status_code == 404


def test_delete_product_removes_it(client):
    created = client.post("/products", json={
        "name": "Disposable", "category": "Fashion", "unit_price_fcfa": 1000,
    }).get_json()

    response = client.delete(f"/products/{created['product_id']}")

    assert response.status_code == 204


def test_delete_product_returns_404_for_unknown_id(client):
    response = client.delete("/products/9999")

    assert response.status_code == 404


def test_delete_product_returns_409_when_referenced_by_an_order(client, app):
    conn = get_connection(app.config["DATABASE_PATH"])
    product = conn.execute("SELECT product_id FROM products WHERE product_id = 1").fetchone()
    assert product is not None

    response = client.delete("/products/1")

    assert response.status_code == 409

    count = conn.execute("SELECT COUNT(*) AS n FROM products WHERE product_id = 1").fetchone()["n"]
    assert count == 1
