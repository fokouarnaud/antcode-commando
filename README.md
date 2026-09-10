# AntCode Commando — E-Commerce Logistics Platform

A Cameroon-focused e-commerce logistics backend: a clean, secure relational
CRUD architecture over a 5-table normalized schema (customers, addresses,
products, orders, payments), populated with realistic Cameroonian volume via
`scripts/seed_cameroon_volume.py`, exposing full CRUD for products/customers/
orders plus idempotent MTN MoMo / Orange Money / Campay / Smobilpay /
GeniusPay payment callbacks. Built strictly test-first — see
[`.agents/skills/test-driven-development/SKILL.md`](.agents/skills/test-driven-development/SKILL.md).

## Architecture

```mermaid
flowchart LR
    SEED["scripts/seed_cameroon_volume.py\n(500 Cameroonian volume logs)"]

    subgraph CFG["app/config/database.py"]
        ENGINE["get_engine() / format_query()\nDB_ENGINE env toggle"]
    end

    subgraph SCHEMA["app/database/ (DDL, isolated from code)"]
        SQLITE_SQL["schema_sqlite.sql"]
        PG_SQL["schema_postgres.sql"]
    end

    subgraph DB["5 normalized tables (sqlite3 or psycopg2, same schema shape)"]
        CUST[("customers")]
        ADDR[("addresses")]
        PROD[("products")]
        ORD[("orders\n+ idx_orders_delivery_status")]
        PAY[("payments\nUNIQUE(provider, external_transaction_id)")]
    end

    subgraph API["Flask app (app/__init__.py: create_app)"]
        PROD_R["GET/POST /products\nPUT/DELETE /products/{id}\napp/routes/products.py"]
        CUST_R["POST /customers\nGET/PUT/DELETE /customers/{id}\napp/routes/customers.py"]
        ORD_R["GET/POST /orders\nGET/PUT/DELETE /orders/{id}\napp/routes/orders.py"]
        CHECKOUT_R["POST /orders/{id}/checkout"]
        PAY_R["GET/POST /payments\nGET /payments/{ref}\nPUT/DELETE /payments/{id}\napp/routes/payments.py"]
        HOOK_R["POST /webhook/{provider}\napp/routes/webhooks.py"]
        DOCS_R["GET /docs, GET /openapi.json\napp/routes/docs.py"]
    end

    DOCS_SPEC["app/docs/openapi.json\n(read by Scalar UI at /docs)"]

    PROVIDER["MoMo / Orange / Campay / Smobilpay / GeniusPay callback"]
    JURY["Jury / API client"]

    SEED -->|uses| ENGINE
    ENGINE -->|init_db reads| SCHEMA
    SCHEMA -.->|defines| DB
    SEED --> CUST & ADDR & PROD & ORD
    PROVIDER -->|HMAC-SHA256 signed| HOOK_R
    HOOK_R -->|idempotent insert| PAY
    HOOK_R -->|update payment_status| ORD
    PAY_R -->|CRUD| PAY
    JURY --> PROD_R & CUST_R & ORD_R & CHECKOUT_R & PAY_R & DOCS_R
    DOCS_R -->|serves| DOCS_SPEC
```

Neighborhood filtering (`GET /orders?neighborhood=...`) joins `orders` to
`addresses` rather than keeping a denormalized copy on `orders` — see
[`docs/indexing_and_query_optimization_report.md`](docs/indexing_and_query_optimization_report.md).

## Project layout

```
app/
├── __init__.py                     # create_app() factory (zero-arg, loads Config), registers blueprints
├── config/
│   ├── database.py                 # get_connection(), init_db(), get_engine(), format_query()
│   │                                #   -- toggles sqlite3 / psycopg2 via DB_ENGINE env var
│   └── settings.py                 # Config class -- app.config.from_object() source, mirrors env vars
├── database/
│   ├── schema_sqlite.sql           # the 5-table schema + indexes (sqlite3)
│   └── schema_postgres.sql         # same schema adapted for PostgreSQL (SERIAL/VARCHAR/TIMESTAMP)
├── docs/
│   └── openapi.json                # OpenAPI 3.0 spec (static file, served as-is)
├── routes/
│   ├── customers.py                # POST /customers, GET/PUT/DELETE /customers/{id}
│   ├── docs.py                     # GET /docs (Scalar UI), GET /openapi.json
│   ├── orders.py                   # GET/POST /orders, GET/PUT/DELETE /orders/{id}, checkout, sync
│   ├── payments.py                 # GET/POST /payments, GET by transaction id, PUT/DELETE /payments/{id}
│   ├── products.py                 # GET/POST /products, PUT/DELETE /products/{id}
│   └── webhooks.py                 # POST /webhook/{provider}
└── services/
    ├── customers.py                # customer + address CRUD
    ├── geniuspay.py                 # GeniusPay checkout session initiation
    ├── orders.py                   # order CRUD, lookup, pagination, offline sync
    ├── payments.py                 # payment ledger CRUD (manual reconciliation/corrections)
    ├── products.py                 # product CRUD
    └── webhooks.py                 # idempotent multi-provider callback processing
scripts/
└── seed_cameroon_volume.py         # seeds 500 Cameroonian orders into the normalized tables
docs/
└── indexing_and_query_optimization_report.md
tests/
├── conftest.py                     # app/client fixtures shared by every test module
├── test_customers_routes.py
├── test_database.py
├── test_docs_routes.py
├── test_geniuspay.py
├── test_orders_routes.py
├── test_payments_routes.py
├── test_products_routes.py
├── test_seed_cameroon_volume.py
├── test_settings.py
└── test_webhooks.py
run.py                               # dev entry point (python run.py)
requirements.txt
README.md
```

