def test_openapi_json_documents_webhook_and_order_lookup_paths(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.get_json()
    assert spec["info"]["title"]
    assert set(spec["paths"]) == {
        "/webhook/{provider}",
        "/orders",
        "/orders/{id_or_ref}",
        "/orders/{order_id}",
        "/orders/sync",
        "/orders/{order_id}/checkout",
        "/products",
        "/products/{product_id}",
        "/customers",
        "/customers/{customer_id}",
        "/payments",
        "/payments/{external_transaction_id}",
        "/payments/{payment_id}",
    }
    assert "post" in spec["paths"]["/webhook/{provider}"]
    assert "get" in spec["paths"]["/orders"]
    assert "post" in spec["paths"]["/orders"]
    assert "get" in spec["paths"]["/orders/{id_or_ref}"]
    assert {"put", "delete"} <= set(spec["paths"]["/orders/{order_id}"])
    assert "get" in spec["paths"]["/products"]
    assert "post" in spec["paths"]["/products"]
    assert {"put", "delete"} <= set(spec["paths"]["/products/{product_id}"])
    assert "post" in spec["paths"]["/customers"]
    assert {"get", "put", "delete"} <= set(spec["paths"]["/customers/{customer_id}"])
    assert {"get", "post"} <= set(spec["paths"]["/payments"])
    assert "get" in spec["paths"]["/payments/{external_transaction_id}"]
    assert {"put", "delete"} <= set(spec["paths"]["/payments/{payment_id}"])


def test_docs_route_serves_html_referencing_the_openapi_spec(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert b'data-url="/openapi.json"' in response.data
