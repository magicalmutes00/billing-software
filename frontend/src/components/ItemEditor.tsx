import { Plus, Trash2 } from 'lucide-react';
import { inr } from '../lib/format';
import { Button, Input } from './ui';
import type { Item } from '../types';

export function newItem(): Item {
  return { description: '', hsn_sac: '', qty: 1, unit_price_paise: 0, discount_paise: 0, tax_rate_pct: 18 };
}

export function estimate(items: Item[]) {
  let subtotal = 0;
  let discount = 0;
  let tax = 0;
  for (const item of items) {
    const gross = Math.round(item.qty * item.unit_price_paise);
    const afterDiscount = Math.max(0, gross - item.discount_paise);
    subtotal += gross;
    discount += item.discount_paise;
    tax += Math.round((afterDiscount * item.tax_rate_pct) / 100);
  }
  const total = subtotal - discount + tax;
  return { subtotal, discount, tax, total };
}

export function ItemEditor({ items, onChange }: { items: Item[]; onChange: (items: Item[]) => void }) {
  function update(index: number, patch: Partial<Item>) {
    onChange(items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }
  const totals = estimate(items);

  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[720px] text-left text-xs">
          <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-muted">
            <tr>
              <th className="w-[36%] px-3 py-2 font-semibold">Description</th>
              <th className="px-3 py-2 font-semibold">HSN/SAC</th>
              <th className="w-16 px-3 py-2 text-right font-semibold">Qty</th>
              <th className="w-32 px-3 py-2 text-right font-semibold">Rate (₹)</th>
              <th className="w-28 px-3 py-2 text-right font-semibold">Disc (₹)</th>
              <th className="w-20 px-3 py-2 text-right font-semibold">Tax %</th>
              <th className="w-28 px-3 py-2 text-right font-semibold">Amount</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {items.map((item, index) => (
              <tr key={index}>
                <td className="px-3 py-2"><Input className="py-1.5 text-xs" value={item.description} placeholder="Item description" onChange={(e) => update(index, { description: e.target.value })} /></td>
                <td className="px-3 py-2"><Input className="py-1.5 text-xs" value={item.hsn_sac || ''} placeholder="998231" onChange={(e) => update(index, { hsn_sac: e.target.value })} /></td>
                <td className="px-3 py-2"><Input type="number" min="0" step="0.01" className="py-1.5 text-right text-xs" value={item.qty} onChange={(e) => update(index, { qty: Number(e.target.value) })} /></td>
                <td className="px-3 py-2"><Input type="number" min="0" step="0.01" className="py-1.5 text-right text-xs" value={(item.unit_price_paise / 100).toFixed(2)} onChange={(e) => update(index, { unit_price_paise: Math.round(Number(e.target.value) * 100) })} /></td>
                <td className="px-3 py-2"><Input type="number" min="0" step="0.01" className="py-1.5 text-right text-xs" value={(item.discount_paise / 100).toFixed(2)} onChange={(e) => update(index, { discount_paise: Math.round(Number(e.target.value) * 100) })} /></td>
                <td className="px-3 py-2"><Input type="number" min="0" max="100" step="0.5" className="py-1.5 text-right text-xs" value={item.tax_rate_pct} onChange={(e) => update(index, { tax_rate_pct: Number(e.target.value) })} /></td>
                <td className="px-3 py-2 text-right font-medium text-ink">{inr(Math.round(item.qty * item.unit_price_paise - item.discount_paise + ((item.qty * item.unit_price_paise - item.discount_paise) * item.tax_rate_pct) / 100))}</td>
                <td className="px-2 py-2"><button type="button" onClick={() => onChange(items.filter((_, i) => i !== index))} className="rounded-md p-1.5 text-muted hover:bg-rose-50 hover:text-rose-600" aria-label="Remove item"><Trash2 size={14} /></button></td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={8} className="py-8 text-center text-muted">Add at least one line item.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <Button type="button" size="sm" onClick={() => onChange([...items, newItem()])}><Plus size={14} /> Add item</Button>
        <div className="flex gap-6 text-xs text-muted">
          <span>Subtotal <b className="ml-2 text-ink">{inr(totals.subtotal)}</b></span>
          <span>Discount <b className="ml-2 text-ink">{inr(totals.discount)}</b></span>
          <span>Tax <b className="ml-2 text-ink">{inr(totals.tax)}</b></span>
          <span className="text-sm font-semibold text-ink">Total {inr(totals.total)}</span>
        </div>
      </div>
    </div>
  );
}
