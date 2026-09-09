import math

from flask import Blueprint, jsonify, request

from app import get_db
from app.services.geniuspay import GeniusPayError, initiate_geniuspay_payment
from app.services.orders import (
    get_order_by_external_ref,
    get_order_by_id,
    get_order_by_transaction_reference,
    get_order_checkout_details,
    list_orders,
    sync_offline_orders,
)

orders_bp = Blueprint("orders", __name__)

_EXTERNAL_REF_PREFIX = "ECM-"


@orders_bp.route("/orders/<id_or_ref>", methods=["GET"])
def order_detail(id_or_ref):
    """Accepts either the internal numeric order_id, the sequential
    external_ref (e.g. "ECM-00001"), or a payment's transaction reference
    (e.g. a GeniusPay/MoMo/Orange external_transaction_id) -- whichever
    one the caller actually has on hand.
    """
    conn = get_db()
    if id_or_ref.isdigit():
        order = get_order_by_id(conn, int(id_or_ref))
    elif id_or_ref.startswith(_EXTERNAL_REF_PREFIX):
        order = get_order_by_external_ref(conn, id_or_ref)
    else:
        order = get_order_by_transaction_reference(conn, id_or_ref)

    if order is None:
        return jsonify({"error": "order not found"}), 404
    return jsonify(dict(order)), 200


@orders_bp.route("/orders", methods=["GET"])
def order_list():
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = max(request.args.get("per_page", default=20, type=int) or 20, 1)

    orders, total_records = list_orders(
        get_db(),
        neighborhood=request.args.get("neighborhood"),
        status=request.args.get("status"),
        page=page,
        per_page=per_page,
    )

    return jsonify({
        "data": [dict(order) for order in orders],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_records": total_records,
            "total_pages": math.ceil(total_records / per_page),
        },
    }), 200


@orders_bp.route("/orders/sync", methods=["POST"])
def orders_sync():
    payload = request.get_json(silent=True)
    if not isinstance(payload, list):
        return jsonify({"error": "expected a JSON array of orders"}), 400

    try:
        result = sync_offline_orders(get_db(), payload)
    except KeyError as exc:
        return jsonify({"error": f"missing required field: {exc}"}), 400

    return jsonify(result), 200


@orders_bp.route("/orders/<int:order_id>/checkout", methods=["POST"])
def order_checkout(order_id):
    details = get_order_checkout_details(get_db(), order_id)
    if details is None:
        return jsonify({"error": "order not found"}), 404

    try:
        result = initiate_geniuspay_payment(
            details["order_id"],
            details["amount_fcfa"],
            customer_phone=details["customer_phone"],
            customer_name=details["customer_name"],
        )
    except GeniusPayError:
        return jsonify({"error": "payment initiation failed"}), 502

    return jsonify(result), 200
