import os
import pathlib
import sqlite3

DATABASE_DIR = pathlib.Path(__file__).parent.parent / "database"
SCHEMA_PATH = DATABASE_DIR / "schema_sqlite.sql"
SCHEMA_POSTGRES_PATH = DATABASE_DIR / "schema_postgres.sql"


def get_engine():
    return os.environ.get("DB_ENGINE", "sqlite").lower()


def format_query(sql_string):
    """Rewrites sqlite-style '?' placeholders to psycopg2-style '%s' when the
    active engine is PostgreSQL, so services can keep writing one SQL string.
    """
    if get_engine() == "postgresql":
        return sql_string.replace("?", "%s")
    return sql_string


def get_connection(path):
    if get_engine() == "postgresql":
        import psycopg2

        return psycopg2.connect(os.environ["DATABASE_URL"])
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    if get_engine() == "postgresql":
        with conn.cursor() as cursor:
            cursor.execute(SCHEMA_POSTGRES_PATH.read_text())
        conn.commit()
    else:
        conn.executescript(SCHEMA_PATH.read_text())
