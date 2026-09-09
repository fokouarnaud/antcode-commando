import os

import pytest

from app import create_app
from app.config.database import get_connection, init_db

WEBHOOK_SECRET = "test-momo-secret"
ORANGE_WEBHOOK_SECRET = "test-orange-secret"
CAMPAY_WEBHOOK_SECRET = "test-campay-secret"
SMOBILPAY_WEBHOOK_SECRET = "test-smobilpay-secret"
DEFAULT_AGGREGATOR = "campay"

os.environ["DB_ENGINE"] = "sqlite"


@pytest.fixture
def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    init_db(conn)
    conn.execute(
        "INSERT INTO customers (full_name, phone_number) VALUES (?, ?)",
        ("Amina Njoya", "+237690000001"),
    )
    conn.execute(
        "INSERT INTO addresses (customer_id, neighborhood, city) VALUES (1, 'Akwa', 'Douala')"
    )
    conn.execute(
        "INSERT INTO orders (customer_id, address_id, customer_neighborhood, delivery_status, "
        "payment_status, external_ref) VALUES (1, 1, 'Akwa', 'Pending', 'Pending', 'ECM-00001')"
    )
    conn.execute(
        "INSERT INTO orders (customer_id, address_id, customer_neighborhood, delivery_status, "
        "payment_status, external_ref) VALUES (1, 1, 'Akwa', 'Delayed', 'Pending', 'ECM-00002')"
    )
    conn.commit()
    conn.close()

    return create_app(
        db_path=db_path,
        webhook_secret=WEBHOOK_SECRET,
        orange_webhook_secret=ORANGE_WEBHOOK_SECRET,
        campay_webhook_secret=CAMPAY_WEBHOOK_SECRET,
        smobilpay_webhook_secret=SMOBILPAY_WEBHOOK_SECRET,
        default_aggregator=DEFAULT_AGGREGATOR,
    )


@pytest.fixture
def client(app):
    return app.test_client()
