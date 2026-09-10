from unittest.mock import Mock, patch

import pytest
import requests

from app import create_app
from app.services.geniuspay import GENIUSPAY_ENDPOINT, GeniusPayError, initiate_geniuspay_payment


@pytest.fixture
def app_context():
    app = create_app()
    app.config["GENIUSPAY_API_KEY"] = "test-api-key"
    app.config["GENIUSPAY_API_SECRET"] = "test-api-secret"
    with app.app_context():
        yield app


@patch("requests.post")
def test_initiate_geniuspay_payment_returns_checkout_url_and_reference_on_success(mock_post, app_context):
    mock_post.return_value = Mock(
        status_code=201,
        json=Mock(return_value={
            "checkout_url": "https://geniuspay.ci/pay/abc123",
            "reference": "GPAY-REF-001",
        }),
    )

    result = initiate_geniuspay_payment(
        42, 15000, customer_phone="+237690000001", customer_name="Amina Njoya"
    )

    assert result == {
        "checkout_url": "https://geniuspay.ci/pay/abc123",
        "transaction_reference": "GPAY-REF-001",
    }
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == GENIUSPAY_ENDPOINT
    assert kwargs["headers"]["X-API-Key"] == "test-api-key"
    assert kwargs["headers"]["X-API-Secret"] == "test-api-secret"
    assert kwargs["json"]["amount"] == 15000
    assert kwargs["json"]["description"] == "Commande #42"
    assert kwargs["json"]["metadata"] == {"order_id": 42}
    assert kwargs["json"]["customer"] == {"name": "Amina Njoya", "phone": "+237690000001"}


@patch("requests.post")
def test_initiate_geniuspay_payment_omits_customer_field_when_not_given(mock_post, app_context):
    mock_post.return_value = Mock(
        status_code=201,
        json=Mock(return_value={"checkout_url": "https://geniuspay.ci/pay/xyz"}),
    )

    initiate_geniuspay_payment(7, 5000)

    _, kwargs = mock_post.call_args
    assert "customer" not in kwargs["json"]


@patch("requests.post")
def test_initiate_geniuspay_payment_customer_object_only_includes_given_fields(mock_post, app_context):
    mock_post.return_value = Mock(
        status_code=201,
        json=Mock(return_value={"checkout_url": "https://geniuspay.ci/pay/xyz"}),
    )

    initiate_geniuspay_payment(7, 5000, customer_phone="+237690000002")

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["customer"] == {"phone": "+237690000002"}


@patch("requests.post")
def test_initiate_geniuspay_payment_raises_on_non_201_status(mock_post, app_context):
    mock_post.return_value = Mock(status_code=400, text="bad request")

    with pytest.raises(GeniusPayError):
        initiate_geniuspay_payment(42, 15000)


@patch("requests.post")
def test_initiate_geniuspay_payment_raises_when_checkout_url_missing(mock_post, app_context):
    mock_post.return_value = Mock(status_code=201, json=Mock(return_value={}), text="{}")

    with pytest.raises(GeniusPayError):
        initiate_geniuspay_payment(42, 15000)


@patch("requests.post")
def test_initiate_geniuspay_payment_falls_back_to_payment_url_when_checkout_url_missing(
    mock_post, app_context
):
    """Some GeniusPay payment methods return `payment_url` instead of
    `checkout_url` -- both must resolve to the same result field.
    """
    mock_post.return_value = Mock(
        status_code=201,
        json=Mock(return_value={
            "payment_url": "https://geniuspay.ci/pay/via-payment-url",
            "reference": "GPAY-REF-002",
        }),
    )

    result = initiate_geniuspay_payment(42, 15000)

    assert result == {
        "checkout_url": "https://geniuspay.ci/pay/via-payment-url",
        "transaction_reference": "GPAY-REF-002",
    }


@patch("requests.post")
def test_initiate_geniuspay_payment_prefers_checkout_url_over_payment_url_when_both_present(
    mock_post, app_context
):
    mock_post.return_value = Mock(
        status_code=201,
        json=Mock(return_value={
            "checkout_url": "https://geniuspay.ci/pay/checkout",
            "payment_url": "https://geniuspay.ci/pay/payment",
            "reference": "GPAY-REF-003",
        }),
    )

    result = initiate_geniuspay_payment(42, 15000)

    assert result["checkout_url"] == "https://geniuspay.ci/pay/checkout"


@patch("requests.post")
def test_initiate_geniuspay_payment_raises_on_network_error(mock_post, app_context):
    mock_post.side_effect = requests.ConnectionError("boom")

    with pytest.raises(GeniusPayError):
        initiate_geniuspay_payment(42, 15000)
