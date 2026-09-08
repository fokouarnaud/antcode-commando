import hmac

from flask import Blueprint, current_app, jsonify, request

from app import get_db
from app.services.webhooks import OrderNotFoundError, process_momo_callback

webhooks_bp = Blueprint("webhooks", __name__)


@webhooks_bp.route("/webhook/momo", methods=["POST"])
def momo_webhook():
    token = request.headers.get("X-Webhook-Token", "")
    expected = current_app.config["MOMO_WEBHOOK_SECRET"]
    if not hmac.compare_digest(token, expected):
        return jsonify({"error": "invalid token"}), 401

    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        result = process_momo_callback(conn, payload)
    except OrderNotFoundError:
        return jsonify({"error": "order not found"}), 404

    return jsonify(result), 200
