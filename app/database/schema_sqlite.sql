-- updated_at defaults use STRFTIME(...,'now') rather than bare
-- CURRENT_TIMESTAMP: CURRENT_TIMESTAMP's 1-second resolution means an
-- insert immediately followed by an update (as in a test) can land in the
-- same wall-clock second and produce an identical string, hiding a real
-- change. The millisecond fraction ("%f") avoids that.
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    phone_number  TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at    TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'now'))
);

-- customer_id is nullable: a customer-registered address is owned by that
-- customer, but a shared logistics reference address (e.g. seeded canonical
-- neighborhood zones reused across many orders/customers) has no single owner.
CREATE TABLE addresses (
    address_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INTEGER REFERENCES customers (customer_id),
    neighborhood    TEXT NOT NULL,
    city            TEXT NOT NULL,
    street_details  TEXT,
    created_at      TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at      TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'now'))
);

CREATE INDEX idx_addresses_neighborhood_city ON addresses (neighborhood, city);

CREATE TABLE products (
    product_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    category         TEXT NOT NULL,
    unit_price_fcfa  INTEGER NOT NULL,
    stock_quantity   INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at       TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'now'))
);

-- AFTER UPDATE triggers refresh updated_at on any modification. The
-- trigger's own UPDATE does not re-fire itself: SQLite's recursive_triggers
-- setting defaults OFF (not enabled by app/config/database.py), so this
-- can't recurse.
CREATE TRIGGER trg_customers_updated_at
AFTER UPDATE ON customers
FOR EACH ROW
BEGIN
    UPDATE customers SET updated_at = STRFTIME('%Y-%m-%d %H:%M:%f', 'now')
    WHERE customer_id = OLD.customer_id;
END;

CREATE TRIGGER trg_addresses_updated_at
AFTER UPDATE ON addresses
FOR EACH ROW
BEGIN
    UPDATE addresses SET updated_at = STRFTIME('%Y-%m-%d %H:%M:%f', 'now')
    WHERE address_id = OLD.address_id;
END;

CREATE TRIGGER trg_products_updated_at
AFTER UPDATE ON products
FOR EACH ROW
BEGIN
    UPDATE products SET updated_at = STRFTIME('%Y-%m-%d %H:%M:%f', 'now')
    WHERE product_id = OLD.product_id;
END;

CREATE TABLE orders (
    order_id         TEXT PRIMARY KEY,
    customer_id      INTEGER NOT NULL REFERENCES customers (customer_id),
    address_id       INTEGER NOT NULL REFERENCES addresses (address_id),
    product_id       INTEGER NOT NULL REFERENCES products (product_id),
    quantity         INTEGER NOT NULL,
    unit_price_fcfa  INTEGER NOT NULL,
    delivery_status  TEXT NOT NULL DEFAULT 'Pending',
    -- payment_status is the order's global payment visibility, not the
    -- state of any one transactional attempt: it is strictly binary
    -- ('Paid' / 'Unpaid'), flipping to 'Paid' only once a payment attempt
    -- resolves as 'completed'. A failed or still-pending attempt leaves it
    -- 'Unpaid' -- see payments.status for the attempt's own state.
    payment_status   TEXT NOT NULL DEFAULT 'Unpaid',
    created_at       TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at       TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_orders_delivery_status ON orders (delivery_status);
CREATE INDEX idx_orders_address_id ON orders (address_id);

CREATE TABLE payments (
    payment_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id                 TEXT NOT NULL REFERENCES orders (order_id),
    provider                 TEXT NOT NULL,
    external_transaction_id  TEXT NOT NULL,
    amount_fcfa              INTEGER NOT NULL,
    -- status is the transactional state of this specific payment
    -- execution attempt: 'pending' / 'completed' / 'failed'.
    status                   TEXT NOT NULL DEFAULT 'pending',
    received_at              TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE (provider, external_transaction_id)
);
