# Billing System — Full Design Specification

## 1. Scope & decisions

Build a **standalone, multi-tenant billing system for generic customer invoicing**, separate from `smart-erp`. It now also includes a **retail counter POS** for tea, soft drinks and food, with per-shop catalogs, staff and reports.

Confirmed choices: Python backend (FastAPI + SQLAlchemy + Alembic + PostgreSQL), React admin + client portal, INR with GST, provider-agnostic payments with a stub provider, and all requested capabilities (customers, invoices, payments, quotes → invoice, recurring invoices, credit notes/refunds, client portal, reports, audit log). The POS is a module inside this app, not a separate service.

**Deliverable:** this document is the design spec. Application code is intentionally out of scope; implementation follows in separate, phase-by-phase work.

Assumptions to flag during review: one supplier GSTIN per tenant; invoice prices are **tax-exclusive** by default (tenant setting can make them inclusive); money is stored as **integer paise**, never floats; email/SMS delivery is via an outbox, not inline in requests.

## 2. Architecture

```
billing/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI app, middleware, exception handlers
│   │   ├── core/                       # config, security (JWT/Argon2), tenancy context, errors
│   │   ├── db/                         # async engine/session, RLS tenant context, base
│   │   ├── models/                     # SQLAlchemy 2.0 ORM models
│   │   ├── schemas/                    # Pydantic v2 request/response DTOs
│   │   ├── services/                   # business logic: invoices, tax, numbering, payments, etc.
│   │   ├── api/v1/routers/             # thin routers: auth, customers, quotes, invoices,
│   │   │                               # payments, credit_notes, recurring, reports, portal, webhooks
│   │   ├── providers/payments/         # protocol + stub (+ future Cashfree/Razorpay adapters)
│   │   ├── workers/                    # Celery tasks + beat schedule
│   │   └── templates/                  # Jinja2 HTML invoice/quote PDF templates
│   ├── alembic/                        # migrations (RLS policies included)
│   ├── tests/                          # unit + integration + tenant-isolation tests
│   └── pyproject.toml
├── frontend/
│   └── src/{admin/,portal/,shared/}    # React + Vite + TS + Tailwind + shadcn/ui
│                                       # TanStack Query, RHF, Zod, Recharts
├── docs/DESIGN.md
└── docker-compose.yml                  # postgres, redis, minio (PDF storage), api, workers
```

Request flow: FastAPI middleware resolves tenant from verified JWT (or portal token), sets a transaction-local `app.tenant_id` for PostgreSQL RLS, then routers delegate to services. Heavy work (PDF rendering, email, recurring runs, reminders) is pushed to Celery via an outbox table. Shared DB with `tenant_id` columns + RLS (not schema-per-tenant); the tenant boundary is enforced twice — application filters and database policies.

## 3. Multi-tenancy, auth, security

- `tenants` own every business row; all queries are tenant-scoped. RLS policies use `current_setting('app.tenant_id')`; a missing context returns zero rows, so a bug cannot leak data.
- JWT access (15 min) + rotating refresh tokens (7 days, reused-refresh detection). Passwords hashed with Argon2. Roles: `OWNER`, `ACCOUNTANT`, `VIEWER`; permissions like `invoices.write`, `payments.refund`, `reports.read` checked by dependency.
- Portal users get a scoped, short-lived magic-link token limited to their customer; no admin permissions.
- Rate limiting, CORS allowlist, security headers, Pydantic validation on every boundary, secrets from env only. No card data is ever stored (gateway-hosted checkout).
- Every mutation writes an append-only `audit_logs` row (actor, action, entity, before/after JSON, IP, user agent). Payment webhook handling is idempotent via `webhook_events.event_id` unique key.

## 4. Data model (key tables)

All tables use UUID PKs, `tenant_id`, `created_at`, `updated_at`; money fields are `*_paise` BigInteger.

