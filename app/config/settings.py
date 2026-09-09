"""Centralized Flask config, loaded once via `app.config.from_object(
"app.config.settings.Config")` in create_app(). Every attribute here is
uppercase so Flask's from_object() picks it up (it only copies uppercase
class attributes).

This mirrors environment variables into app.config for route-level code
that runs inside a Flask request (current_app.config is available there).
It is a parallel, Flask-specific view of the same environment -- it does
NOT replace get_engine()/format_query()/get_connection() in
app/config/database.py, which read os.environ directly on every call
because they're also used by scripts/ that run with no Flask app context
at all (current_app would raise outside one).
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_ENGINE = os.environ.get("DB_ENGINE", "sqlite")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/ecommerce.db")
    DATABASE_URL = os.environ.get("DATABASE_URL")
    MOMO_WEBHOOK_SECRET = os.environ.get("MOMO_WEBHOOK_SECRET", "dev-secret-change-me")
    ORANGE_WEBHOOK_SECRET = os.environ.get("ORANGE_WEBHOOK_SECRET", "dev-secret-change-me")
    CAMPAY_WEBHOOK_SECRET = os.environ.get("CAMPAY_WEBHOOK_SECRET", "dev-secret-change-me")
    SMOBILPAY_WEBHOOK_SECRET = os.environ.get("SMOBILPAY_WEBHOOK_SECRET", "dev-secret-change-me")
    GENIUSPAY_WEBHOOK_SECRET = os.environ.get("GENIUSPAY_WEBHOOK_SECRET", "dev-secret-change-me")
    DEFAULT_AGGREGATOR = os.environ.get("DEFAULT_AGGREGATOR", "campay")
    GENIUSPAY_API_KEY = os.environ.get("GENIUSPAY_API_KEY", "pk_sandbox_mock")
    GENIUSPAY_API_SECRET = os.environ.get("GENIUSPAY_API_SECRET", "sk_sandbox_mock")
