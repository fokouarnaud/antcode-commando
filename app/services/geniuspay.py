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
    if customer_phone:
        payload["customer_phone"] = customer_phone
    if customer_name:
        payload["customer_name"] = customer_name

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

    checkout_url = response.json().get("checkout_url")
    if not checkout_url:
        logger.error("GeniusPay response missing checkout_url for order %s", order_id)
        raise GeniusPayError("GeniusPay payment initiation failed")

    return checkout_url
