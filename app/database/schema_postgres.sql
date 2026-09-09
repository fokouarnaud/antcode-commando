CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    full_name     VARCHAR(255) NOT NULL,
    phone_number  VARCHAR(32) NOT NULL UNIQUE,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE addresses (
    address_id      SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers (customer_id),
    neighborhood    VARCHAR(255) NOT NULL,
    city            VARCHAR(255) NOT NULL,
    street_details  VARCHAR(255),
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_addresses_neighborhood_city ON addresses (neighborhood, city);

CREATE TABLE products (
    product_id       SERIAL PRIMARY KEY,
    name             VARCHAR(255) NOT NULL,
    category         VARCHAR(255) NOT NULL,
    unit_price_fcfa  INTEGER NOT NULL,
    stock_quantity   INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
    order_id         VARCHAR(255) PRIMARY KEY,
    customer_id      INTEGER NOT NULL REFERENCES customers (customer_id),
    address_id       INTEGER NOT NULL REFERENCES addresses (address_id),
    product_id       INTEGER NOT NULL REFERENCES products (product_id),
    quantity         INTEGER NOT NULL,
    unit_price_fcfa  INTEGER NOT NULL,
    delivery_status  VARCHAR(64) NOT NULL DEFAULT 'Pending',
    payment_status   VARCHAR(64) NOT NULL DEFAULT 'Pending',
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_delivery_status ON orders (delivery_status);
CREATE INDEX idx_orders_address_id ON orders (address_id);

CREATE TABLE payments (
    payment_id               SERIAL PRIMARY KEY,
    order_id                 VARCHAR(255) NOT NULL REFERENCES orders (order_id),
    provider                 VARCHAR(64) NOT NULL,
    external_transaction_id  VARCHAR(255) NOT NULL,
    amount_fcfa              INTEGER NOT NULL,
    status                   VARCHAR(64) NOT NULL DEFAULT 'Pending',
    received_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, external_transaction_id)
);
