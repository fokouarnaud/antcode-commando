def test_openapi_json_documents_webhook_and_order_lookup_paths(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.get_json()
    assert spec["info"]["title"]
    assert set(spec["paths"]) == {
        "/webhook/momo",
        "/webhook/orange",
        "/orders",
        "/orders/{order_id}",
    }
    assert "post" in spec["paths"]["/webhook/momo"]
    assert "post" in spec["paths"]["/webhook/orange"]
    assert "get" in spec["paths"]["/orders"]
    assert "get" in spec["paths"]["/orders/{order_id}"]


def test_docs_route_serves_html_referencing_the_openapi_spec(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert b'data-url="/openapi.json"' in response.data