## Getting started

```bash
pip install -r requirements.txt

# 1. Seed 500 realistic Cameroonian orders into the normalized tables
python scripts/seed_cameroon_volume.py

# 2. Run the API
MOMO_WEBHOOK_SECRET=your-momo-secret ORANGE_WEBHOOK_SECRET=your-orange-secret python run.py
```

`DB_ENGINE` defaults to `sqlite` (no env var needed for local dev). Set
`DB_ENGINE=postgresql` and `DATABASE_URL=...` to run against PostgreSQL
instead — `app/config/database.py` picks the matching schema file from
`app/database/` and swaps `?` placeholders for `%s` via `format_query()`
automatically.

### Running with any provider (MoMo, Orange, Campay, Smobilpay, GeniusPay)

`POST /webhook/{provider}` is a single dynamic route: `_webhook(provider)`
(`app/routes/webhooks.py`) resolves that provider's own secret and
signature header straight from `_PROVIDER_CONFIG`, keyed on the `provider`
URL segment. Adding a new provider is a config-map entry, not a new route.

```bash
CAMPAY_WEBHOOK_SECRET=secret python run.py
# then POST to /webhook/campay, signed with X-Campay-Signature
```

Every provider works the same way — swap the URL segment and its matching
secret env var: `/webhook/momo` + `MOMO_WEBHOOK_SECRET`, `/webhook/orange` +
`ORANGE_WEBHOOK_SECRET`, `/webhook/smobilpay` + `SMOBILPAY_WEBHOOK_SECRET`,
or `/webhook/geniuspay` + `GENIUSPAY_WEBHOOK_SECRET` (which additionally
requires `X-Webhook-Timestamp` and `X-Webhook-Event` headers, since
GeniusPay signs `f"{timestamp}.{raw_body}"` rather than the raw body
alone). A `provider` segment with no entry in `_PROVIDER_CONFIG` returns
500.

Then open **http://127.0.0.1:5000/docs** for the interactive Scalar API
reference, or **http://127.0.0.1:5000/openapi.json** for the raw spec.

## API

