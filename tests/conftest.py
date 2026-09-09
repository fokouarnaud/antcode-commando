import os

import pytest

from app import create_app
from app.config.database import get_connection, init_db

WEBHOOK_SECRET = "test-momo-secret"
ORANGE_WEBHOOK_SECRET = "test-orange-secret"
CAMPAY_WEBHOOK_SECRET = "test-campay-secret"
SMOBILPAY_WEBHOOK_SECRET = "test-smobilpay-secret"
GENIUSPAY_WEBHOOK_SECRET = "test-geniuspay-secret"
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

    flask_app = create_app()
    # Inject isolated test config directly into app.config, overriding
    # whatever Config.from_object() loaded from the real environment --
    # the suite must never touch the production db file or real secrets.
    flask_app.config["DATABASE_PATH"] = db_path
    flask_app.config["MOMO_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    flask_app.config["ORANGE_WEBHOOK_SECRET"] = ORANGE_WEBHOOK_SECRET
    flask_app.config["CAMPAY_WEBHOOK_SECRET"] = CAMPAY_WEBHOOK_SECRET
    flask_app.config["SMOBILPAY_WEBHOOK_SECRET"] = SMOBILPAY_WEBHOOK_SECRET
    flask_app.config["GENIUSPAY_WEBHOOK_SECRET"] = GENIUSPAY_WEBHOOK_SECRET
    flask_app.config["DEFAULT_AGGREGATOR"] = DEFAULT_AGGREGATOR
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()
