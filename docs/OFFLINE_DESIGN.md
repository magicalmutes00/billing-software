# Offline-First Counter — Design (Phase 3 roadmap)

Status: **design + spike only**. Not implemented in Phase 2. This is the largest
remaining market gap: Petpooja, GoFrugal, Vyapar, Tap & Bill, Zoho POS and Wink all
keep billing during internet outages and sync afterwards.

## Goal
The counter keeps selling when the network drops. Sales, holds, shifts and cash
movements are captured locally and synced once connectivity returns, with
**server-authoritative BILL numbering** and exactly-once delivery.

## Architecture

### Client (browser / PWA)
- **Service worker** caches the app shell and the last `/pos/menu` payload.
- **IndexedDB** stores:
  - `menu` snapshot (categories, products, variants, modifiers, prices, tax rates).
  - `outbox` of pending operations: `sale`, `hold`, `shift.open`, `shift.close`,
    `cash.movement`, `refund`. Each has a client-generated `idempotency_key` (UUID),
    a `local_seq`, payload, and `created_at`.
  - `local_state`: open shift, held orders, cached settings.
- **Online/Offline indicator** + pending-count badge in the counter header.
- When offline, `create_sale` writes to the outbox and returns a **provisional**
  receipt with a local reference (e.g. `LOCAL-0001`), clearly marked "pending sync".
  No real BILL number is invented client-side.

### Sync protocol
- `POST /api/v1/pos/sync` accepts a batch:
  ```json
  { "device_id": "...", "operations": [ { "idempotency_key": "...", "type": "sale", "payload": {...} } ] }
  ```
- Server processes operations **in order**, deduplicating by `idempotency_key`
  (new table `sync_operations(idempotency_key PK, device_id, type, result_json, created_at)`).
- For each `sale`, the server runs the normal `create_sale` path (real BILL number,
  tax, payments, shift cash movement) and returns the authoritative invoice.
- Response maps `idempotency_key -> {invoice_id, number, status}` so the client can
  replace provisional receipts with real ones and reprint if needed.
- Conflicts (e.g. product price changed while offline) are resolved
  **server-authoritative**: the server recomputes totals from current catalog; the
  client surfaces a reconciliation note rather than silently trusting local prices.

### Numbering & ordering
- BILL numbers are assigned only by the server (`numbering.next_number`, already
  race-safe via `INSERT … ON CONFLICT`). Offline sales never pre-allocate numbers.
- `local_seq` preserves the order sales were rung; the server applies them in that
  order per device so the counter's sequence is sensible.

### Shifts & cash offline
- Shift open/close and cash movements queue like sales. Expected-cash reconciliation
  is computed server-side on sync; the client shows a provisional drawer total.
- A shift cannot be closed online until its queued sales are synced (guard in UI).

## Data model additions (when built)
- `sync_operations` (idempotency ledger).
- `Invoice.pos_meta.local_ref` / `device_id` for traceability.
- Client IndexedDB schema (no server migration).

## Spike acceptance (Phase 3 entry criterion)
1. With network disabled, ring up 3 sales → provisional receipts, outbox count = 3.
2. Re-enable network → sync assigns 3 unique sequential BILL numbers; receipts update.
3. Re-sending the same batch creates **no duplicates** (idempotency).
4. Refresh/restart while offline preserves the outbox and open shift.

## Risks / open questions
- Price drift while offline (server-authoritative reconciliation UX).
- Multi-device counter ordering and shift ownership across registers.
- Payment capture for UPI/CARD offline (record as pending reference; reconcile later).
- Storage limits and eviction policy for long outages.

## Why deferred
Phase 2 delivered the counter-operations table stakes (holds, shifts, split tender,
refunds, line discounts, SKU) plus UPI QR and receipt sharing. Offline-first is a
substantial architectural effort (service worker, IndexedDB, sync protocol,
reconciliation) best done as its own phase once Phase 2 is stable in production.
