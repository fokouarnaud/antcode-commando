"""Dev entry point: `python run.py`. Reads DATABASE_PATH / MOMO_WEBHOOK_SECRET /
ORANGE_WEBHOOK_SECRET / CAMPAY_WEBHOOK_SECRET / SMOBILPAY_WEBHOOK_SECRET /
DEFAULT_AGGREGATOR from the environment so webhook secrets are never
hardcoded in source.

Example: run with Campay as the active aggregator on /webhook/aggregator:
    DEFAULT_AGGREGATOR=campay CAMPAY_WEBHOOK_SECRET=secret python run.py
"""

import os

from app import create_app

app = create_app(
    db_path=os.environ.get("DATABASE_PATH", "ecommerce.db"),
    webhook_secret=os.environ.get("MOMO_WEBHOOK_SECRET", "dev-secret-change-me"),
    orange_webhook_secret=os.environ.get("ORANGE_WEBHOOK_SECRET", "dev-secret-change-me"),
    campay_webhook_secret=os.environ.get("CAMPAY_WEBHOOK_SECRET", "dev-secret-change-me"),
    smobilpay_webhook_secret=os.environ.get("SMOBILPAY_WEBHOOK_SECRET", "dev-secret-change-me"),
    default_aggregator=os.environ.get("DEFAULT_AGGREGATOR", "campay"),
)

if __name__ == "__main__":
    app.run(debug=True)