| Route | Method | Purpose |
|---|---|---|
| `/orders` | GET | List orders, optional `?neighborhood=` (joins `addresses`) and/or `?status=` (served by `idx_orders_delivery_status`) filters, plus `?page=` (default 1) and `?per_page=` (default 20). Response is `{"data": [...], "pagination": {"page", "per_page", "total_records", "total_pages"}}` |
| `/orders` | POST | Creates a single order. Accepts `customer_id` or `customer_name`+`customer_phone`+`neighborhood`(+`city`) (get-or-create), and `product_id` or `product_name`+`category`+`unit_price_fcfa` (get-or-create), plus `quantity`. `order_id` is auto-generated (`ECM-NNNNN`) if omitted |
| `/orders/{id_or_ref}` | GET | Fetch a single order by its own `order_id` (e.g. `ECM-00001`) or a payment's transaction reference (e.g. `MTX-A1B2C3D4E5`) — whichever one the caller has on hand. 404 if none match |
| `/orders/{order_id}` | PUT | Updates an order's `delivery_status` (`Pending`/`Shipped`/`Delivered`) and/or `payment_status` (`Paid`/`Unpaid`). 400 on an invalid value, 404 if the order doesn't exist |
| `/orders/{order_id}` | DELETE | Deletes an order. 404 if it doesn't exist, 409 if `payments` still reference it |
| `/orders/{order_id}/checkout` | POST | Triggers `initiate_geniuspay_payment()` (`app/services/geniuspay.py`) for `quantity * unit_price_fcfa` and returns `{"checkout_url", "transaction_reference"}`. 404 if the order doesn't exist, 502 if the outbound GeniusPay call fails |
| `/orders/sync` | POST | Bulk-ingests a JSON array of offline-captured orders (`app/services/orders.py::sync_offline_orders`). Idempotent on `order_id`: replaying an identical batch after a connectivity blackout skips every already-synced order instead of duplicating it. Returns `{"synced", "skipped"}` |
| `/products` | GET | Paginated product list (`?page=`, `?per_page=`) |
| `/products` | POST | Creates a product (`name`, `category`, `unit_price_fcfa`, optional `stock_quantity`). 400 on invalid fields |
| `/products/{id}` | PUT | Partially updates a product. 404 if unknown |
| `/products/{id}` | DELETE | Deletes a product. 404 if unknown, 409 if referenced by an order |
| `/customers` | POST | Creates a customer together with its first address (`full_name`, `phone_number` as `+2376XXXXXXXX`, `neighborhood`, `city`, optional `street_details`). 400 on invalid phone format, 409 on a phone already in use |
| `/customers/{id}` | GET | Fetch a customer with its nested `addresses`. 404 if unknown |
| `/customers/{id}` | PUT | Updates customer fields and/or its primary address's fields. 404 if unknown, 409 on a phone taken by another customer |
| `/customers/{id}` | DELETE | Deletes a customer and its addresses. 404 if unknown, 409 if the customer has existing orders |
| `/payments` | GET | Paginated payment ledger, newest first (`ORDER BY payment_id DESC`) |
| `/payments` | POST | Manually records a payment (offline cash, direct bank wire), enforcing `UNIQUE(provider, external_transaction_id)`. 400 on invalid fields, 404 if `order_id` doesn't exist, 409 on a duplicate `(provider, external_transaction_id)` |
| `/payments/{external_transaction_id}` | GET | Fetches a payment's full details with its order nested under `"order"`. 404 if no payment matches |
| `/payments/{payment_id}` | PUT | Updates `status` and/or `external_transaction_id` only — `order_id`/`provider`/`amount_fcfa` are immutable. 400 on invalid status, 404 if unknown, 409 on a reference collision |
| `/payments/{payment_id}` | DELETE | Deletes a payment log entry. 404 if unknown |
| `/webhook/{provider}` | POST | Payment callback for the named provider (`momo`, `orange`, `campay`, `smobilpay`, `geniuspay`). Requires that provider's own signature header (e.g. `X-Momo-Signature`, `X-Campay-Signature`, or `X-Webhook-Signature` + `X-Webhook-Timestamp` + `X-Webhook-Event` for `geniuspay`) keyed with its own secret, resolved dynamically from `_PROVIDER_CONFIG`. Idempotent on `(provider, external_transaction_id)`; an unrecognized `provider` returns 500 |
| `/webhook/simulate-carrier` | POST | **Dev-only** (404s unless the app runs with `debug=True`): bypasses signature verification entirely to fire a `momo`/`orange` callback straight from the Scalar UI, for demoing the payment lifecycle without hand-computing an HMAC. Never enable `debug` in production |
| `/docs` | GET | Interactive Scalar API reference — try all endpoints above from the browser |
| `/openapi.json` | GET | OpenAPI 3.0 spec backing `/docs` (`app/docs/openapi.json`) |

### 🧪 Live End-to-End Testing Scenarios

These three scenarios walk the full GeniusPay payment lifecycle by hand
against a running server (`python run.py`), either from the Scalar UI at
**http://127.0.0.1:5000/docs** or with `curl`. They exercise the exact same
guarantees `tests/test_geniuspay.py` and `tests/test_webhooks.py` already
assert with mocks — here you're watching them hold against the real
routes. Replace `1` below with a real `order_id` from `GET /orders` if
your database doesn't already have one.

#### Scenario 1 — Outbound Initiation

```bash
curl -X POST http://127.0.0.1:5000/orders/1/checkout
```

Expected response:

```json
{
  "checkout_url": "https://geniuspay.ci/pay/...",
  "transaction_reference": "..."
}
```

This is a *real* outbound `POST https://geniuspay.ci/api/v1/merchant/payments`
(`app/services/geniuspay.py::initiate_geniuspay_payment`), signed with
`GENIUSPAY_API_KEY`/`GENIUSPAY_API_SECRET` from `.env`. Without live
GeniusPay sandbox credentials there's nothing real to reach, so expect
`502 {"error": "payment initiation failed"}` instead — that's
`GeniusPayError` being caught cleanly, not a crash. Swap in real sandbox
keys to see an actual `checkout_url` come back.

#### Scenario 2 — Async Webhook Ingestion

**Option A — GeniusPay's real signature scheme.** GeniusPay signs
`f"{timestamp}.{raw_body}"`, so compute the signature before sending:

```bash
python3 - <<'PY'
import hashlib, hmac, json, time

secret = "dev-secret-change-me"  # your GENIUSPAY_WEBHOOK_SECRET
timestamp = str(int(time.time()))
body = json.dumps({"data": {"transaction_id": "GPAY-DEMO-01", "amount": 12000, "metadata": {"order_id": 1}}})
signature = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
print(f'curl -X POST http://127.0.0.1:5000/webhook/geniuspay \\\n  -H "X-Webhook-Signature: {signature}" \\\n  -H "X-Webhook-Timestamp: {timestamp}" \\\n  -H "X-Webhook-Event: payment.success" \\\n  -H "Content-Type: application/json" \\\n  -d \'{body}\'')
PY
```

