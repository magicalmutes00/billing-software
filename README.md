# Billing — multi-tenant invoicing + retail counter POS

Design spec: `docs/DESIGN.md`.

The app also includes a retail counter POS for tea, soft drinks and food. Each shop is a separate tenant with its own catalog, staff, sales and reports. Invoices, quotes, payments and the client portal continue to work unchanged.

## Docker Compose (full stack)

```bash
cd billing
docker compose up --build
```

This starts PostgreSQL, Redis, the FastAPI backend and the React frontend. The backend container runs `alembic upgrade head` and the idempotent demo seed on startup.

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8010/docs
- PostgreSQL: `localhost:5432` (`billing` / `billing` / `billing`)
- Demo login: `owner@acme.example.com` / `Password123!`
- Client portal: `billing@bengaluru.example.com`, tenant slug `acme`

Retail counter demo (seeded on startup):

| Login | Password | Shop code | Access |
|---|---|---|---|
| `owner@chaicorner.example.com` | `Password123!` | `chai-indiranagar` or `chai-koramangala` | Full admin for one shop |
| `cashier@chaicorner.example.com` | `Password123!` | `chai-indiranagar` | Counter only (sell, reports, read catalog) |

The shop code is required when the same email exists in more than one tenant. Enter it in the **Shop code** field on the login page. Each shop has its own categories, products, add-ons, staff and sales.

Stop with `docker compose down`. Add `-v` to also delete the database volume.

## Local development (SQLite, no services required)

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
python seed.py
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs. Demo login: `owner@acme.example.com` / `Password123!`. Client portal demo: `billing@bengaluru.example.com`, tenant slug `acme`. Retail demo: `owner@chaicorner.example.com` / `Password123!` with shop code `chai-indiranagar` or `chai-koramangala`; counter demo: `cashier@chaicorner.example.com` / `Password123!` with shop code `chai-indiranagar`.

## Retail counter POS

Each shop is a separate tenant, so catalogs, staff, sales and reports never mix. A counter sale is stored as a paid invoice (`channel='POS'`) with a hidden per-tenant walk-in customer and a `BILL-YYYY-#####` number. Receipts are simple 80 mm receipts, not GST tax invoices.

- **Counter** (`/pos`): tiled menu with search/category filters, size variants, add-on modifier groups, cart with discounts, cash/UPI/card payment and a printable receipt.
- **Products** (`/catalog`): manage categories, products, variants and add-on groups.
- **Counter sales** (`/pos/sales`): search, filter, view, reprint and void sales; daily report with payment mix and top items; CSV export.
- **Settings → Counter receipt**: header, footer, phone, GSTIN visibility, tax mode (inclusive/exclusive) and round-off.

API under `/api/v1` (all responses wrapped in `{ "data": ... }`):

- `GET /pos/menu`, `GET|POST /catalog/categories`, `GET|POST /catalog/products`, `GET|POST /catalog/modifier-groups` (+ `PATCH`/`DELETE` for each).
- `POST /pos/sales`, `GET /pos/sales`, `GET /pos/sales/{id}`, `GET /pos/sales/{id}/receipt`, `POST /pos/sales/{id}/void`, `GET /pos/reports/daily`.

Permissions: `pos.sell` (counter), `catalog.read|write`, `pos.reports`, `pos.void`. The cashier demo has `pos.sell`, `pos.reports` and `catalog.read` but not `pos.void`.

Key implementation choices: money stays integer paise (INR); menu prices are tax-inclusive by default so the tile price is the customer price; no live payment gateway, product image upload or table/token/kitchen/inventory features.

### Phase 2 — counter operations, payments & reporting

