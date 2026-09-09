"""Dev entry point: `python run.py`. Reads DATABASE_PATH / MOMO_WEBHOOK_SECRET /
ORANGE_WEBHOOK_SECRET from the environment so webhook secrets are never
hardcoded in source.
"""

import os

from app import create_app

app = create_app(
    db_path=os.environ.get("DATABASE_PATH", "ecommerce.db"),
    webhook_secret=os.environ.get("MOMO_WEBHOOK_SECRET", "dev-secret-change-me"),
    orange_webhook_secret=os.environ.get("ORANGE_WEBHOOK_SECRET", "dev-secret-change-me"),
)

if __name__ == "__main__":
    app.run(debug=True)
