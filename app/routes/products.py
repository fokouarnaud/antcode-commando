import math

from flask import Blueprint, jsonify, request

from app import get_db
from app.config.database import integrity_errors
from app.services.products import (
    ProductValidationError,
    create_product,
    delete_product,
    get_product_by_id,
    list_products,
    update_product,
)

products_bp = Blueprint("products", __name__)


@products_bp.route("/products", methods=["GET"])
def product_list():
    page = max(request.args.get("page", default=1, type=int), 1)
    per_page = min(max(request.args.get("per_page", default=20, type=int), 1), 100)

    products, total_records = list_products(get_db(), page=page, per_page=per_page)

    return jsonify({
        "data": [dict(product) for product in products],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_records": total_records,
            "total_pages": math.ceil(total_records / per_page),
        },
    }), 200


@products_bp.route("/products", methods=["POST"])
def product_create():
    payload = request.get_json(silent=True) or {}

    try:
        product = create_product(
            get_db(),
            payload.get("name"),
            payload.get("category"),
            payload.get("unit_price_fcfa"),
            payload.get("stock_quantity", 0),
        )
    except ProductValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(dict(product)), 201


@products_bp.route("/products/<int:product_id>", methods=["PUT"])
def product_update(product_id):
    payload = request.get_json(silent=True) or {}

    try:
        product = update_product(get_db(), product_id, payload)
    except ProductValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    if product is None:
        return jsonify({"error": "product not found"}), 404
    return jsonify(dict(product)), 200


@products_bp.route("/products/<int:product_id>", methods=["DELETE"])
def product_delete(product_id):
    conn = get_db()
    if get_product_by_id(conn, product_id) is None:
        return jsonify({"error": "product not found"}), 404

    try:
        delete_product(conn, product_id)
    except integrity_errors():
        conn.rollback()
        return jsonify({"error": "product has existing orders and cannot be deleted"}), 409

    return "", 204