- **Mixed-tender split payments**: `POST /pos/sales` accepts `payments: [{method, amount_paise, tendered_paise?, reference_no?}]`; the legs must sum to the bill total. The counter payment modal has a "Split payment" toggle.
- **UPI QR at checkout**: set `pos_upi_id`/`pos_upi_name` in Settings → Counter receipt; the UPI tab renders a server-generated SVG QR (`GET /pos/upi-qr?amount_paise=&tn=`) encoding a `upi://pay` intent for the exact amount. Manual confirmation — not a gateway collect.
- **Shareable receipts**: `POST /pos/sales/{id}/share-token` returns a 7-day token; `GET /public/receipt/{token}` renders the receipt without login. The UI opens a WhatsApp deep link and copies the URL.
- **Held / parked orders**: `POST|GET /pos/holds`, `POST /pos/holds/{id}/resume`, `DELETE /pos/holds/{id}`. Server-side, so any register in the shop can resume.
- **Shifts / cash drawer**: `POST /pos/shifts/open`, `/shifts/close`, `/shifts/cash-movement`, `GET /shifts/current`, `/shifts/x-report`, `/shifts/{id}/z-report`. Expected cash = float + cash sales + cash-in − cash-out − refunds; variance recorded at close (never blocks). Blind close hides expected cash from the cashier.
- **Partial refunds**: `POST /pos/sales/{id}/refund` (`amount_paise` or `lines`), gated by `pos.void`; reports net of refunds.
- **Line-level discounts**: `PosItemIn.discount_paise` / `discount_pct`.
- **Manager PIN override**: `POST /auth/pin` sets a PIN; `POST /auth/verify-pin` returns a 5-minute approval token granting one permission, sent as `X-Approval-Token` so a cashier can approve a void/refund without a full owner login.
- **SKU / barcode**: optional `sku`/`barcode` on products for fast entry.
- **Reporting**: `GET /pos/reports/range?date_from=&date_to=` (with previous-period comparison), `/reports/items`, `/reports/cashiers`, `/pos/sales/export` (CSV), and `GET /reports/shops` (consolidated counter KPIs across every shop the user's email belongs to). The dashboard shows an "All shops today" card when more than one shop is accessible.

Offline-first billing is designed but deferred to Phase 3 — see `docs/OFFLINE_DESIGN.md`.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000` by default. If the backend runs elsewhere, set `BILLING_API_TARGET` before starting Vite, for example `BILLING_API_TARGET=http://127.0.0.1:8010 npm run dev`.

## Migrations and RLS

Migrations live in `backend/alembic`. Revision `0001` creates all tables and enables PostgreSQL row-level security per tenant; `0002_retail_pos` adds the catalog/POS tables and invoice channel metadata; `0003_hardening` adds POS composite indexes and provisions the non-owner `billing_app` role; `0004_counter_ops` adds PIN, SKU/barcode, held orders, shifts and cash movements. All use idempotent existence checks so fresh SQLite and PostgreSQL databases both work. The Compose backend container applies migrations automatically; for a local PostgreSQL instance run:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://billing:billing@localhost:5432/billing alembic upgrade head
```

The SQLite dev database is created automatically at startup and is only for local use.

To verify the POS catalog tables and their tenant RLS policies on PostgreSQL after `alembic upgrade head`:

```bash
docker compose exec postgres psql -U billing -d billing -c \
  "SELECT tablename, policyname FROM pg_policies WHERE tablename IN ('product_categories','products','product_variants','modifier_groups','modifiers','product_modifier_groups') ORDER BY tablename;"
```

All six tables should have a `tenant_isolation` policy. **RLS is enforced for the runtime app**: Compose sets `APP_DATABASE_URL` to the non-owner `billing_app` role (provisioned by `0003`), which is subject to RLS, while migrations, seed and cross-tenant auth resolution (login/refresh/portal-token/webhooks) use the owner `DATABASE_URL`. Set `app.tenant_id` per request; a connection scoped to tenant A cannot read tenant B rows even without an explicit filter.

## Tests

```bash
cd backend && pytest -q
python smoke_api.py   # full HTTP smoke test against a temporary SQLite database
```

PostgreSQL-only hardening tests (numbering concurrency + RLS isolation) skip unless `PG_TEST_URL` is set:

```bash
PG_TEST_URL=postgresql+asyncpg://billing:billing@localhost:5432/billing pytest tests/test_postgres.py -q
```

Frontend tests:

```bash
cd frontend
npm run test    # Vitest unit tests (counter cart/money math)
npm run e2e     # Playwright E2E against the running stack (npx playwright install chromium first)
```
