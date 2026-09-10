import math

from flask import Blueprint, jsonify, request

from app import get_db
from app.services.payments import (
    DuplicatePaymentError,
    PaymentValidationError,
    create_payment,
    delete_payment,
    get_payment_by_transaction_id,
    list_payments,
    update_payment,
)
from app.services.webhooks import OrderNotFoundError

payments_bp = Blueprint("payments", __name__)


@payments_bp.route("/payments", methods=["GET"])
def payment_list():
    page = max(request.args.get("page", default=1, type=int), 1)
    per_page = min(max(request.args.get("per_page", default=20, type=int), 1), 100)

    payments, total_records = list_payments(get_db(), page=page, per_page=per_page)

    return jsonify({
        "data": [dict(payment) for payment in payments],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_records": total_records,
            "total_pages": math.ceil(total_records / per_page),
        },
    }), 200


@payments_bp.route("/payments", methods=["POST"])
def payment_create():
    payload = request.get_json(silent=True) or {}

    try:
        payment = create_payment(
            get_db(),
            payload.get("order_id"),
            payload.get("provider"),
            payload.get("external_transaction_id"),
            payload.get("amount_fcfa"),
            payload.get("status", "pending"),
        )
    except PaymentValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except OrderNotFoundError:
        return jsonify({"error": "order not found"}), 404
    except DuplicatePaymentError:
        return jsonify({
            "error": "a payment with this provider and external_transaction_id already exists"
        }), 409

    return jsonify(dict(payment)), 201


@payments_bp.route("/payments/<external_transaction_id>", methods=["GET"])
def payment_detail(external_transaction_id):
    payment = get_payment_by_transaction_id(get_db(), external_transaction_id)
    if payment is None:
        return jsonify({"error": "payment not found"}), 404
    return jsonify(payment), 200


@payments_bp.route("/payments/<int:payment_id>", methods=["PUT"])
def payment_update(payment_id):
    payload = request.get_json(silent=True) or {}

    try:
        payment = update_payment(get_db(), payment_id, payload)
    except PaymentValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except DuplicatePaymentError:
        return jsonify({
            "error": "a payment with this provider and external_transaction_id already exists"
        }), 409

    if payment is None:
        return jsonify({"error": "payment not found"}), 404
    return jsonify(dict(payment)), 200


@payments_bp.route("/payments/<int:payment_id>", methods=["DELETE"])
def payment_delete(payment_id):
    deleted = delete_payment(get_db(), payment_id)
    if not deleted:
        return jsonify({"error": "payment not found"}), 404
    return "", 204