Run the `curl` command it prints.

**Option B — the dev-only simulation route** (`momo`/`orange`, no
signature math required; only answers when the app runs with
`debug=True`, e.g. `python run.py`):

```bash
curl -X POST http://127.0.0.1:5000/webhook/simulate-carrier \
  -H "Content-Type: application/json" \
  -d '{"provider": "momo", "order_id": 1, "amount": 12000, "phone": "+237690000001", "external_transaction_id": "SIM-DEMO-01"}'
```

Either way, expected response:

```json
{"status": "processed", "payment_id": 1}
```

Confirm the order flipped to `Paid`, by `order_id`:

```bash
curl http://127.0.0.1:5000/orders/1
```

Or fetch the exact same order state using the *transaction reference*
the callback just recorded — no `order_id` needed at all, exactly what a
GeniusPay/MoMo/Orange confirmation screen would hand a customer back
(`GET /orders/{id_or_ref}` resolves this through
`get_order_by_transaction_reference()` against `payments.external_transaction_id`,
app/services/orders.py):

```bash
curl http://127.0.0.1:5000/orders/GPAY-DEMO-01      # if you used Option A
curl http://127.0.0.1:5000/orders/SIM-DEMO-01       # if you used Option B
```

A quick verification lookup showcasing the same transaction reference
against the payments ledger directly (`GET /payments/{external_transaction_id}`,
`app/routes/payments.py`) — the payment plus its order nested under
`"order"`, so a support agent double-checking a webhook's effect gets the
full picture in one call, right after the callback resolves:

```bash
curl http://127.0.0.1:5000/payments/GPAY-DEMO-01    # if you used Option A
curl http://127.0.0.1:5000/payments/SIM-DEMO-01     # if you used Option B
```

#### Scenario 3 — Double-Entry Replay Attack Safeguard

Resend the *exact same* request from Scenario 2 (identical
`external_transaction_id`) a second time:

```bash
curl -X POST http://127.0.0.1:5000/webhook/simulate-carrier \
  -H "Content-Type: application/json" \
  -d '{"provider": "momo", "order_id": 1, "amount": 12000, "phone": "+237690000001", "external_transaction_id": "SIM-DEMO-01"}'
```

Expected response — still `200`, but no new row written:

```json
{"status": "already_processed", "payment_id": 1}
```

`SELECT COUNT(*) FROM payments WHERE external_transaction_id =
'SIM-DEMO-01'` stays at `1` no matter how many times this is replayed —
the pre-flight lookup on `(provider, external_transaction_id)` (`UNIQUE`
in the schema) catches it before any insert, exactly as proven by
`test_momo_webhook_does_not_double_process_retried_callback` and
`test_simulate_carrier_webhook_is_idempotent_on_replay_when_debug_enabled`.

## Testing

```bash
python -m pytest -v
```

135 tests, 100% passing (`python -m pytest -v`). Every behavior above —
including the schema, the CRUD services/routes, the dual-engine connection
layer, the multi-provider webhooks, the GeniusPay checkout/webhook
lifecycle, the offline sync endpoint, the seeder, and the paginated order
lookup — was written test-first: a failing test proving the gap, then the
minimal code to close it, per the project's
[TDD skill](.agents/skills/test-driven-development/SKILL.md).

## Cameroonian context adaptation

### Volume seeder: three independent pools, not one duplicated per order

`scripts/seed_cameroon_volume.py` inserts realistic transaction logs straight
into the normalized tables through `get_connection()`/`format_query()` — no
raw staging table, no ETL step. `main()` first calls `reset_database()`
(drops every table, child-before-parent, then re-runs `init_db()`) so each
run starts from a pristine slate rather than accumulating on top of
whatever the file already held.

Three phases populate three genuinely independent pools, each fully built
before the next reads from it — an earlier revision instead created one new
address row per customer (500 near-duplicate rows for 5 neighborhoods),
which this structure now makes structurally impossible:

- **Reference data**: products (Electronics/Phones/Fashion, e.g.
  Tecno/Samsung/Infinix phones, TVs, wax print fabric) and a **fixed pool of
  5 logistics addresses**, get-or-created by name/(`neighborhood`, `city`)
  — one row per Douala/Yaoundé neighborhood (Akwa, Bonapriso → Douala;
  Bastos, Mendong, Biyem-Assi → Yaoundé), owned by no customer
  (`addresses.customer_id IS NULL`).
- **100 distinct customers**, each with a real-looking Cameroonian full
  name and a unique `+2376XXXXXXXX` mobile number — no address of their own
  at this stage.
- **500 orders**, each picking an *existing* `customer_id`, `address_id`,
  and `product_id` at random from the pools above (never creating a new
  one), with a random quantity, one of the three tracking states
  (`Pending`/`Shipped`/`Delivered`), and a sequential `order_id`
  (`ECM-NNNNN`).

