"""AntCode Hub - E-Commerce Logistics Crisis
Generates ecommerce_orders_messy_data.csv (1000+ rows incl. deliberate
duplicates) using the exact generator supplied in the sprint brief, then
loads it into the relational SQLite database (ecommerce.db) via
parameterized raw SQL INSERTs so the system can be exercised at realistic
volume.

The generator (docx Code Block 2) deliberately injects missing values,
garbage date strings, negative quantities/prices, and duplicate rows so
Track 2 candidates have a genuinely messy dataset to load and query, not
just numbers in a table. clean_row() and insert_orders() below are the
part of this pipeline that has real behavior worth protecting with tests:
whitespace stripping and NaN -> NULL conversion decide what actually lands
in the database.
"""

import os
import pathlib
import random
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config.database import format_query, get_connection, get_engine  # noqa: E402

CSV_PATH = REPO_ROOT / "data" / "ecommerce_orders_messy_data.csv"
DB_PATH = pathlib.Path(
    os.environ.get("DATABASE_PATH", str(REPO_ROOT / "data" / "ecommerce.db"))
)

N_ROWS = 1000

NEIGHBORHOODS = [
    "Akwa", "Bonapriso", "Bastos", "Mendong", "Bonamoussadi",
    "Deido", "Nlongkak", "Biyem-Assi", "Ngousso", "New Bell",
]
NEIGHBORHOOD_VARIANTS = {
    n: [n, n.lower(), n.upper(), n + " ", n.replace("-", " ")] for n in NEIGHBORHOODS
}

PRODUCT_CATEGORIES = ["Electronics", "Fashion", "Home Goods", "Groceries", "Beauty", "Phones & Accessories"]
PAYMENT_METHODS = ["MTN MoMo", "Orange Money", "Cash on Delivery", "mtn momo", "ORANGE MONEY", "COD"]
PAYMENT_STATUS = ["Paid", "Pending", "Failed", "paid", "FAILED", np.nan]
DELIVERY_STATUS = ["Delivered", "In Transit", "Delayed", "Returned", "Cancelled", "delivered", "DELAYED"]

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y", "%d %b %Y", "%Y/%m/%d"]

