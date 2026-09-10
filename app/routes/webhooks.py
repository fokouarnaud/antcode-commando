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
        "signature_header": "X-GeniusPay-Signature",
        "event_header": "X-GeniusPay-Event",
    },
}


def _has_valid_signature(secret, message, signature):
    if not signature:
        return False
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _webhook(provider):
    config = _PROVIDER_CONFIG.get(provider)
    if config is None:
        return jsonify({"error": f"unknown provider: {provider}"}), 500

    secret = current_app.config[config["secret_key"]]
    signature = request.headers.get(config["signature_header"], "")

    if not _has_valid_signature(secret, request.get_data(), signature):
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


@webhooks_bp.route("/webhook/<provider>", methods=["POST"])
def provider_webhook(provider):
    """Single dynamic entry point for every provider's payment callback --
    the provider name comes straight from the URL and is handed to
    _webhook(), which resolves that provider's own secret, signature
    header, and (for GeniusPay) event header from _PROVIDER_CONFIG. Every
    provider, GeniusPay included, signs the raw request body alone.
    Adding a new provider only means adding an entry to _PROVIDER_CONFIG --
    no new route or view function.
    """
    return _webhook(provider)


@webhooks_bp.route("/webhook/simulate-carrier", methods=["POST"])
def simulate_carrier_webhook():
    """DEV-ONLY convenience route: skips HMAC signature verification
    entirely so a momo/orange callback can be fired from the Scalar UI
    (/docs) without hand-computing a raw-body signature -- every request
    here is treated as a successful transaction. Gated on Flask's debug
    flag (404s unless the app runs with debug=True, e.g. `python run.py`),
    so a production deployment that doesn't opt into debug mode never
    exposes it. Never enable app.debug in production.
    """
    if not current_app.debug:
        return jsonify({"error": "not found"}), 404

    body = request.get_json(silent=True) or {}
    provider = body.get("provider")
    if provider not in ("momo", "orange"):
        return jsonify({"error": "provider must be 'momo' or 'orange'"}), 400

    payload = {
        "provider": provider,
        "order_id": body.get("order_id"),
        "external_transaction_id": body.get("external_transaction_id"),
        "amount_fcfa": body.get("amount"),
        "status": "SUCCESSFUL",
    }

    conn = get_db()
    try:
        result = process_momo_callback(conn, payload)
    except OrderNotFoundError:
        return jsonify({"error": "order not found"}), 404

    return jsonify(result), 200
