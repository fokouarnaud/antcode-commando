# Indexing & Query Optimization Report

## Index under review

```sql
CREATE INDEX idx_orders_neighborhood_status
    ON orders (customer_neighborhood, delivery_status);
```

Defined in `app/database/schema_sqlite.sql`, created automatically by `init_db()`, and
verified live in `ecommerce.db` via `PRAGMA index_list(orders)` and covered
by `tests/test_database.py::test_init_db_creates_orders_neighborhood_status_index`.

## Why these two columns, in this order

`customer_neighborhood` and `delivery_status` are stored directly on
`orders` (not only via the `addresses` join) specifically so this index can
answer the platform's most common operational query without a join:
**"which orders in neighborhood X are currently in status Y?"** — the query
ops and dispatch teams run continuously to route drivers, chase delayed
deliveries, and flag cancellations by zone.

SQLite (like most B-tree engines) can use a composite index for:
- an equality match on the leading column alone (`customer_neighborhood = ?`), or
- an equality match on both columns together (`customer_neighborhood = ? AND delivery_status = ?`)

but **not** for a query that filters on `delivery_status` alone — the
column order is chosen so the more selective, more frequently-filtered
column (neighborhood — 10 stable values, evenly distributed) leads, and the
higher-cardinality-per-neighborhood status filter narrows it further. This
mirrors the query patterns actually run against the data (see below).

## Evidence: index is live and used

Query plan for the exact composite lookup, run against the loaded database
(912 orders):

```sql
EXPLAIN QUERY PLAN
SELECT order_id FROM orders
WHERE customer_neighborhood = 'Akwa' AND delivery_status = 'Delivered';
```

```
SEARCH orders USING COVERING INDEX idx_orders_neighborhood_status
    (customer_neighborhood=? AND delivery_status=?)
```

Forcing SQLite to ignore the index on the same query (`NOT INDEXED`) shows
what the query costs without it:

```
SCAN orders
```

`SCAN` touches every row in the table; `SEARCH ... USING COVERING INDEX`
seeks directly to the matching B-tree range and never has to read the
underlying table rows at all (the index alone contains every column the
query needs — hence "covering"). The leading-column case also uses the
index on its own:

```sql
EXPLAIN QUERY PLAN
SELECT order_id FROM orders WHERE customer_neighborhood = 'Bastos';
-- SEARCH orders USING COVERING INDEX idx_orders_neighborhood_status (customer_neighborhood=?)
```

## Why this matters at end-of-month Cameroonian shopping peaks

End-of-month paydays (and MoMo/Orange Money top-ups that follow) reliably
spike order volume in this dataset's Douala/Yaoundé neighborhoods. Without
this index, every dispatch-board refresh, delayed-order sweep, or
per-neighborhood delivery dashboard would force a full table scan of
`orders` — cost that grows **linearly with total order history**, not with
the size of the answer. At 10x today's 912-row volume (a realistic
end-of-month multiplier), an unindexed scan reads 10x more rows for the
exact same answer set, and that cost is paid by every concurrent
dispatcher/webhook/dashboard query hitting the table at once during the
peak window — the moment the system can least afford it.

With the index, cost scales with the **number of matching rows**, not the
table size: a lookup for one neighborhood/status pair costs the same
whether `orders` holds 912 rows or 912,000. This is what keeps
neighborhood-level dispatch views and delayed-delivery alerts responsive
exactly when order volume (and therefore load) is highest.

## Data quality precondition: normalized neighborhood casing

A composite index only groups values that are byte-identical. Before this
index was populated, the raw import (`ecommerce_orders_raw`) contained the
same real-world neighborhood under multiple spellings — casing variants
(`akwa`, `AKWA`, `Akwa `) and, for hyphenated names, a space variant
(`Biyem-Assi` vs `Biyem Assi`, produced by the source system's mobile app
sync). Left uncleaned, each spelling would occupy its own index bucket,
silently splitting one neighborhood's orders across several — undercounting
every per-neighborhood dashboard and missing rows on any exact-match filter
that didn't happen to use the same spelling.

`app/services/pipeline.py::normalize_neighborhood()` (used by
`load_structured_data()` when populating `orders.customer_neighborhood`
from `ecommerce_orders_raw`) resolves this by:
1. stripping whitespace and title-casing, then
2. snapping known Douala/Yaoundé neighborhoods to one canonical spelling
   regardless of hyphen/space variation, so `"biyem assi"`, `"Biyem Assi"`,
   and `"BIYEM-ASSI"` all normalize to `"Biyem-Assi"`.

Verified against the full loaded dataset: `orders.customer_neighborhood`
holds exactly 10 distinct values, one per known neighborhood, with no
casing or spacing duplicates — confirming the index groups each
neighborhood's orders correctly.

## Summary

| Without the index | With the index |
|---|---|
| `SCAN orders` — cost grows with total order history | `SEARCH ... USING COVERING INDEX` — cost grows with matching rows only |
| Every neighborhood/status dashboard query competes for full-table I/O during peak load | Lookups stay a direct B-tree seek regardless of concurrent load |
| Text anomalies (casing/spacing) silently fragment per-neighborhood counts | Normalized at load time; index buckets are correct |
