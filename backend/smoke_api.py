"""End-to-end HTTP smoke test against a fresh SQLite database."""
import os
from datetime import date
from pathlib import Path

DB = Path("smoke_billing.db")
if DB.exists():
    DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["JWT_SECRET"] = "smoke-only-secret-long-enough-for-hs256"
os.environ["WEBHOOK_SECRET"] = "smoke-webhook-secret"

from fastapi.testclient import TestClient

from app.db.session import SessionLocal, init_db
from app.services.auth_service import create_tenant_with_owner

import asyncio

async def seed():
    await init_db()
    async with SessionLocal() as s:
        await create_tenant_with_owner(
            s, name="Acme Studio", slug="acme", email="owner@acme.example.com",
            password="Password123!", full_name="Demo Owner", state_code="KA",
            gstin="29ABCDE1234F1Z5",
        )
        await s.commit()

asyncio.run(seed())

from app.main import app

client = TestClient(app)
BASE = "/api/v1"
checks = []


def call(method, path, token=None, code=200, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.request(method, BASE + path, headers=headers, **kwargs)
    response.expected_code = code
    checks.append((method.upper(), path, response.status_code))
    return response


def expect(response):
    code = getattr(response, "expected_code", 200)
    assert response.status_code == code, f"{response.request.method} {response.request.url} -> {response.status_code}: {response.text[:400]}"
    return response.json()["data"]


login = expect(call("POST", "/auth/login", json={"email": "owner@acme.example.com", "password": "Password123!"}))
token = login["access_token"]
expect(call("GET", "/auth/me", token))

customer = expect(call("POST", "/customers", token, json={
    "legal_name": "Bengaluru Traders", "display_name": "Bengaluru Traders",
    "state_code": "KA", "gstin": "29AABCI9876K1Z9", "tax_type": "REGISTERED",
    "email": "billing@bengaluru.example.com",
    "addresses": [{"line1": "12 MG Road", "city": "Bengaluru", "state_code": "KA", "pincode": "560001"}],
}, code=201))
assert customer["addresses"][0]["city"] == "Bengaluru"
cid = customer["id"]

invoice = expect(call("POST", "/invoices", token, json={
    "customer_id": cid, "issue_date": "2026-11-21",
    "items": [{"description": "Design work", "qty": 1, "unit_price_paise": 100000, "tax_rate_pct": 18}],
}, code=201))
assert invoice["number"] is None
iid = invoice["id"]
invoice = expect(call("POST", f"/invoices/{iid}/send", token))
assert invoice["number"] and invoice["status"] == "SENT"

payment = expect(call("POST", "/payments", token, json={
    "customer_id": cid, "amount_paise": 50000, "method": "BANK",
    "allocations": [{"invoice_id": iid, "amount_paise": 50000}],
}, code=201))
assert payment["allocated_paise"] == 50000 and len(payment["allocations"]) == 1, payment
pid = payment["id"]
expect(call("GET", f"/payments/{pid}", token))
expect(call("GET", "/payments", token))

quote = expect(call("POST", "/quotes", token, json={
    "customer_id": cid, "issue_date": "2026-11-21", "valid_until": "2026-12-21",
    "items": [{"description": "Brand refresh", "qty": 2, "unit_price_paise": 25000, "tax_rate_pct": 18}],
}, code=201))
expect(call("POST", f"/quotes/{quote['id']}/send", token))
expect(call("POST", f"/quotes/{quote['id']}/accept", token))
converted = expect(call("POST", f"/quotes/{quote['id']}/convert", token, code=201))
assert converted["quote_id"] == quote["id"]

note = expect(call("POST", "/credit-notes", token, json={
    "customer_id": cid, "invoice_id": iid, "reason": "Discount correction",
    "items": [{"description": "Correction", "qty": 1, "unit_price_paise": 10000, "tax_rate_pct": 18}],
}, code=201))
expect(call("POST", f"/credit-notes/{note['id']}/issue", token))
applied = expect(call("POST", f"/credit-notes/{note['id']}/apply", token, json={}))
assert applied["applied_paise"] == 11800

schedule = expect(call("POST", "/recurring", token, json={
    "customer_id": cid, "name": "Monthly retainer", "frequency": "MONTHLY", "interval": 1,
    "start_date": "2026-12-01",
    "template": {"items": [{"description": "Retainer", "qty": 1, "unit_price_paise": 50000, "tax_rate_pct": 18}]},
}, code=201))
expect(call("POST", f"/recurring/{schedule['id']}/generate-now", token))

expect(call("GET", "/reports/dashboard", token))
expect(call("GET", "/reports/gst-summary", token))
expect(call("GET", "/reports/sales?months=12", token))
expect(call("GET", "/reports/collections?months=12", token))
expect(call("GET", "/reports/ar-aging", token))
expect(call("GET", "/tenants/me", token))
expect(call("GET", "/tenants/users", token))
expect(call("GET", "/tenants/roles", token))
expect(call("GET", "/audit", token))
expect(call("GET", "/invoices", token))
expect(call("GET", "/customers", token))
expect(call("GET", "/quotes", token))
expect(call("GET", "/credit-notes", token))
expect(call("GET", "/recurring", token))

pdf = call("GET", f"/invoices/{iid}/pdf", token)
assert pdf.status_code == 200, pdf.text[:400]
assert "TAX INVOICE" in pdf.text

# ---------- Retail counter POS ----------
category = expect(call("POST", "/catalog/categories", token, json={
    "name": "Beverages", "color": "#0369a1", "sort_order": 1, "is_active": True,
}, code=201))
group = expect(call("POST", "/catalog/modifier-groups", token, json={
    "name": "Milk", "min_select": 0, "max_select": 1, "is_required": False,
    "modifiers": [{"name": "Extra milk", "price_paise": 500, "sort_order": 1, "is_active": True}],
}, code=201))
product = expect(call("POST", "/catalog/products", token, json={
    "category_id": category["id"], "name": "Masala Chai", "base_price_paise": 2500,
    "tax_rate_pct": 5, "hsn_sac": "996331",
    "variants": [{"name": "Small", "price_paise": 2500, "is_default": True, "sort_order": 1, "is_active": True}],
    "modifier_group_ids": [group["id"]],
}, code=201))
menu = expect(call("GET", "/pos/menu", token))
assert any(cat["name"] == "Beverages" for cat in menu), menu

sale = expect(call("POST", "/pos/sales", token, json={
    "items": [{
        "product_id": product["id"],
        "variant_id": product["variants"][0]["id"],
        "modifier_ids": [group["modifiers"][0]["id"]],
        "qty": 2,
    }],
    "discount_paise": 0,
    "payment": {"method": "CASH", "tendered_paise": 10000},
}, code=201))
assert sale["channel"] == "POS" and sale["status"] == "PAID", sale
assert sale["number"].startswith("BILL-"), sale["number"]
assert sale["total_paise"] == 6000, sale["total_paise"]
assert sale["pos_meta"]["change_paise"] == 4000, sale["pos_meta"]

detail = expect(call("GET", f"/pos/sales/{sale['id']}", token))
assert detail["id"] == sale["id"]
receipt = call("GET", f"/pos/sales/{sale['id']}/receipt", token)
assert receipt.status_code == 200, receipt.text[:400]
assert "Masala Chai" in receipt.text

upi_sale = expect(call("POST", "/pos/sales", token, json={
    "items": [{"product_id": product["id"], "qty": 1}],
    "payment": {"method": "UPI", "reference_no": "SMOKEUPI1"},
}, code=201))
assert upi_sale["pos_meta"]["method"] == "UPI"

report = expect(call("GET", "/pos/reports/daily", token, params={"day": date.today().isoformat()}))
assert report["sales_count"] == 2, report
assert report["payment_mix"]["CASH"]["count"] == 1
assert report["payment_mix"]["UPI"]["count"] == 1
assert report["gross_paise"] == 8500, report

sales = expect(call("GET", "/pos/sales", token, params={"limit": 10}))
assert len(sales) == 2
filtered = expect(call("GET", "/pos/sales", token, params={"payment": "UPI"}))
assert len(filtered) == 1

expect(call("POST", f"/pos/sales/{sale['id']}/void", token, json={"reason": "Smoke void"}))
report = expect(call("GET", "/pos/reports/daily", token, params={"day": date.today().isoformat()}))
assert report["sales_count"] == 1, report

portal = expect(call("POST", "/portal/token", json={"email": "billing@bengaluru.example.com", "tenant_slug": "acme"}))
ptoken = portal["access_token"]
expect(call("GET", "/portal/me", ptoken))
expect(call("GET", "/portal/invoices", ptoken))
expect(call("GET", "/portal/quotes", ptoken))

print(f"SMOKE OK — {len(checks)} HTTP calls")
for method, path, status in checks:
    print(f"  {status} {method:6} {path}")
try:
    if DB.exists():
        DB.unlink()
except PermissionError:
    pass  # engine still holds the file on Windows; next run unlinks it up front