| Table | Key fields / purpose |
|---|---|
| `tenants` | name, slug, legal_name, gstin, state_code, address, currency=`INR`, settings JSON (prefixes, terms, tax mode) |
| `users`, `roles`, `permissions`, `user_roles`, `role_permissions` | auth + RBAC, per tenant |
| `customers` | legal_name, display_name, gstin, tax_type (`REGISTERED`/`UNREGISTERED`/`COMPOSITE`), state_code, email, phone, payment_terms_days, status, soft-delete |
| `customer_addresses` | BILLING/SHIPPING, state_code used for GST determination |
| `document_sequences` | tenant_id, kind (`INVOICE`/`QUOTE`/`CREDIT_NOTE`/`PAYMENT`), series, year, next_number — numbered under `SELECT … FOR UPDATE` |
| `quotes` | number, customer_id, status, valid_until, subtotal/discount/tax/total paise, converted_invoice_id, `version` |
| `quote_items` | description, qty, unit_price_paise, discount_paise, tax_rate_pct, tax_paise, hsn_sac |
| `invoices` | number, customer_id, quote_id?, status, issue_date, due_date, subtotal/discount/tax/round_off/total/paid/credited/balance paise, pdf_key, `version` |
| `invoice_items` | as quote_items + CGST/SGST/IGST split snapshot, taxable value |
| `payments` | number (receipt no), customer_id, amount_paise, method (`CASH`/`BANK`/`UPI`/`CARD`/`GATEWAY`), provider, provider_ref, status, paid_at, reference_no |
| `payment_allocations` | payment_id, invoice_id, amount_paise; sum per payment ≤ payment amount; unique(payment_id, invoice_id) |
| `credit_notes` | number, customer_id, invoice_id?, reason, status, total_paise, applied_paise, tax_paise (GST reversal) |
| `credit_note_allocations` | credit_note_id, invoice_id, amount_paise |
| `recurring_schedules` | customer_id, template payload JSON, frequency/interval, start/end, next_run_at, status, last_invoice_id |
| `webhook_events` | provider, event_id (unique), payload, status, attempts |
| `outbox_events` | tenant_id, type, payload, status, attempts, next_attempt_at |
| `reminders` | invoice_id, kind (`PRE_DUE`/`OVERDUE`), due_at, channel, status |
| `attachments` | entity type/id, object-storage key, mime, size |
| `audit_logs` | append-only; actor/action/entity/before/after/ip/user_agent |

## 5. Money, GST, numbering rules

- All calculations in integer paise. Line taxable value = `qty × unit_price − line_discount`; line tax = `round(taxable × rate / 100)`. Invoice-level `round_off` reconciles the sum to the payable paise. Totals are snapshots stored on the document, so later tax-rate or customer edits never mutate issued invoices.
- GST: compare tenant state_code with the customer billing address. Same state → CGST + SGST (half each); different state → IGST. Each line carries HSN/SAC and tax rate. Basic GSTIN format validation; reports provide a GST summary (taxable value + CGST/SGST/IGST) for filing prep. Full GSTR JSON export is out of scope for v1.
- Document numbers are per tenant, per kind, per series, per financial year, allocated inside one DB transaction with a row lock — no duplicate numbers under concurrency. Drafts get no number until issued.
- Optimistic concurrency via `version` on editable documents; stale writes return HTTP 409. Cancelling/voiding is explicit; issued documents are never hard-deleted.

## 6. State machines

