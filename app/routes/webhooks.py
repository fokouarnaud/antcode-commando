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
    "geniuspay": {
        "secret_key": "GENIUSPAY_WEBHOOK_SECRET",
        "signature_header": "X-Webhook-Signature",
        "timestamp_header": "X-Webhook-Timestamp",
        "event_header": "X-Webhook-Event",
    },
}


def _has_valid_signature(secret, message, signature):
    if not signature:
        return False
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _signed_message(config):
    """Builds the exact byte string each provider signs. GeniusPay's
    structural spec prepends f"{timestamp}." ahead of the raw body -- every
    other provider signs the raw body alone.
    """
    raw_body_string = request.get_data(as_text=True)
    if "timestamp_header" in config:
        timestamp = request.headers.get(config["timestamp_header"], "")
        return f"{timestamp}.{raw_body_string}".encode()
    return raw_body_string.encode()


def _webhook(provider):
    config = _PROVIDER_CONFIG.get(provider)
    if config is None:
        return jsonify({"error": f"unknown aggregator: {provider}"}), 500

    secret = current_app.config[config["secret_key"]]
    signature = request.headers.get(config["signature_header"], "")
    message = _signed_message(config)

    if not _has_valid_signature(secret, message, signature):
        return jsonify({"error": "invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    payload["provider"] = provider
    if "event_header" in config:
        payload["event"] = request.headers.get(config["event_header"], "")

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


@webhooks_bp.route("/webhooks/geniuspay", methods=["POST"])
def geniuspay_webhook():
    return _webhook("geniuspay")


@webhooks_bp.route("/webhook/aggregator", methods=["POST"])
def aggregator_webhook():
    """Routes to whichever aggregator (Campay, Smobilpay, ...) is configured
    as DEFAULT_AGGREGATOR, so adding a new aggregator only means adding an
    entry to _PROVIDER_CONFIG -- no new route or view function.
    """
    return _webhook(current_app.config["DEFAULT_AGGREGATOR"])
