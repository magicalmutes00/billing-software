from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.schemas.documents import ItemIn


def to_paise(value: float | int | Decimal) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_rupee(paise: int) -> int:
    return int((Decimal(paise) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 100


def calculate_items(items: list[ItemIn], *, tax_mode: str = "EXCLUSIVE", same_state: bool = True) -> dict:
    """Calculate line-level taxable values and GST splits. All money in integer paise."""
    lines: list[dict] = []
    subtotal = discount = tax_total = total = 0
    cgst_total = sgst_total = igst_total = 0

    for pos, item in enumerate(items):
        gross = to_paise(Decimal(str(item.qty)) * Decimal(item.unit_price_paise))
        disc = min(item.discount_paise, gross)
        if tax_mode == "INCLUSIVE":
            line_total = gross - disc
            taxable = to_paise(Decimal(line_total) / (Decimal(1) + Decimal(str(item.tax_rate_pct)) / Decimal(100)))
            tax = line_total - taxable
        else:
            taxable = gross - disc
            tax = to_paise(Decimal(taxable) * Decimal(str(item.tax_rate_pct)) / Decimal(100))
            line_total = taxable + tax

        if same_state:
            cgst = to_paise(Decimal(tax) / Decimal(2))
            sgst = tax - cgst
            igst = 0
        else:
            cgst = sgst = 0
            igst = tax

        line = {
            "description": item.description,
            "hsn_sac": item.hsn_sac,
            "qty": item.qty,
            "unit_price_paise": item.unit_price_paise,
            "discount_paise": disc,
            "tax_rate_pct": item.tax_rate_pct,
            "taxable_paise": taxable,
            "cgst_paise": cgst,
            "sgst_paise": sgst,
            "igst_paise": igst,
            "tax_paise": tax,
            "total_paise": line_total,
            "position": pos,
        }
        lines.append(line)
        subtotal += gross
        discount += disc
        tax_total += tax
        total += line_total
        cgst_total += cgst
        sgst_total += sgst
        igst_total += igst

    rounded_total = round_rupee(total)
    return {
        "lines": lines,
        "subtotal_paise": subtotal,
        "discount_paise": discount,
        "tax_paise": tax_total,
        "cgst_paise": cgst_total,
        "sgst_paise": sgst_total,
        "igst_paise": igst_total,
        "total_paise": total,
        "round_off_paise": rounded_total - total,
        "payable_paise": rounded_total,
    }


def is_same_state(supplier_state: str, customer_state: str) -> bool:
    return supplier_state.upper() == customer_state.upper()
