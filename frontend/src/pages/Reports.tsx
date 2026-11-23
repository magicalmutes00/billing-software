import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, FileDown, ReceiptText } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { apiErrorMessage, apiGet } from '../lib/api';
import { inr } from '../lib/format';
import { Button, Card, CardHeader, PageHeader, Skeleton } from '../components/ui';

type GstRow = { rate: number; type: string; taxable_paise: number; cgst_paise: number; sgst_paise: number; igst_paise: number; tax_paise: number };
type Series = { month: string; amount_paise: number };
type Aging = { bucket: string; amount_paise: number };

const tabs = [
  { key: 'gst', label: 'GST summary', icon: ReceiptText },
  { key: 'sales', label: 'Sales & collections', icon: BarChart3 },
  { key: 'aging', label: 'Receivables aging', icon: FileDown },
] as const;

export default function Reports() {
  const [tab, setTab] = useState<(typeof tabs)[number]['key']>('gst');
  const gst = useQuery({ queryKey: ['gst'], queryFn: async () => (await apiGet<GstRow[]>('/reports/gst-summary')).data });
  const sales = useQuery({ queryKey: ['sales'], queryFn: async () => (await apiGet<Series[]>('/reports/sales?months=12')).data });
  const collections = useQuery({ queryKey: ['collections'], queryFn: async () => (await apiGet<Series[]>('/reports/collections?months=12')).data });
  const aging = useQuery({ queryKey: ['aging'], queryFn: async () => (await apiGet<Aging[]>('/reports/ar-aging')).data });
  const error = gst.error || sales.error || collections.error || aging.error;

  function exportCsv() {
    let rows: (string | number)[][] = [];
    if (tab === 'gst') {
      rows = [['Rate', 'Type', 'Taxable', 'CGST', 'SGST', 'IGST', 'Total tax'], ...(gst.data || []).map((r) => [r.rate, r.type, r.taxable_paise / 100, r.cgst_paise / 100, r.sgst_paise / 100, r.igst_paise / 100, r.tax_paise / 100])];
    } else if (tab === 'sales') {
      rows = [['Month', 'Sales', 'Collections'], ...(sales.data || []).map((r, i) => [r.month, r.amount_paise / 100, (collections.data?.[i]?.amount_paise || 0) / 100])];
    } else {
      rows = [['Bucket', 'Amount'], ...(aging.data || []).map((r) => [r.bucket, r.amount_paise / 100])];
    }
    const csv = rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `billing-${tab}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (error) return <div className="text-sm text-rose-600">{apiErrorMessage(error)}</div>;

  return (
    <div>
      <PageHeader title="Reports" subtitle="GST, sales, collections and receivables analytics." actions={<Button onClick={exportCsv}><FileDown size={15} /> Export CSV</Button>} />
      <div className="mb-5 flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button key={item.key} onClick={() => setTab(item.key)} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${tab === item.key ? 'bg-brand-600 text-white shadow-sm' : 'bg-white text-muted ring-1 ring-line hover:text-ink'}`}><item.icon size={15} /> {item.label}</button>
        ))}
      </div>

      {tab === 'gst' && (
        <Card>
          <CardHeader title="GST summary" subtitle="Taxable value and tax by rate · intra-state (CGST+SGST) vs inter-state (IGST)" />
          {gst.isLoading ? <Skeleton rows={6} /> : (
            <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-muted"><tr><th className="px-5 py-3 font-semibold">Rate</th><th className="px-5 py-3 font-semibold">Type</th><th className="px-5 py-3 text-right font-semibold">Taxable value</th><th className="px-5 py-3 text-right font-semibold">CGST</th><th className="px-5 py-3 text-right font-semibold">SGST</th><th className="px-5 py-3 text-right font-semibold">IGST</th><th className="px-5 py-3 text-right font-semibold">Total tax</th></tr></thead>
              <tbody className="divide-y divide-line">{(gst.data || []).map((row, index) => <tr key={index}><td className="px-5 py-3 font-medium text-ink">{row.rate}%</td><td className="px-5 py-3 text-xs text-muted">{row.type === 'IGST' ? 'Inter-state' : 'Intra-state'}</td><td className="px-5 py-3 text-right">{inr(row.taxable_paise)}</td><td className="px-5 py-3 text-right text-muted">{inr(row.cgst_paise)}</td><td className="px-5 py-3 text-right text-muted">{inr(row.sgst_paise)}</td><td className="px-5 py-3 text-right text-muted">{inr(row.igst_paise)}</td><td className="px-5 py-3 text-right font-medium">{inr(row.tax_paise)}</td></tr>)}
                {(gst.data || []).length === 0 && <tr><td colSpan={7} className="px-5 py-12 text-center text-sm text-muted">No tax data yet.</td></tr>}
              </tbody></table></div>
          )}
        </Card>
      )}

      {tab === 'sales' && (
        <Card>
          <CardHeader title="Sales vs collections" subtitle="Last 12 months" />
          <div className="h-96 p-5">
            {sales.isLoading || collections.isLoading ? <Skeleton rows={6} /> : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={(sales.data || []).map((row, i) => ({ month: row.month, sales: row.amount_paise / 100, collections: (collections.data?.[i]?.amount_paise || 0) / 100 }))} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef0f3" />
                  <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: '#667085' }} />
                  <YAxis tickFormatter={(v: number) => `₹${Math.round(v / 100000)}L`} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: '#667085' }} />
                  <Tooltip formatter={(value) => inr(Number(value) * 100)} contentStyle={{ borderRadius: 10, border: '1px solid #e4e7ec', fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="sales" name="Sales" fill="#3538cd" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="collections" name="Collections" fill="#10b981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
      )}

      {tab === 'aging' && (
        <Card>
          <CardHeader title="Receivables aging" subtitle="Open invoice balance bucketed by days past due" />
          {aging.isLoading ? <Skeleton rows={5} /> : (
            <div className="space-y-5 p-6">
              {(aging.data || []).map((row) => {
                const total = (aging.data || []).reduce((sum, item) => sum + item.amount_paise, 0) || 1;
                const percent = Math.round((row.amount_paise / total) * 100);
                return (
                  <div key={row.bucket}>
                    <div className="mb-1.5 flex justify-between text-sm"><span className="font-medium text-ink">{row.bucket} days</span><span className="font-semibold text-ink">{inr(row.amount_paise)} <span className="ml-2 text-xs font-normal text-muted">{percent}%</span></span></div>
                    <div className="h-3 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-brand-500" style={{ width: `${percent}%` }} /></div>
                  </div>
                );
              })}
              {(aging.data || []).length === 0 && <div className="py-16 text-center text-sm text-muted">No outstanding receivables.</div>}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