- **Quote:** `DRAFT → SENT → ACCEPTED → CONVERTED`; `SENT → REJECTED | EXPIRED` (job); `CONVERTED` is terminal.
- **Invoice:** `DRAFT → SENT → PARTIALLY_PAID → PAID`; any unpaid state `→ OVERDUE` (nightly job); `SENT|PARTIALLY_PAID|OVERDUE → CANCELLED` only when no settled payments exist, otherwise a credit note is required.
- **Payment:** `PENDING → CAPTURED | FAILED`; `CAPTURED → REFUNDED`. A payment may be allocated across multiple invoices; allocations are validated against the payment total in one transaction.
- **Credit note:** `DRAFT → ISSUED → APPLIED | VOID`. Issuing a credit note reduces `credited_paise`/balance and, for tax purposes, records a GST reversal snapshot. Refunds never mutate a paid invoice's original amounts.
- **Recurring schedule:** `ACTIVE → PAUSED → ACTIVE | CANCELLED`; generation is idempotent per `(schedule_id, period)` so a retry cannot double-bill.

## 7. Payment gateway abstraction

`PaymentProvider` protocol: `create_payment(amount_paise, currency, order_ref, return_url)`, `verify_webhook(headers, body)`, `get_status(provider_ref)`, `refund(provider_ref, amount_paise)`. Registry selected by `PAYMENT_PROVIDER` (default `stub`). The stub provider returns a deterministic sandbox ref and marks payments `CAPTURED` in test/dev; it is never enabled in production. Real adapters plug in without touching routers. Gateway checkout is hosted by the provider; webhooks hit `/api/v1/webhooks/payments/{provider}`, are signature-verified, deduplicated by `event_id`, and update payment status + enqueue receipts/notifications via the outbox. Manual methods (cash/bank/UPI) are recorded by staff with an optional attachment.

## 8. API design (v1)

REST under `/api/v1`, envelope `{ data, meta? }` and errors `{ error: { code, message, details? } }`, pagination/filtering/sorting on all lists, `If-Match` version checks on edits.

- Auth: `POST /auth/login|refresh|logout`, `GET /auth/me`
- Tenant: `GET/PATCH /tenants/me`, `GET/PATCH /tenants/me/settings`, users/roles endpoints
- Customers: `GET/POST /customers`, `GET/PATCH/DELETE /customers/{id}`, address sub-resource
- Quotes: CRUD, `POST /quotes/{id}/send|accept|reject|convert`
- Invoices: CRUD, `POST /invoices/{id}/send|cancel`, `GET /invoices/{id}/pdf`, `POST /invoices/{id}/payments`
- Payments: CRUD, `POST /payments/{id}/allocate`, `POST /payments/{id}/refund`, `POST /payments/gateway/session`
- Credit notes: CRUD, `POST /credit-notes/{id}/issue|apply|void`
- Recurring: CRUD, `POST /recurring/{id}/pause|resume|generate-now`
- Reports: `GET /reports/ar-aging|collections|gst-summary|sales|customer-statement`
- Portal: `POST /portal/auth/magic-link`, `GET /portal/invoices|quotes`, `GET /portal/invoices/{id}`, `POST /portal/invoices/{id}/pay` (returns provider session)
- Ops: `GET /health`, `/ready`, webhook route, audit-log query with filters

## 9. UI screens

**Admin (React):** Login; Dashboard (receivables, overdue count, collections trend, GST summary); Customers list/detail/form; Quotes list/editor/preview/send/convert; Invoices list/editor with live line-item tax totals, PDF preview, send, cancel, record payment; Payments list/record-payment/allocate/refund; Credit notes list/editor/apply; Recurring schedules; Reports (AR aging, sales, GST, statements); Settings (tenant/GSTIN/address, document numbering, payment terms, email templates, users & roles); Audit log browser. All lists: search, filters, pagination, skeletons, empty/error states, toasts, confirmation dialogs — no raw CRUD look.

**Client portal:** magic-link sign-in, invoice & quote list/detail, accept/reject quote, pay invoice through the provider session, payment history, PDF downloads.

## 10. Jobs & notifications

Celery + Redis beat: mark invoices overdue nightly, generate due recurring invoices, send pre-due/overdue reminders (e.g. 7/3/0/+7 days), retry failed outbox events, refresh report snapshots. Outbox events are processed at-least-once with idempotent handlers; every attempt is recorded. PDFs are rendered with WeasyPrint from Jinja2 templates and stored in S3-compatible storage; only the object key is persisted.

