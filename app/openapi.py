"""Hand-authored OpenAPI 3.0 spec for the routes this app actually serves.

No codegen/reflection library is used -- the API surface is small (3 routes)
and a hand-written spec stays exactly in sync with what's reviewed in code
review, instead of depending on docstring-parsing magic.
"""

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "AntCode Commando - E-Commerce Logistics API",
        "version": "1.0.0",
        "description": (
            "Order lookups over the customer_neighborhood/delivery_status "
            "composite index, and the idempotent MTN MoMo / Orange Money "
            "payment webhook."
        ),
    },
    "components": {
        "securitySchemes": {
            "webhookToken": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Webhook-Token",
            }
        },
        "schemas": {
            "Order": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer"},
                    "customer_neighborhood": {"type": "string", "example": "Akwa"},
                    "delivery_status": {
                        "type": "string",
                        "example": "Delivered",
                        "enum": ["Pending", "In Transit", "Delivered", "Delayed", "Returned", "Cancelled"],
                    },
                    "payment_status": {
                        "type": "string",
                        "example": "Paid",
                        "enum": ["Pending", "Paid", "Failed"],
                    },
                    "external_ref": {"type": "string", "example": "ECM-00001"},
                },
            },
            "MomoCallback": {
                "type": "object",
                "required": ["order_id", "external_transaction_id", "amount_fcfa", "status"],
                "properties": {
                    "provider": {"type": "string", "example": "MTN MoMo"},
                    "order_id": {"type": "integer", "example": 1},
                    "external_transaction_id": {"type": "string", "example": "MOMO-TX-0001"},
                    "amount_fcfa": {"type": "integer", "example": 15000},
                    "status": {"type": "string", "enum": ["SUCCESSFUL", "FAILED"]},
                },
            },
        },
    },
    "paths": {
        "/orders": {
            "get": {
                "summary": "List orders, optionally filtered by neighborhood and/or delivery status",
                "description": (
                    "Backed by idx_orders_neighborhood_status: a neighborhood-only filter "
                    "uses the index's leading column, neighborhood+status uses the full "
                    "composite seek."
                ),
                "parameters": [
                    {
                        "name": "neighborhood",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "Akwa",
                    },
                    {
                        "name": "status",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "Delayed",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Matching orders",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Order"},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/orders/{order_id}": {
            "get": {
                "summary": "Fetch a single order by its internal id",
                "parameters": [
                    {
                        "name": "order_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "The order",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Order"}
                            }
                        },
                    },
                    "404": {"description": "No order with that id"},
                },
            }
        },
        "/webhook/momo": {
            "post": {
                "summary": "MTN MoMo / Orange Money payment callback",
                "description": (
                    "Idempotent: replaying the same external_transaction_id (e.g. after "
                    "an MTN retry following a 3G timeout in Douala/Yaounde) returns "
                    "already_processed instead of double-charging the order."
                ),
                "security": [{"webhookToken": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/MomoCallback"}
                        }
                    },
                },
                "responses": {
                    "200": {"description": "Processed, or already processed (idempotent replay)"},
                    "401": {"description": "Missing or invalid X-Webhook-Token"},
                    "404": {"description": "order_id does not exist"},
                },
            }
        },
    },
}
