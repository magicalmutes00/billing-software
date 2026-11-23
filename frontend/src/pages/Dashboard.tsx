import { useQuery } from '@tanstack/react-query';
import { ArrowDownRight, ArrowUpRight, CircleDollarSign, Clock3, FileText, TrendingUp } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Link } from 'react-router-dom';
import { ShoppingCart } from 'lucide-react';
import { apiGet, apiErrorMessage } from '../lib/api';
import { inr, shortDate, statusTone, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, PageHeader, Skeleton } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import type { DailyReport, Invoice, ShopSummary } from '../types';

type DashboardData = {
  billed_paise: number;
  collected_paise: number;
  outstanding_paise: number;
  overdue_paise: number;
  this_month_paise: number;
  invoice_counts: Record<string, number>;
};

type Series = { month: string; amount_paise: number };
type Aging = { bucket: string; amount_paise: number };

export default function Dashboard() {
  const { can } = useAuth();
  const dashboard = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await apiGet<DashboardData>('/reports/dashboard')).data,
  });
  const collections = useQuery({
    queryKey: ['collections'],
    queryFn: async () => (await apiGet<Series[]>('/reports/collections?months=12')).data,
  });
  const aging = useQuery({
    queryKey: ['aging'],
    queryFn: async () => (await apiGet<Aging[]>('/reports/ar-aging')).data,
  });
  const invoices = useQuery({
    queryKey: ['invoices', 'recent'],
    queryFn: async () => (await apiGet<Invoice[]>('/invoices?limit=6')).data,
  });
  const counter = useQuery({
    queryKey: ['pos', 'daily', 'dashboard'],
    queryFn: async () => (await apiGet<DailyReport>('/pos/reports/daily')).data,
    enabled: can('pos.reports'),
  });
  const shops = useQuery({
    queryKey: ['reports', 'shops'],
    queryFn: async () => (await apiGet<ShopSummary[]>('/reports/shops')).data,
    enabled: can('reports.read'),
  });

  if (dashboard.isLoading) return <Skeleton rows={10} />;
  if (dashboard.isError) return <div className="text-sm text-rose-600">{apiErrorMessage(dashboard.error)}</div>;
  const data = dashboard.data!;

  const cards = [
    { label: 'Total billed', value: inr(data.billed_paise), hint: 'Lifetime invoice value', icon: FileText, tone: 'text-brand-600 bg-brand-50' },
    { label: 'Collected', value: inr(data.collected_paise), hint: `${inr(data.this_month_paise)} this month`, icon: CircleDollarSign, tone: 'text-emerald-600 bg-emerald-50' },
    { label: 'Outstanding', value: inr(data.outstanding_paise), hint: 'Open receivable balance', icon: TrendingUp, tone: 'text-amber-600 bg-amber-50' },
    { label: 'Overdue', value: inr(data.overdue_paise), hint: 'Past due invoices', icon: Clock3, tone: 'text-rose-600 bg-rose-50' },
  ];

  return (
    <div>
      <PageHeader title="Overview" subtitle="A quick read on billing, collections and receivables." actions={<Link to="/invoices"><span className="rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-700">New invoice</span></Link>} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.label} className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-xs font-medium text-muted">{card.label}</div>
                <div className="mt-2 text-2xl font-semibold tracking-tight text-ink">{card.value}</div>
              </div>
              <div className={`grid h-9 w-9 place-items-center rounded-lg ${card.tone}`}><card.icon size={18} /></div>
            </div>
            <div className="mt-3 text-[11px] text-muted">{card.hint}</div>
          </Card>
        ))}
      </div>

      {can('pos.reports') && (
        <Card className="mt-5 border-brand-100 bg-brand-50/40">
          <div className="flex flex-wrap items-center justify-between gap-4 p-5">
            <div className="flex items-center gap-4">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-brand-600 text-white"><ShoppingCart size={19} /></div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-muted">Today at the counter</div>
                <div className="mt-1 flex flex-wrap items-baseline gap-3">
                  <span className="text-2xl font-semibold tracking-tight text-ink">{inr(counter.data?.gross_paise || 0)}</span>
                  <span className="text-xs text-muted">{counter.data?.sales_count || 0} sales · avg {inr(counter.data?.average_bill_paise || 0)}</span>
                  {counter.data?.top_items?.[0] && <span className="text-xs text-muted">Top: {counter.data.top_items[0].description}</span>}
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              {can('pos.sell') && <Link to="/pos"><Button variant="primary" size="sm">Open counter</Button></Link>}
              <Link to="/pos/sales"><Button size="sm">View sales</Button></Link>
            </div>
          </div>
        </Card>
      )}

      {(shops.data?.length ?? 0) > 1 && (
        <Card className="mt-5">
          <CardHeader title="All shops today" subtitle="Counter gross across every shop you manage" />
          <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">
            {shops.data!.map((shop) => (
              <div key={shop.tenant_id} className="rounded-lg border border-line p-4">
                <div className="flex items-center justify-between">
                  <span className="truncate text-sm font-medium text-ink">{shop.tenant_name || shop.slug}</span>
                  <Badge tone="bg-slate-100 text-slate-600 ring-slate-200">{shop.role}</Badge>
                </div>
                <div className="mt-2 text-xl font-semibold text-ink">{inr(shop.today_gross_paise)}</div>
                <div className="text-[11px] text-muted">{shop.today_sales} sales today · {shop.slug}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="mt-5 grid gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Collections over time" subtitle="Captured payments by month" />
          <div className="h-72 p-4">
            {collections.isLoading ? <Skeleton rows={5} /> : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={collections.data || []} margin={{ top: 10, right: 12, left: -8, bottom: 0 }}>
                  <defs>
                    <linearGradient id="collectionFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3538cd" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#3538cd" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef0f3" />
                  <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: '#667085' }} />
                  <YAxis tickFormatter={(v: number) => `₹${Math.round(v / 100000)}L`} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: '#667085' }} />
                  <Tooltip formatter={(value) => inr(Number(value))} labelFormatter={(label) => `Month: ${label}`} contentStyle={{ borderRadius: 10, border: '1px solid #e4e7ec', fontSize: 12 }} />
                  <Area type="monotone" dataKey="amount_paise" stroke="#3538cd" strokeWidth={2} fill="url(#collectionFill)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title="Receivables aging" subtitle="Outstanding by days past due" />
          <div className="space-y-4 p-5">
            {(aging.data || []).map((row) => {
              const width = Math.min(100, Math.round((row.amount_paise / Math.max(1, data.outstanding_paise)) * 100));
              return (
                <div key={row.bucket}>
                  <div className="mb-1 flex justify-between text-xs"><span className="font-medium text-ink">{row.bucket} days</span><span className="text-muted">{inr(row.amount_paise)}</span></div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${row.bucket === '90+' ? 'bg-rose-500' : row.bucket === '61-90' ? 'bg-amber-500' : 'bg-brand-500'}`} style={{ width: `${width}%` }} /></div>
                </div>
              );
            })}
            {!aging.data?.length && <div className="py-8 text-center text-sm text-muted">No outstanding invoices</div>}
          </div>
          <div className="border-t border-line px-5 py-4 text-xs text-muted">Tip: follow up on the oldest bucket first.</div>
        </Card>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Recent invoices" action={<Link to="/invoices" className="text-xs font-medium text-brand-600 hover:underline">View all →</Link>} />
          {invoices.isLoading ? <Skeleton rows={5} /> : (
            <div className="divide-y divide-line">
              {(invoices.data || []).slice(0, 6).map((invoice) => (
                <Link key={invoice.id} to={`/invoices/${invoice.id}`} className="flex items-center gap-4 px-5 py-3 hover:bg-slate-50/70">
                  <div className={`grid h-8 w-8 place-items-center rounded-lg text-xs font-semibold ${invoice.status === 'PAID' ? 'bg-emerald-50 text-emerald-700' : 'bg-brand-50 text-brand-700'}`}>{invoice.number?.slice(-2) || 'D'}</div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-ink">{invoice.number || 'Draft invoice'}</div>
                    <div className="text-[11px] text-muted">Issued {shortDate(invoice.issue_date)} · Due {shortDate(invoice.due_date)}</div>
                  </div>
                  <Badge tone={statusTone(invoice.status)}>{titleCase(invoice.status)}</Badge>
                  <div className="hidden w-28 text-right text-sm font-medium text-ink sm:block">{inr(invoice.balance_paise)}</div>
                </Link>
              ))}
              {!invoices.data?.length && <div className="py-10 text-center text-sm text-muted">No invoices yet.</div>}
            </div>
          )}
        </Card>
        <Card>
          <CardHeader title="Invoice pipeline" subtitle="By current status" />
          <div className="space-y-3 p-5">
            {Object.entries(data.invoice_counts || {}).map(([status, count]) => (
              <div key={status} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2"><Badge tone={statusTone(status)}>{titleCase(status)}</Badge></div>
                <span className="font-semibold text-ink">{count}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-3 border-t border-line px-5 py-4 text-[11px] text-muted">
            <span className="flex items-center gap-1 text-emerald-600"><ArrowUpRight size={13} /> On track</span>
            <span className="flex items-center gap-1 text-rose-600"><ArrowDownRight size={13} /> Needs attention</span>
          </div>
        </Card>
      </div>
    </div>
  );
}
