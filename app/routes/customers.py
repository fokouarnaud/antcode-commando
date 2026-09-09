from flask import Blueprint, jsonify, request

from app import get_db
from app.config.database import integrity_errors
from app.services.customers import (
    CustomerValidationError,
    DuplicatePhoneError,
    create_customer_with_address,
    delete_customer,
    get_customer,
    update_customer,
)

customers_bp = Blueprint("customers", __name__)


@customers_bp.route("/customers", methods=["POST"])
def customer_create():
    payload = request.get_json(silent=True) or {}

    try:
        customer = create_customer_with_address(
            get_db(),
            payload.get("full_name"),
            payload.get("phone_number"),
            payload.get("neighborhood"),
            payload.get("city"),
            payload.get("street_details"),
        )
    except CustomerValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except DuplicatePhoneError:
        return jsonify({"error": "phone_number is already registered"}), 409

    return jsonify(customer), 201


@customers_bp.route("/customers/<int:customer_id>", methods=["GET"])
def customer_detail(customer_id):
    customer = get_customer(get_db(), customer_id)
    if customer is None:
        return jsonify({"error": "customer not found"}), 404
    return jsonify(customer), 200


@customers_bp.route("/customers/<int:customer_id>", methods=["PUT"])
def customer_update(customer_id):
    payload = request.get_json(silent=True) or {}

    try:
        customer = update_customer(get_db(), customer_id, payload)
    except CustomerValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except DuplicatePhoneError:
        return jsonify({"error": "phone_number is already registered"}), 409

    if customer is None:
        return jsonify({"error": "customer not found"}), 404
    return jsonify(customer), 200


@customers_bp.route("/customers/<int:customer_id>", methods=["DELETE"])
def customer_delete(customer_id):
    conn = get_db()
    try:
        deleted = delete_customer(conn, customer_id)
    except integrity_errors():
        return jsonify({"error": "customer has existing orders and cannot be deleted"}), 409

    if not deleted:
        return jsonify({"error": "customer not found"}), 404
    return "", 204