This mirrors real e-commerce behavior directly: customers place multiple
orders, and many orders/customers share the same canonical delivery zone.
`app/services/orders.py::_get_or_create_address()` (used by this seeder,
`POST /orders`, and `POST /orders/sync`) is keyed purely on
`(neighborhood, city)` for exactly this reason — contrast with a customer's
own *registered* address in `app/services/customers.py`, which legitimately
belongs to that one customer and is a separate, unaffected code path.

Verified by `tests/test_seed_cameroon_volume.py`: exactly 5 address rows
(one per neighborhood, `customer_id IS NULL`) and 100 customers regardless
of how many of the 500 orders are generated; every order's `customer_id`/
`address_id` comes from the pre-populated pool, not a fresh insert; every
phone number unique and `+2376`-formatted; and `reset_database()` verified
to zero every table before a second seeding run reproduces the same counts.

### Network timeout protection: idempotent webhook

3G connectivity drops in Douala/Yaoundé are routine, and payment providers
retry a callback when they don't get an acknowledgement in time. If that
retry were processed twice, an order could get double-charged or its
`payment_status` flipped back and forth. `POST /webhook/momo`
(`app/services/webhooks.py::process_momo_callback`) gates on
`payments.external_transaction_id`, which is `UNIQUE` in the schema: the
first callback for a given transaction ID inserts the payment and updates
the order; every retry of that same transaction ID is recognized before any
write and answered with `{"status": "already_processed"}` — same result,
zero duplicate writes. Enforced at both the application layer (a lookup
before insert) and the database layer (the `UNIQUE` constraint as a
backstop), and proven by
`tests/test_webhooks.py::test_momo_webhook_does_not_double_process_retried_callback`,
which posts the identical callback twice and asserts exactly one payment
row exists afterward.

Authenticity is checked with a real HMAC, not a bare shared secret: the
caller sends `X-Momo-Signature`, the hex HMAC-SHA256 of the *raw request
body* keyed with `MOMO_WEBHOOK_SECRET`
(`app/routes/webhooks.py::_has_valid_signature`, compared with
`hmac.compare_digest` to avoid timing attacks). That binds the signature to
the exact bytes received, so a signature computed over one payload will not
validate a tampered one — proven by
`test_momo_webhook_rejects_tampered_payload_even_with_valid_looking_signature`,
which reuses a genuine signature against a modified `amount_fcfa` and
asserts it's rejected.

### Limit/Offset pagination: saving 3G data and battery

`GET /orders` with no bounds would ship every row in one response —
expensive on the metered, throttled 3G/4G connections common in Douala and
Yaoundé, and on phones where every extra second of radio activity drains the
battery. `app/services/orders.py::list_orders()` now takes `page`/`per_page`
(defaults 1/20) and appends `LIMIT ? OFFSET ?` to the query — through
`format_query()`, so the same code paginates correctly whether the query
runs against sqlite3 or PostgreSQL. The response never asks a client to
guess: `pagination.total_records` and `pagination.total_pages` are computed
from a `COUNT(*)` over the *same* filtered `WHERE` clause as the page
itself, so a field agent's app can request exactly the next page it needs —
and nothing more — instead of re-fetching or truncating a full list
client-side.

### Dual-operator webhook safety gates

Field agents and customers pay with whichever operator has signal and float
at the moment — MTN MoMo and Orange Money both, often interchangeably.
`POST /webhook/momo` and `POST /webhook/orange` are two distinct Flask
routes (`app/routes/webhooks.py`), each checked against its *own* shared
secret (`MOMO_WEBHOOK_SECRET` / `ORANGE_WEBHOOK_SECRET`) and its own
signature header (`X-Momo-Signature` / `X-Orange-Signature`) before either
touches the database — a request signed with Orange's secret is rejected on
the momo route and vice versa
(`test_momo_webhook_rejects_orange_signature_for_the_momo_route`). The
provider identity stored against each payment is taken from the *route
that verified the signature*, never from a client-supplied field in the
JSON body, closing off a class of bug where a forged or mistaken `provider`
value in the payload could point a payment at the wrong operator's ledger.

This also fixes a latent collision risk: the idempotency lock used to be
keyed on `external_transaction_id` alone, so if MTN and Orange ever
independently minted the same transaction ID string, the second operator's
real payment would have been silently discarded as a duplicate. The lock is
now `UNIQUE(provider, external_transaction_id)` in both schema files, and
`test_momo_and_orange_callbacks_reusing_the_same_transaction_id_are_independent`
posts the same transaction ID to both routes and asserts both are processed
as distinct payments.

## AI Prompt Ledger

