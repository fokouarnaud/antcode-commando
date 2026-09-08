import hashlib
import hmac

from flask import Blueprint, current_app, jsonify, request

from app import get_db
from app.services.webhooks import OrderNotFoundError, process_momo_callback

webhooks_bp = Blueprint("webhooks", __name__)


def _has_valid_signature(secret, raw_body, signature):
    if not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@webhooks_bp.route("/webhook/momo", methods=["POST"])
def momo_webhook():
    secret = current_app.config["MOMO_WEBHOOK_SECRET"]
    signature = request.headers.get("X-Momo-Signature", "")
    raw_body = request.get_data()

    if not _has_valid_signature(secret, raw_body, signature):
        return jsonify({"error": "invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        result = process_momo_callback(conn, payload)
    except OrderNotFoundError:
        return jsonify({"error": "order not found"}), 404

    return jsonify(result), 200