COLUMNS = [
    "order_id", "customer_neighborhood", "order_date", "product_category",
    "quantity", "unit_price_fcfa", "payment_method", "payment_status",
    "delivery_status", "delivery_date", "delivery_duration_hours",
    "driver_id", "distance_km",
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ecommerce_orders_raw (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id                 TEXT,
    customer_neighborhood    TEXT,
    order_date               TEXT,
    product_category         TEXT,
    quantity                 INTEGER,
    unit_price_fcfa          REAL,
    payment_method           TEXT,
    payment_status           TEXT,
    delivery_status          TEXT,
    delivery_date            TEXT,
    delivery_duration_hours  REAL,
    driver_id                TEXT,
    distance_km              REAL
)
"""

CREATE_TABLE_SQL_POSTGRES = """
CREATE TABLE IF NOT EXISTS ecommerce_orders_raw (
    id                       SERIAL PRIMARY KEY,
    order_id                 TEXT,
    customer_neighborhood    TEXT,
    order_date               TEXT,
    product_category         TEXT,
    quantity                 INTEGER,
    unit_price_fcfa          REAL,
    payment_method           TEXT,
    payment_status           TEXT,
    delivery_status          TEXT,
    delivery_date            TEXT,
    delivery_duration_hours  REAL,
    driver_id                TEXT,
    distance_km              REAL
)
"""

INSERT_SQL = """
INSERT INTO ecommerce_orders_raw (
    order_id, customer_neighborhood, order_date, product_category,
    quantity, unit_price_fcfa, payment_method, payment_status,
    delivery_status, delivery_date, delivery_duration_hours,
    driver_id, distance_km
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def generate_messy_dataframe():
    """Verbatim generator from the sprint brief (docx Code Block 2),
    wrapped in a function so it can write into data/ and feed the loader
    below instead of running as a standalone top-level script.
    """
    np.random.seed(7)
    random.seed(7)

    start_date = datetime(2025, 3, 1)
    rows = []
    for i in range(1, N_ROWS + 1):
        neighborhood_clean = random.choice(NEIGHBORHOODS)
        neighborhood_display = random.choice(NEIGHBORHOOD_VARIANTS[neighborhood_clean])

        order_dt = start_date + timedelta(days=random.randint(0, 150), hours=random.randint(0, 23))
        fmt = random.choice(DATE_FORMATS)
        order_date_str = order_dt.strftime(fmt)

        delivery_hours = max(1, np.random.normal(loc=30, scale=18))
        delivery_dt = order_dt + timedelta(hours=delivery_hours)

        quantity = random.randint(1, 6)
        unit_price = round(np.random.normal(loc=15000, scale=8000), 0)
        distance_km = round(np.random.normal(loc=8, scale=4), 1)

        rows.append({
            "order_id": f"ECM-{i:05d}",
            "customer_neighborhood": neighborhood_display,
            "order_date": order_date_str,
            "product_category": random.choice(PRODUCT_CATEGORIES),
            "quantity": quantity,
            "unit_price_fcfa": unit_price,
            "payment_method": random.choice(PAYMENT_METHODS),
            "payment_status": random.choice(PAYMENT_STATUS),
            "delivery_status": random.choice(DELIVERY_STATUS),
            "delivery_date": delivery_dt.strftime(random.choice(DATE_FORMATS)),
            "delivery_duration_hours": round(delivery_hours, 1),
            "driver_id": f"DRV-{random.randint(1, 80):03d}",
            "distance_km": distance_km,
        })

    df = pd.DataFrame(rows)

    # 1. Missing values across several important columns
    for col, frac in [
        ("payment_status", 0.08),
        ("delivery_date", 0.05),
        ("unit_price_fcfa", 0.04),
        ("distance_km", 0.06),
        ("driver_id", 0.03),
    ]:
        idx = df.sample(frac=frac, random_state=hash(col) % 1000).index
        df.loc[idx, col] = np.nan

    # 2. Invalid / garbage date strings mixed in (manual entry errors)
    bad_date_idx = df.sample(n=20, random_state=11).index
    bad_date_values = ["31/02/2025", "0000-00-00", "N/A", "unknown", "13/13/2025"]
    df.loc[bad_date_idx, "order_date"] = [
        random.choice(bad_date_values) for _ in range(len(bad_date_idx))
    ]

    # 3. Negative / impossible quantities and prices
    neg_qty_idx = df.sample(n=12, random_state=12).index
    df.loc[neg_qty_idx, "quantity"] = -df.loc[neg_qty_idx, "quantity"].abs()

    neg_price_idx = df.sample(n=10, random_state=13).index
    df.loc[neg_price_idx, "unit_price_fcfa"] = -df.loc[neg_price_idx, "unit_price_fcfa"].abs()

    # 4. Extreme transport anomalies (impossible delivery durations / distances)
    anomaly_idx = df.sample(n=15, random_state=14).index
    df.loc[anomaly_idx, "delivery_duration_hours"] = np.random.choice(
        [-5.0, 250.0, 300.0], size=len(anomaly_idx)
    )
    distance_outlier_idx = df.sample(n=10, random_state=15).index
    df.loc[distance_outlier_idx, "distance_km"] = df.loc[distance_outlier_idx, "distance_km"].abs() * 25

    # 5. Duplicate rows (orders syncing twice from a mobile app)
    dup_rows = df.sample(n=12, random_state=16)
    df = pd.concat([df, dup_rows], ignore_index=True)

    # 6. Shuffle final dataset
    df = df.sample(frac=1, random_state=17).reset_index(drop=True)

    return df


def clean_row(row):
    """Strip whitespace and turn NaN/NaT into None so the database stores
    NULL instead of the string "nan" -- the one piece of this pipeline
    with real, testable behavior.
    """
    cleaned = {}
    for key, value in row.items():
        if isinstance(value, str):
            value = value.strip()
        if pd.isna(value):
            value = None
        cleaned[key] = value
    return cleaned


def ensure_import_table(conn):
    sql = CREATE_TABLE_SQL_POSTGRES if get_engine() == "postgresql" else CREATE_TABLE_SQL
    conn.execute(format_query(sql))


def insert_orders(conn, rows):
    cleaned_rows = [clean_row(row) for row in rows]
    conn.executemany(
        format_query(INSERT_SQL),
        [tuple(row[col] for col in COLUMNS) for row in cleaned_rows],
    )
    conn.commit()
    return len(cleaned_rows)


def main():
    df = generate_messy_dataframe()
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    print(f"Generated {CSV_PATH} with {len(df)} rows.")

    parsed = pd.read_csv(CSV_PATH).to_dict(orient="records")

    conn = get_connection(str(DB_PATH))
    ensure_import_table(conn)
    inserted = insert_orders(conn, parsed)
    conn.close()
    print(f"Inserted {inserted} rows into {DB_PATH} (table ecommerce_orders_raw).")


if __name__ == "__main__":
    main()
