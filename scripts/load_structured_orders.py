"""Runs the ecommerce_orders_raw -> structured tables pipeline against the
real project database (ecommerce.db), initializing the schema first if the
structured tables don't exist yet.
"""

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config.database import get_connection, init_db  # noqa: E402
from app.services.pipeline import load_structured_data  # noqa: E402

DB_PATH = REPO_ROOT / "ecommerce.db"


def main():
    conn = get_connection(str(DB_PATH))
    existing_tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "orders" not in existing_tables:
        init_db(conn)

    result = load_structured_data(conn)
    conn.close()
    print(f"Loaded structured data from ecommerce_orders_raw into {DB_PATH}: {result}")


if __name__ == "__main__":
    main()
