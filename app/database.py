import pathlib
import sqlite3

SCHEMA_PATH = pathlib.Path(__file__).parent / "schema.sql"


def get_connection(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA_PATH.read_text())
