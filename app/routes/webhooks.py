import hashlib
import hmac

from flask import Blueprint, current_app, jsonify, request

from app import get_db
from app.services.webhooks import OrderNotFoundError, process_momo_callback

webhooks_bp = Blueprint("webhooks", __name__)

_PROVIDER_CONFIG = {
    "momo": {
        "secret_key": "MOMO_WEBHOOK_SECRET",
        "signature_header": "X-Momo-Signature",
    },
    "orange": {
        "secret_key": "ORANGE_WEBHOOK_SECRET",
        "signature_header": "X-Orange-Signature",
    },
    "campay": {
        "secret_key": "CAMPAY_WEBHOOK_SECRET",
        "signature_header": "X-Campay-Signature",
    },
    "smobilpay": {
        "secret_key": "SMOBILPAY_WEBHOOK_SECRET",
        "signature_header": "X-Smobilpay-Signature",
    },
}


def _has_valid_signature(secret, raw_body, signature):
    if not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _webhook(provider):
    config = _PROVIDER_CONFIG.get(provider)
    if config is None:
        return jsonify({"error": f"unknown aggregator: {provider}"}), 500

    secret = current_app.config[config["secret_key"]]
    signature = request.headers.get(config["signature_header"], "")
    raw_body = request.get_data()

    if not _has_valid_signature(secret, raw_body, signature):
        return jsonify({"error": "invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    payload["provider"] = provider

    conn = get_db()
    try:
        result = process_momo_callback(conn, payload)
    except OrderNotFoundError:
        return jsonify({"error": "order not found"}), 404

    return jsonify(result), 200


@webhooks_bp.route("/webhook/momo", methods=["POST"])
def momo_webhook():
    return _webhook("momo")


@webhooks_bp.route("/webhook/orange", methods=["POST"])
def orange_webhook():
    return _webhook("orange")


@webhooks_bp.route("/webhook/aggregator", methods=["POST"])
def aggregator_webhook():
    """Routes to whichever aggregator (Campay, Smobilpay, ...) is configured
    as DEFAULT_AGGREGATOR, so adding a new aggregator only means adding an
    entry to _PROVIDER_CONFIG -- no new route or view function.
    """
    return _webhook(current_app.config["DEFAULT_AGGREGATOR"])
