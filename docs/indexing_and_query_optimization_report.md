# Indexing & Query Optimization Report

## Indexes under review

```sql
CREATE INDEX idx_addresses_neighborhood_city ON addresses (neighborhood, city);
CREATE INDEX idx_orders_delivery_status ON orders (delivery_status);
CREATE INDEX idx_orders_address_id ON orders (address_id);
```

Defined in `app/database/schema_sqlite.sql` / `schema_postgres.sql`, created
automatically by `init_db()`, and covered by `tests/test_database.py`.

## Why three indexes instead of one composite

The earlier schema stored `customer_neighborhood` directly on `orders` (a
denormalized copy of `addresses.neighborhood`) specifically so one composite
index, `idx_orders_neighborhood_status`, could answer "which orders in
neighborhood X are currently in status Y?" without a join. This refactor
removed that denormalized column in favor of a properly normalized schema —
`orders.address_id` is the only source of a customer's neighborhood now, via
`addresses`. That access pattern still has to stay fast, so it now needs two
things instead of one:

- **`idx_addresses_neighborhood_city`** (pre-existing) lets a neighborhood
  filter seek `addresses` directly instead of scanning it.
- **`idx_orders_address_id`** is new. A `FOREIGN KEY` column gets **no**
  automatic index in SQLite or PostgreSQL — without one, joining `orders` to
  the matched `addresses` rows falls back to a full scan of `orders`, which
  defeats the point of seeking `addresses` first. Confirmed empirically
  below: adding this index changed the join's plan from `SCAN orders` to a
  `SEARCH` on both sides.
- **`idx_orders_delivery_status`** (renamed from
  `idx_orders_neighborhood_status`, now single-column) still answers a
  delivery-status filter — alone, or combined with a neighborhood filter —
  without scanning `orders`.

## Evidence: measured against 500 seeded orders

Query plans below were captured with `EXPLAIN QUERY PLAN` against a database
populated by `scripts/seed_cameroon_volume.py::seed(conn, count=500)` (real
distribution: 5 neighborhoods at 92–105 orders each, 3 delivery statuses at
158–180 orders each — see `tests/test_seed_cameroon_volume.py`).

**Neighborhood-only filter** (`GET /orders?neighborhood=Akwa`,
`app/services/orders.py::list_orders`):

```sql
SELECT o.order_id FROM orders o
JOIN addresses a ON a.address_id = o.address_id
WHERE a.neighborhood = 'Akwa';
```

```
SEARCH a USING COVERING INDEX idx_addresses_neighborhood_city (neighborhood=?)
SEARCH o USING INDEX idx_orders_address_id (address_id=?)
```

Without `idx_orders_address_id`, the second line degrades to
`SCAN o` — SQLite has to walk every one of the 500 orders looking for
matches on `address_id`, instead of doing one indexed lookup per matched
address (92 for `Akwa` above).

**Neighborhood + status filter** (`GET
/orders?neighborhood=Akwa&status=Shipped`):

```
SEARCH o USING INDEX idx_orders_delivery_status (delivery_status=?)
SEARCH a USING INTEGER PRIMARY KEY (rowid=?)
```

SQLite's planner picks whichever filter is more selective to drive the
query — here `delivery_status='Shipped'` (180/500 rows) narrows further
than starting from `addresses`, then probes `addresses` by its own primary
key (`address_id` *is* `addresses`'s rowid) for the neighborhood check. Both
orderings are index-driven; no path in this query touches every row.

**Status-only filter** (`GET /orders?status=Shipped`):

```
SEARCH orders USING INDEX idx_orders_delivery_status (delivery_status=?)
```

Forcing SQLite to ignore every index on the same query (`orders NOT INDEXED`)
shows the baseline this avoids:

```
SCAN orders
```

## Why this matters at end-of-month Cameroonian shopping peaks

End-of-month paydays (and MoMo/Orange Money top-ups that follow) reliably
spike order volume in Douala/Yaoundé neighborhoods. `SCAN orders` costs grow
**linearly with total order history** — at 10x today's seeded volume, the
same dispatch-board query reads 10x more rows for the same answer, and pays
that cost on every concurrent dispatcher/webhook/dashboard request during
the exact window the system can least afford it. With `idx_orders_address_id`
and `idx_orders_delivery_status` in place, cost instead scales with the
**number of matching rows**, independent of how large `orders` grows.

## Trade-off: normalization moved the cost, not eliminated it

Going from one denormalized composite index to a join across two indexed
tables is strictly more normalized and removes a copy that could drift out
of sync with `addresses.neighborhood` — but it does mean the
neighborhood-filtered path now touches two tables instead of one, and its
cost depends on both indexes existing. `idx_orders_address_id` is the one
easy to forget (FK columns look indexed but aren't), which is exactly the
gap this report's `EXPLAIN QUERY PLAN` evidence caught.

## Summary

| Query | Without the relevant index | With it |
|---|---|---|
| `neighborhood = ?` (joined) | `SCAN orders` — cost grows with total order history | `SEARCH` on `addresses` then `SEARCH` on `orders` by `address_id` — cost grows with matching rows only |
| `delivery_status = ?` | `SCAN orders` | `SEARCH orders USING INDEX idx_orders_delivery_status` |
| `neighborhood = ? AND delivery_status = ?` | `SCAN orders` | Planner drives from whichever filter is more selective; both sides index-seek |
