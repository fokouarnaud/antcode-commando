import re

from app.config.database import format_query, get_last_row_id

_PHONE_PATTERN = re.compile(r"^\+2376\d{8}$")


class CustomerValidationError(Exception):
    pass


class DuplicatePhoneError(Exception):
    pass


def _validate_phone(phone_number):
    if not phone_number or not _PHONE_PATTERN.match(phone_number):
        raise CustomerValidationError(
            "'phone_number' must be a Cameroonian mobile number in the form "
            "+2376XXXXXXXX"
        )


def _phone_in_use(conn, phone_number, exclude_customer_id=None):
    row = conn.execute(
        format_query("SELECT customer_id FROM customers WHERE phone_number = ?"),
        (phone_number,),
    ).fetchone()
    if row is None:
        return False
    return row["customer_id"] != exclude_customer_id


def get_customer(conn, customer_id):
    customer = conn.execute(
        format_query(
            "SELECT customer_id, full_name, phone_number, created_at, updated_at FROM customers "
            "WHERE customer_id = ?"
        ),
        (customer_id,),
    ).fetchone()
    if customer is None:
        return None

    addresses = conn.execute(
        format_query(
            "SELECT address_id, neighborhood, city, street_details, created_at, updated_at "
            "FROM addresses WHERE customer_id = ? ORDER BY address_id"
        ),
        (customer_id,),
    ).fetchall()

    result = dict(customer)
    result["addresses"] = [dict(address) for address in addresses]
    return result


def create_customer_with_address(conn, full_name, phone_number, neighborhood, city, street_details=None):
    if not full_name:
        raise CustomerValidationError("'full_name' is required")
    if not neighborhood or not city:
        raise CustomerValidationError("'neighborhood' and 'city' are required")
    _validate_phone(phone_number)
    if _phone_in_use(conn, phone_number):
        raise DuplicatePhoneError(phone_number)

    cursor = conn.execute(
        format_query("INSERT INTO customers (full_name, phone_number) VALUES (?, ?)"),
        (full_name, phone_number),
    )
    customer_id = get_last_row_id(cursor, "customers", "customer_id")

    conn.execute(
        format_query(
            "INSERT INTO addresses (customer_id, neighborhood, city, street_details) "
            "VALUES (?, ?, ?, ?)"
        ),
        (customer_id, neighborhood, city, street_details),
    )
    conn.commit()

    return get_customer(conn, customer_id)


def update_customer(conn, customer_id, fields):
    existing = get_customer(conn, customer_id)
    if existing is None:
        return None

    customer_updates = {}
    if "full_name" in fields:
        customer_updates["full_name"] = fields["full_name"]
    if "phone_number" in fields:
        _validate_phone(fields["phone_number"])
        if _phone_in_use(conn, fields["phone_number"], exclude_customer_id=customer_id):
            raise DuplicatePhoneError(fields["phone_number"])
        customer_updates["phone_number"] = fields["phone_number"]

    if customer_updates:
        set_clause = ", ".join(f"{column} = ?" for column in customer_updates)
        conn.execute(
            format_query(f"UPDATE customers SET {set_clause} WHERE customer_id = ?"),
            list(customer_updates.values()) + [customer_id],
        )

    address_updates = {
        key: fields[key] for key in ("neighborhood", "city", "street_details") if key in fields
    }
    if address_updates and existing["addresses"]:
        primary_address_id = existing["addresses"][0]["address_id"]
        set_clause = ", ".join(f"{column} = ?" for column in address_updates)
        conn.execute(
            format_query(f"UPDATE addresses SET {set_clause} WHERE address_id = ?"),
            list(address_updates.values()) + [primary_address_id],
        )

    conn.commit()
    return get_customer(conn, customer_id)


def delete_customer(conn, customer_id):
    """Returns True if deleted, False if customer_id didn't exist. Deletes
    the customer's addresses first, then the customer row. Lets
    IntegrityError bubble up (with the transaction rolled back) when
    orders still reference this customer or one of its addresses -- the
    route translates that into a 409.
    """
    existing = get_customer(conn, customer_id)
    if existing is None:
        return False

    try:
        conn.execute(
            format_query("DELETE FROM addresses WHERE customer_id = ?"), (customer_id,)
        )
        conn.execute(
            format_query("DELETE FROM customers WHERE customer_id = ?"), (customer_id,)
        )
    except Exception:
        conn.rollback()
        raise

    conn.commit()
    return True