This project was built with Claude Code, directed through recurring
commands: **`/goal`** to hand off a scoped, multi-step directive for
autonomous TDD execution; **`/clear`** to reset context between unrelated
phases so each phase starts from a clean slate instead of accumulating
unrelated history; **`/run`**, used in this project to execute the verified
`git add`/`git commit` for a phase once its full suite was green (rather
than its more common use of launching and driving an app); and **`/plan`**,
available for phases where the approach itself needs to be worked out with
a human before any code is written — not invoked as an explicit command in
this session's transcript; the CLI auto-toggled plan mode around the first
`/goal` below with no separate planning dialogue to log, since each `/goal`
directive already scoped the work precisely enough to go straight into the
TDD red/green/refactor loop.

| Phase | Trigger | Scope | Result |
|---|---|---|---|
| Initial scaffold | *(prompt predates this session's context — not preserved; see commit `abf00a7`)* | Repo scaffold: `app/schema.sql` (6-table schema), `app/database.py`, TDD skill files | `abf00a7 first commit` |
| Mock data generation | *(prompt predates this session's context — not preserved; see commit `268d41b`)* | Messy CSV generator, `ecommerce_orders_raw` loader, `clean_row`/`insert_orders` tests | `268d41b feature: data processing` |
| — | `/clear` | Context reset before Phase 3 | — |
| Phase 3: Data Pipeline, Indexing, Webhooks | `/goal` | ETL from `ecommerce_orders_raw` into the 6 tables with neighborhood normalization; `idx_orders_neighborhood_status`; `docs/indexing_and_query_optimization_report.md`; idempotent `POST /webhook/momo` | Schema migration, `pipeline.py`, indexing report, webhook route/service — 24 tests passing |
| — | `/clear` | Context reset before Phase 4 | — |
| Phase 4: Final Validation | `/goal` | `/docs` interactive API reference (Scalar), order lookup endpoints, this README, full-suite green check | `app/openapi.py`, `app/routes/docs.py`, order lookup routes, this README — 30 tests passing |
| Phase 5: Consolidation & HMAC hardening | `/goal` (same session, no `/clear` before it) | Re-verify all prior phases against elite architecture specs; upgrade webhook auth from a bare shared-secret header to a real HMAC-SHA256 signature over the raw body; move the OpenAPI spec from a Python dict to a static `app/openapi.json` file | `_has_valid_signature()` in `app/routes/webhooks.py`, `app/openapi.json` (replaces `app/openapi.py`), 2 new tests (missing/wrong-secret signature, tampered-payload rejection) — 32 tests passing |
| — | `/clear` | Context reset before this session | — |
| Phase 6: Coaching kickoff | Plain prompt (French) — not a `/goal` | Socratic walkthrough of the existing codebase (`app/`, `config/`, `scripts/`, `tests/`), starting with the schema/ETL pipeline, then webhook idempotence; on request, switched to direct explanations of `clean_row()`/`generate_mock_transactions.py` and a project tree listing | No files changed — exploration and Q&A only |
| Phase 7: Database agnosticism I | `/goal` | Move `app/database.py` → `app/config/database.py`, `app/schema.sql` → `app/database/schema_sqlite.sql`, `app/openapi.json` → `app/docs/openapi.json`; add `get_engine()`/`format_query()`/`DB_ENGINE`-aware `get_connection()`/`init_db()`; write `app/database/schema_postgres.sql` | New `app/config/`, `app/database/`, `app/docs/` layout; `psycopg2-binary` added (lazy-imported) — 37 tests passing; committed via `/run` as `48d0f23` |
| Phase 8: Database agnosticism II | `/goal` | Add `get_last_row_id()` (sqlite `cursor.lastrowid` vs. postgres `currval(pg_get_serial_sequence(...))`); remove `cursor.lastrowid` from `pipeline.py`/`webhooks.py`; wire `format_query()` into every `conn.execute()` in `pipeline.py`, `webhooks.py`, `orders.py` | 39 tests passing; committed via `/run` as `af8a86e`. Flagged as still incomplete for real Postgres use: `schema_postgres.sql` never ran against a live server (none available in this environment) |
| — | Plain prompt | Explain (not implement) how the HMAC layer could extend to a second provider (Orange Money) via URL-based routing | No code changed — design discussion, formalized into Phase 9 below |
| Phase 9: Multi-provider webhooks | `/goal` | Split `/webhook/momo` into `/webhook/momo` + `/webhook/orange` behind a shared `_webhook(provider)` helper and a provider config map; change the idempotency key from `external_transaction_id` alone to `UNIQUE(provider, external_transaction_id)` in both schema files | 4 new tests (Orange tampered/valid, cross-provider secret rejection, same-transaction-id-different-provider independence) — 43 tests passing; committed via `/run` as `957ae90` |
| Phase 10: Orders pagination | `/goal` | Add `page`/`per_page` query params to `GET /orders`, `LIMIT ?/OFFSET ?` through `format_query()`, wrap the response in a `{data, pagination}` envelope, update `openapi.json` | Breaking response-shape change to `GET /orders` (existing tests updated to match); 1 new pagination-slice test — 44 tests passing; committed via `/run` bundled with Phase 11's README update as `3f0f16c` |
| Phase 11: README overhaul | `/goal` | First full rewrite of this README: architecture diagram, project layout, AI Prompt Ledger (this table), Cameroonian-context pagination/dual-operator sections, roadmap | This document, largely as it now reads — committed as `3f0f16c` (bundled with Phase 10's still-uncommitted code, flagged to the user at the time) |
| — | `/goal` ×2 | Fix a real Mermaid syntax bug this ledger's own diagram introduced (`provider="momo"` — double quotes inside a `\|...\|` edge label break GitHub's renderer) actually on lines 57-58, not the line number first guessed; then reformat the project-layout tree with box-drawing characters | `0d9ebc3`, `fc89f34` |
| Phase 12: Aggregator toggle layer | `/goal` | Generic `POST /webhook/aggregator` routing to whichever provider `DEFAULT_AGGREGATOR` names, reusing the existing `_webhook(provider)`/`_PROVIDER_CONFIG` machinery from Phase 9; add `campay`/`smobilpay` config entries; guard against an unconfigured `DEFAULT_AGGREGATOR` value (500, not an unhandled exception) | 3 new tests (default-aggregator secret verification, secret swap on aggregator change, unknown-aggregator 500) — 47 tests passing |
| Phase 13: Data directory cleanup | `/goal` | Move the SQLite database file from the repo root to `data/ecommerce.db` (`run.py`, both `scripts/`); make `scripts/generate_mock_transactions.py`'s `ensure_import_table()`/`insert_orders()` engine-aware via `format_query()` and an engine-picked `CREATE_TABLE_SQL`/`CREATE_TABLE_SQL_POSTGRES` pair instead of hardcoded sqlite DDL | 1 new test (postgres DDL branch, mocked connection) — 48 tests passing. `.gitignore`'s existing `*.db` pattern already covered the new path — verified with `git check-ignore`, no `.gitignore` edit needed. `scripts/load_structured_orders.py::main()` still queries `sqlite_master` directly (sqlite-only) — out of this phase's scope, flagged as a follow-up gap rather than silently left undocumented |
| — | `/goal` ×2 | Two directives describing defects in `scripts/generate_mock_transactions.py` and its own database-path handling that, on inspection, did not exist in the actual file (a "duplicated block before the docstring" and a "truncated `generate_messy_dataframe()`" that was already complete; a "missing postgres branch" that `get_connection()` already handled centrally) | No code changed either time — verified against the real file/module first, reported back with the specific line numbers and function bodies proving the premise was false, declined to fabricate a fix for a non-existent bug |
| Phase 14: Centralized settings | `/goal` | New `app/config/settings.py::Config` (env-var-backed, uppercase class attributes for Flask's `from_object`); `create_app()` takes zero arguments and loads it via `app.config.from_object("app.config.settings.Config")`; `run.py` reduced to `create_app()`; `conftest.py`/`test_webhooks.py::_build_app()` inject isolated test config directly into `app.config` post-construction instead of passing constructor kwargs | 2 new tests (`tests/test_settings.py`: defaults, env-var overrides) — 50 tests passing. `get_connection()`/`get_engine()`/`format_query()` in `app/config/database.py` deliberately still read `os.environ` directly rather than `current_app.config` -- they're also called from `scripts/` with no Flask app context, where `current_app` would raise |
| — | `/goal` | A directive claiming this README was "truncated" and listing specific missing sections -- the same claim (and the same sections, all already present) as part of the Phase 13 request above, this time as a standalone directive | No code changed — re-verified every claimed-missing section by line number (`grep -n "^## \|^### "`), all present and complete; reported back that this repeats an already-checked false premise |
| Phase 15: Clean CRUD architecture + Cameroonian seeder | `/goal` | Deleted the ETL demo (`scripts/generate_mock_transactions.py`, `scripts/load_structured_orders.py`, `app/services/pipeline.py`, `ecommerce_orders_raw`); dropped `order_items` and the denormalized `orders.customer_neighborhood` column, replaced by a direct `orders.product_id`/`quantity`/`unit_price_fcfa` and a join to `addresses`; renamed `idx_orders_neighborhood_status` to `idx_orders_delivery_status`; added full CRUD (`app/services/products.py`, `app/services/customers.py`, `app/routes/products.py`, `app/routes/customers.py`, plus `POST`/`PUT`/`DELETE /orders/{id}`); added `scripts/seed_cameroon_volume.py` (500 Cameroonian orders via `get_connection()`/`format_query()`) | 102 tests passing (new `test_products_routes.py`, `test_customers_routes.py`, `test_seed_cameroon_volume.py`; existing suites updated for the new schema shape) |
| Phase 16: Seeder reusability fix | `/goal` | Fixed a normalization flaw Phase 15's seeder introduced: it created one new `addresses` row per customer, so 500 seeded orders meant ~500 near-duplicate address rows for only 5 real neighborhoods. Made `addresses.customer_id` nullable (a shared logistics reference address has no single owner); reworked `app/services/orders.py::_get_or_create_address()` to key purely on `(neighborhood, city)` instead of `(customer_id, neighborhood)`, used by `POST /orders`/`POST /orders/sync` and this seeder alike; `app/services/customers.py`'s own customer-owned-address path is a deliberately separate, untouched concept. Rewrote `scripts/seed_cameroon_volume.py` into three independent pools (products+5 reference addresses, then 100 customers, then 500 orders randomly picking from the existing pools) plus `reset_database()` (drop-all + `init_db()`) called from `main()` for a pristine slate every run | 107 tests passing (`test_seed_cameroon_volume.py` rewritten around the three-pool structure; new `test_sync_reuses_shared_address_across_different_customers_in_same_neighborhood` regression test proving the fix) |
| Phase 17: Temporal accountability (`updated_at`) | `/goal` | Added an `updated_at` column to `products`, `customers`, and `addresses` (millisecond-resolution default in sqlite — `STRFTIME('%Y-%m-%d %H:%M:%f','now')` — since bare `CURRENT_TIMESTAMP`'s 1-second resolution let an insert-then-update test land in the same second with an unchanged value); `schema_sqlite.sql` gets one `AFTER UPDATE` trigger per table that re-stamps `updated_at` on any modification (safe from recursion since `recursive_triggers` defaults off), `schema_postgres.sql` gets a single reusable `set_updated_at()` `plpgsql` function fired `BEFORE UPDATE` on all three tables. Exposed `updated_at` in `app/services/products.py`/`customers.py`'s `SELECT` column lists so it flows through existing API responses with no route changes. Re-verified the full CRUD grid (products/customers/orders) and the seeder against the new columns | 115 tests passing (new parametrized trigger tests in `test_database.py`, `updated_at`-refresh assertions added to the products/customers `PUT` tests) |
| Phase 18: Payments CRUD | `/goal` | Added full CRUD over the `payments` ledger for direct transactional transparency, separate from `app/services/webhooks.py` (which only ever inserts a payment as a side effect of a provider callback): new `app/services/payments.py` + `app/routes/payments.py` (`GET`/`POST /payments` paginated newest-first, `GET /payments/{external_transaction_id}` with the order nested under `"order"`, `PUT`/`DELETE /payments/{payment_id}` — only `status`/`external_transaction_id` mutable, `UNIQUE(provider, external_transaction_id)` enforced on both create and update). Reused `OrderNotFoundError` from `app/services/webhooks.py` rather than duplicating it. Updated `openapi.json` (`Payment`/`PaymentWithOrder` schemas, all 5 new path/method combinations) and the README's live E2E Scenario 2 with a `GET /payments/{ref}` verification step right after a webhook resolves | 135 tests passing (new `test_payments_routes.py`; `test_docs_routes.py`'s path-set assertion extended) |

Each `/goal` phase followed the same discipline: RED (failing test proving
the gap) → GREEN (minimal code to close it) → REFACTOR (clean up without
changing behavior), verified by running the full suite before considering
the phase done. `python -m pytest -v` is the single source of truth for
"is this actually finished" throughout — not manual inspection.

## Production readiness roadmap

Two gaps stand between this API and a real production deployment, neither
implemented yet:

- **CORS.** There is currently no `Access-Control-Allow-Origin` handling
  anywhere in `app/__init__.py` or the route blueprints, so a browser-based
  dashboard served from a different origin cannot call `/orders` or the
  webhook routes directly. Adding `flask-cors` (or hand-rolled
  `after_request` headers) scoped to the dashboard's actual origin — not a
  blanket `*` — would be the next step.
- **Authentication on lookup routes.** `GET /orders` and
  `GET /orders/{order_id}` are open today: anyone who can reach the server
  can list every customer's orders. The webhook routes are already gated by
  per-provider HMAC signatures, but the read routes have no equivalent.
  Before this serves real delivery drivers or a dashboard, it needs either
  short-lived JWTs issued to authenticated dashboard users, or a simpler
  per-driver static API key (a "driver key") checked in an
  `@before_request` hook — whichever matches how drivers actually
  authenticate in the field (a JWT implies a login flow; a driver key
  implies a provisioning step per device instead).

Also still open from earlier phases: `schema_postgres.sql` and the
PostgreSQL branch of `get_connection()`/`init_db()`/`get_last_row_id()` have
never run against a live PostgreSQL server (none is available in this
project's environment) — validated by code review and mocked unit tests
only, not an end-to-end run. And `scripts/seed_cameroon_volume.py::main()`
still checks for existing tables via `SELECT name FROM sqlite_master WHERE
type='table'` — a sqlite-only system table — so this script would need a
`get_engine()` branch (e.g. `information_schema.tables` on PostgreSQL)
before it could seed a Postgres instance.
