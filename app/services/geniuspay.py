"""Initiates real checkout sessions against the GeniusPay Merchant API.

`order_id` is threaded into the request's `metadata` block so the
/webhook/geniuspay callback (app/routes/webhooks.py) can recover which
local order a GeniusPay payment notification belongs to.
"""

import logging

from flask import current_app

logger = logging.getLogger(__name__)

GENIUSPAY_ENDPOINT = "https://geniuspay.ci/api/v1/merchant/payments"


class GeniusPayError(Exception):
    pass


def initiate_geniuspay_payment(order_id, amount_fcfa, customer_phone=None, customer_name=None):
    import requests

    headers = {
        "X-API-Key": current_app.config["GENIUSPAY_API_KEY"],
        "X-API-Secret": current_app.config["GENIUSPAY_API_SECRET"],
    }
    payload = {
        "amount": amount_fcfa,
        "description": f"Commande #{order_id}",
        "metadata": {"order_id": order_id},
    }
    customer = {}
    if customer_name:
        customer["name"] = customer_name
    if customer_phone:
        customer["phone"] = customer_phone
    if customer:
        payload["customer"] = customer

    try:
        response = requests.post(GENIUSPAY_ENDPOINT, json=payload, headers=headers, timeout=10)
    except requests.RequestException:
        logger.exception("GeniusPay request failed for order %s", order_id)
        raise GeniusPayError("GeniusPay payment initiation failed")

    if response.status_code != 201:
        logger.error(
            "GeniusPay returned status %s for order %s: %s",
            response.status_code, order_id, getattr(response, "text", ""),
        )
        raise GeniusPayError("GeniusPay payment initiation failed")

    body = response.json()
    data = body.get("data") or {}
    checkout_url = data.get("checkout_url") or data.get("payment_url")
    if not checkout_url:
        logger.error(
            "GeniusPay response missing data.checkout_url/data.payment_url for order %s: %s",
            order_id, response.text,
        )
        raise GeniusPayError("GeniusPay payment initiation failed")

    return {
        "checkout_url": checkout_url,
        "transaction_reference": data.get("reference"),
    }
