from app.config.database import format_query, get_last_row_id

_PRODUCT_COLUMNS = "product_id, name, category, unit_price_fcfa, stock_quantity, created_at"


class ProductValidationError(Exception):
    pass


def list_products(conn, page=1, per_page=20):
    total_records = conn.execute(
        format_query("SELECT COUNT(*) AS n FROM products")
    ).fetchone()["n"]

    offset = (page - 1) * per_page
    rows = conn.execute(
        format_query(
            f"SELECT {_PRODUCT_COLUMNS} FROM products ORDER BY product_id LIMIT ? OFFSET ?"
        ),
        (per_page, offset),
    ).fetchall()

    return rows, total_records


def get_product_by_id(conn, product_id):
    return conn.execute(
        format_query(f"SELECT {_PRODUCT_COLUMNS} FROM products WHERE product_id = ?"),
        (product_id,),
    ).fetchone()


def create_product(conn, name, category, unit_price_fcfa, stock_quantity=0):
    if not name or not category:
        raise ProductValidationError("'name' and 'category' are required")
    if not isinstance(unit_price_fcfa, int) or unit_price_fcfa <= 0:
        raise ProductValidationError("'unit_price_fcfa' must be a positive integer")
    if not isinstance(stock_quantity, int) or stock_quantity < 0:
        raise ProductValidationError("'stock_quantity' must be a non-negative integer")

    cursor = conn.execute(
        format_query(
            "INSERT INTO products (name, category, unit_price_fcfa, stock_quantity) "
            "VALUES (?, ?, ?, ?)"
        ),
        (name, category, unit_price_fcfa, stock_quantity),
    )
    conn.commit()
    product_id = get_last_row_id(cursor, "products", "product_id")
    return get_product_by_id(conn, product_id)


def update_product(conn, product_id, fields):
    existing = get_product_by_id(conn, product_id)
    if existing is None:
        return None

    allowed = {"name", "category", "unit_price_fcfa", "stock_quantity"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if "unit_price_fcfa" in updates and (
        not isinstance(updates["unit_price_fcfa"], int) or updates["unit_price_fcfa"] <= 0
    ):
        raise ProductValidationError("'unit_price_fcfa' must be a positive integer")
    if "stock_quantity" in updates and (
        not isinstance(updates["stock_quantity"], int) or updates["stock_quantity"] < 0
    ):
        raise ProductValidationError("'stock_quantity' must be a non-negative integer")

    if not updates:
        return existing

    set_clause = ", ".join(f"{column} = ?" for column in updates)
    conn.execute(
        format_query(f"UPDATE products SET {set_clause} WHERE product_id = ?"),
        list(updates.values()) + [product_id],
    )
    conn.commit()
    return get_product_by_id(conn, product_id)


def delete_product(conn, product_id):
    """Returns True if deleted, False if product_id didn't exist. Lets
    IntegrityError bubble up when orders still reference this product --
    the route translates that into a 409.
    """
    cursor = conn.execute(format_query("DELETE FROM products WHERE product_id = ?"), (product_id,))
    conn.commit()
    return cursor.rowcount > 0
