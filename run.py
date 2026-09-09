"""Dev entry point: `python run.py`. All configuration is centralized in
app.config.settings.Config, which reads DATABASE_PATH / DB_ENGINE /
DATABASE_URL / MOMO_WEBHOOK_SECRET / ORANGE_WEBHOOK_SECRET /
CAMPAY_WEBHOOK_SECRET / SMOBILPAY_WEBHOOK_SECRET / GENIUSPAY_WEBHOOK_SECRET
from the environment, so webhook secrets are never hardcoded in source.

Example: run with Campay's webhook active on POST /webhook/campay:
    CAMPAY_WEBHOOK_SECRET=secret python run.py
"""

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
