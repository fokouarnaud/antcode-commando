CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    phone_number  TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE addresses (
    address_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INTEGER NOT NULL REFERENCES customers (customer_id),
    neighborhood    TEXT NOT NULL,
    city            TEXT NOT NULL,
    street_details  TEXT,
    created_at      TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_addresses_neighborhood_city ON addresses (neighborhood, city);

CREATE TABLE products (
    product_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    category         TEXT NOT NULL,
    unit_price_fcfa  INTEGER NOT NULL,
    stock_quantity   INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE orders (
    order_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id             INTEGER NOT NULL REFERENCES customers (customer_id),
    address_id              INTEGER NOT NULL REFERENCES addresses (address_id),
    customer_neighborhood   TEXT NOT NULL,
    delivery_status         TEXT NOT NULL DEFAULT 'Pending',
    payment_status          TEXT NOT NULL DEFAULT 'Pending',
    external_ref            TEXT UNIQUE,
    created_at              TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at              TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_orders_neighborhood_status ON orders (customer_neighborhood, delivery_status);

CREATE TABLE order_items (
    order_item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER NOT NULL REFERENCES orders (order_id),
    product_id       INTEGER NOT NULL REFERENCES products (product_id),
    quantity         INTEGER NOT NULL,
    unit_price_fcfa  INTEGER NOT NULL
);

CREATE TABLE payments (
    payment_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id                 INTEGER NOT NULL REFERENCES orders (order_id),
    provider                 TEXT NOT NULL,
    external_transaction_id  TEXT NOT NULL,
    amount_fcfa              INTEGER NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'Pending',
    received_at              TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE (provider, external_transaction_id)
);
