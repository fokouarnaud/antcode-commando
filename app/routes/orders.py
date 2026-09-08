from flask import Blueprint, jsonify, request

from app import get_db
from app.services.orders import get_order_by_id, list_orders

orders_bp = Blueprint("orders", __name__)


@orders_bp.route("/orders/<int:order_id>", methods=["GET"])
def order_detail(order_id):
    order = get_order_by_id(get_db(), order_id)
    if order is None:
        return jsonify({"error": "order not found"}), 404
    return jsonify(dict(order)), 200


@orders_bp.route("/orders", methods=["GET"])
def order_list():
    orders = list_orders(
        get_db(),
        neighborhood=request.args.get("neighborhood"),
        status=request.args.get("status"),
    )
    return jsonify([dict(order) for order in orders]), 200