## 11. Reports & audit

Reports derive from document snapshots, not mutable live values: AR aging buckets (0–30/31–60/61–90/90+), collections by period, GST summary by rate and component, sales by customer/period, customer statement. All report endpoints are permission-gated and tenant-scoped. Audit log is append-only (no update/delete routes) and retains before/after snapshots for sensitive fields; money/status changes always emit an entry.

## 12. Non-functional & test plan

- pytest: unit tests for money/GST/numbering/state transitions; integration tests with a real Postgres test DB; explicit tenant-isolation tests that try cross-tenant IDs and assert zero rows; webhook idempotency and concurrency tests for numbering/payment allocation.
- Frontend: Vitest + Testing Library for tax totals and form validation; Playwright smoke tests for invoice → payment → receipt flow.
- CI (GitHub Actions): lint (ruff/mypy), pytest, frontend typecheck/build, Alembic migration check. Docker Compose for local Postgres/Redis/MinIO; structured JSON logs + request IDs; health/readiness probes; nightly DB backups before any production use.

## 13. Implementation phases (each = migration + backend + tests + UI + docs)

1. Scaffold repo, config, Docker Compose, health checks, Alembic baseline.
2. Tenants, auth, RBAC, RLS enforcement, audit-log plumbing.
3. Customers, addresses, settings, document sequences (concurrency tests).
4. Quotes with GST line items, PDF preview, send/accept/convert.
5. Invoices with GST/round-off/PDF/send/cancel, status transitions.
6. Payments + allocations + receipt numbering, credit notes/refunds, stub gateway + webhooks.
7. Recurring schedules, reminders, outbox workers, client portal.
8. Reports, audit browser, hardening, load/concurrency tests, runbook.
9. Retail counter POS: per-shop catalogs, variants and add-ons, quick cart, cash/UPI/card sales, simple receipts, counter reports and voiding. Deliberately out of scope: table/token management, kitchen display, held orders, inventory, online ordering, live payment gateway/UPI QR and product image upload.

### 13.1 Retail counter POS design

- **Tenancy:** each shop/branch is its own tenant (same isolation as invoicing). Login accepts an optional shop code so the same email may exist in several tenants; `/auth/me` returns `tenant_slug`. A `CASHIER` role has `pos.sell`, `pos.reports` and `catalog.read` but not `pos.void`.
- **Catalog:** `pos_categories → pos_products → pos_variants` plus reusable `pos_modifier_groups → pos_modifiers`, joined to products through `pos_product_modifier_groups`. All rows are tenant-scoped and RLS-protected. Menu prices are tax-inclusive by default so the tile price is the customer price; a tenant setting can switch counter sales to exclusive tax.
- **Sale model:** a counter sale is an `Invoice` with `channel='POS'`, a hidden per-tenant walk-in customer (`Customer.is_walkin`), `pos_meta` JSON (payment method, tendered/change paise, cashier, reference) and item snapshots (variant/add-on names). Numbering uses `POS_SALE → BILL` (`BILL-YYYY-#####`). Payment is recorded at creation, so the invoice is `PAID` immediately.
- **Receipts:** `GET /pos/sales/{id}/receipt` renders a simple 80 mm HTML receipt with shop header/footer, optional GSTIN/phone and cashier, change due and a thank-you line — explicitly not a GST tax invoice. Invoice PDF remains for normal invoices.
- **Reports:** `GET /pos/reports/daily` returns sales count, gross/average, payment mix (CASH/UPI/CARD) and top items for a day; `GET /pos/sales` supports search/filter/CSV and the dashboard shows a counter summary. Voiding is a separate permission-gated action backed by the existing invoice cancel flow.
- **Money:** all amounts remain integer paise in INR. The UI converts rupees ↔ paise at the boundary only.
