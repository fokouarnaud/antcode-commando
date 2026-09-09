import math

from flask import Blueprint, jsonify, request

from app import get_db
from app.services.geniuspay import GeniusPayError, initiate_geniuspay_payment
from app.services.orders import get_order_by_id, get_order_checkout_details, list_orders

orders_bp = Blueprint("orders", __name__)


@orders_bp.route("/orders/<int:order_id>", methods=["GET"])
def order_detail(order_id):
    order = get_order_by_id(get_db(), order_id)
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


@orders_bp.route("/orders/<int:order_id>/checkout", methods=["POST"])
def order_checkout(order_id):
    details = get_order_checkout_details(get_db(), order_id)
    if details is None:
        return jsonify({"error": "order not found"}), 404

    try:
        checkout_url = initiate_geniuspay_payment(
            details["order_id"],
            details["amount_fcfa"],
            customer_phone=details["customer_phone"],
            customer_name=details["customer_name"],
        )
    except GeniusPayError:
        return jsonify({"error": "payment initiation failed"}), 502

    return jsonify({"checkout_url": checkout_url}), 200
