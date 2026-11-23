import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Eye, Printer, Share2, Undo2, XCircle } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { apiErrorMessage, apiGet, apiSend, printAuthenticatedHtml } from '../lib/api';
import { inr, shortDate, statusTone, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, DataTable, Field, Input, Modal, PageHeader, Skeleton, useToast, type Column } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import type { DailyReport, RangeReport } from '../types';

type SaleRow = {
  id: string;
  number?: string | null;
  status: string;
  issue_date: string;
  created_at?: string | null;
  total_paise: number;
  paid_paise: number;
  balance_paise: number;
  pos_meta: {
    method?: string;
    tendered_paise?: number;
    change_paise?: number;
    reference_no?: string | null;
    cashier?: string | null;
    voided?: boolean;
  } | null;
  items: Array<{ description: string; qty: number; total_paise: number }>;
};

export default function PosSales() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { can, user } = useAuth();
  const navigate = useNavigate();
  const { id } = useParams();
  const [search, setSearch] = useState('');
  const [payment, setPayment] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const sales = useQuery({
    queryKey: ['pos', 'sales', search, payment, dateFrom, dateTo],
    queryFn: async () => (await apiGet<SaleRow[]>('/pos/sales', {
      search: search || undefined,
      payment: payment || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      limit: 100,
    })).data,
  });

  const sale = useQuery({
    queryKey: ['pos', 'sale', id],
    queryFn: async () => (await apiGet<SaleRow>(`/pos/sales/${id!}`)).data,
    enabled: !!id,
  });

  const report = useQuery({
    queryKey: ['pos', 'daily', dateFrom || new Date().toISOString().slice(0, 10)],
    queryFn: async () => (await apiGet<DailyReport>('/pos/reports/daily', {
      day: dateFrom || new Date().toISOString().slice(0, 10),
    })).data,
  });

  const voidSale = useMutation({
    mutationFn: async (saleId: string) => (await apiSend('post', `/pos/sales/${saleId}/void`, { reason: 'Voided from counter sales' })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'sales'] });
      queryClient.invalidateQueries({ queryKey: ['pos', 'daily'] });
      notify('Sale voided');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  // ---------- Partial refund ----------
  const [refundId, setRefundId] = useState<string | null>(null);
  const [refundAmount, setRefundAmount] = useState('');
  const [refundReason, setRefundReason] = useState('');
  const refundSale = useMutation({
    mutationFn: async () => (await apiSend('post', `/pos/sales/${refundId}/refund`, {
      amount_paise: Math.round(Number(refundAmount || 0) * 100),
      reason: refundReason || 'Refund at counter',
    })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'sales'] });
      queryClient.invalidateQueries({ queryKey: ['pos', 'sale', refundId] });
      queryClient.invalidateQueries({ queryKey: ['pos', 'daily'] });
      setRefundId(null); setRefundAmount(''); setRefundReason('');
      notify('Refund recorded', 'success');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  const shareReceipt = useMutation({
    mutationFn: async (saleId: string) => (await apiSend<{ token: string }>('post', `/pos/sales/${saleId}/share-token`)).data,
    onSuccess: ({ token }) => {
      const url = `${window.location.origin}/api/v1/public/receipt/${token}`;
      window.open(`https://wa.me/?text=${encodeURIComponent(`Receipt: ${url}`)}`, '_blank');
      void navigator.clipboard?.writeText(url).catch(() => {});
      notify('Receipt link copied', 'success');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  // ---------- Range / item / cashier reports ----------
  const today = new Date().toISOString().slice(0, 10);
  const rangeFrom = dateFrom || today;
  const rangeTo = dateTo || rangeFrom;
  const rangeReport = useQuery({
    queryKey: ['pos', 'range', rangeFrom, rangeTo],
    queryFn: async () => (await apiGet<RangeReport>('/pos/reports/range', { date_from: rangeFrom, date_to: rangeTo })).data,
  });
  const itemReport = useQuery({
    queryKey: ['pos', 'items', rangeFrom, rangeTo],
    queryFn: async () => (await apiGet<Array<{ description: string; qty: number; amount_paise: number }>>('/pos/reports/items', { date_from: rangeFrom, date_to: rangeTo })).data,
  });
  const cashierReport = useQuery({
    queryKey: ['pos', 'cashiers', rangeFrom, rangeTo],
    queryFn: async () => (await apiGet<Array<{ cashier: string; sales: number; amount_paise: number }>>('/pos/reports/cashiers', { date_from: rangeFrom, date_to: rangeTo })).data,
  });

  const gross = sales.data?.reduce((sum, row) => sum + row.total_paise, 0) || 0;
  const count = sales.data?.length || 0;

  const columns: Column<SaleRow>[] = [
    {
      key: 'number',
      header: 'Bill',
      render: (row) => <div><div className="font-medium text-ink">{row.number || '—'}</div><div className="text-[11px] text-muted">{shortDate(row.created_at || row.issue_date)}</div></div>,
    },
    {
      key: 'items',
      header: 'Items',
      render: (row) => row.items.map((item, i) => <div key={i} className="text-xs text-muted truncate max-w-[130px]">{item.description} ×{item.qty}</div>),
    },
    {
      key: 'payment',
      header: 'Payment',
      render: (row) => <span className="text-xs font-medium text-ink">{row.pos_meta?.method || '—'}</span>,
    },
    {
      key: 'total',
      header: 'Total',
      render: (row) => <span className="font-medium text-ink text-right">{inr(row.total_paise)}</span>,
      className: 'text-right',
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <Badge tone={row.status === 'CANCELLED' ? 'bg-slate-100 text-slate-600 ring-slate-200' : statusTone(row.status)}>{titleCase(row.status)}</Badge>,
    },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (row) => (
        <div className="flex justify-end gap-1">
          <button onClick={(e) => { e.stopPropagation(); navigate(`/pos/sales/${row.id}`); }} className="rounded-md p-1.5 text-muted hover:bg-slate-100" title="View"><Eye size={15} /></button>
          <button onClick={(e) => { e.stopPropagation(); printAuthenticatedHtml(`/api/v1/pos/sales/${row.id}/receipt`); }} className="rounded-md p-1.5 text-muted hover:bg-brand-50 hover:text-brand-600" title="Print receipt"><Printer size={15} /></button>
          {can('pos.void') && row.status !== 'CANCELLED' && <button onClick={(e) => { e.stopPropagation(); if (confirm('Void this sale and refund the payment?')) voidSale.mutate(row.id); }} className="rounded-md p-1.5 text-muted hover:bg-rose-50 hover:text-rose-600" title="Void"><XCircle size={15} /></button>}
        </div>
      ),
    },
  ];

  if (id) {
    return (
      <div>
        <PageHeader title="Sale detail" subtitle="Counter sale receipt and actions" actions={<Link to="/pos/sales"><Button size="sm"><ArrowLeft size={15} /> Back to sales list</Button></Link>} />
        {sale.isLoading ? <Skeleton rows={6} /> : (
          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title="Receipt" />
              <div className="p-5 max-w-xs border border-line rounded-xl bg-white/50">
                {!sale.data ? null : (
                  <>
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted">{user?.tenant_name || 'Your shop'}</div>
                    <div className="mt-2 text-sm font-medium text-ink">{sale.data.number || '—'}</div>
                    <hr className="my-3 border-dashed" />
                    <div className="space-y-2">
                      {sale.data.items.map((item, i) => (
                        <div key={i} className="flex justify-between text-sm">
                          <span className="text-ink">{item.description} <span className="ml-2 text-xs font-normal text-muted">×{item.qty}</span></span>
                          <span className="text-right">{inr(item.total_paise)}</span>
                        </div>
                      ))}
                    </div>
                    <hr className="my-3 border-dashed" />
                    <div className="flex justify-between text-sm font-medium text-ink">
                      <span>Total</span>
                      <span>{inr(sale.data.total_paise)}</span>
                    </div>
                    <div className="flex justify-between text-xs text-muted mt-1">
                      <span>Paid by</span>
                      <span>{sale.data.pos_meta?.method || '—'}</span>
                    </div>
                    {sale.data.pos_meta?.tendered_paise != null && (
                      <div className="flex justify-between text-xs text-muted">
                        <span>Tendered</span>
                        <span>{inr(sale.data.pos_meta.tendered_paise)}</span>
                      </div>
                    )}
                    {sale.data.pos_meta?.change_paise != null && sale.data.pos_meta.change_paise > 0 && (
                      <div className="flex justify-between text-xs text-muted">
                        <span>Change</span>
                        <span>{inr(sale.data.pos_meta.change_paise)}</span>
                      </div>
                    )}
                    <hr className="my-3 border-dashed" />
                    <div className="text-[11px] text-center text-muted">Thank you! Visit again.</div>
                  </>
                )}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button onClick={() => { printAuthenticatedHtml(`/api/v1/pos/sales/${id}/receipt`); }}><Printer size={15} /> Print receipt</Button>
                <Button onClick={() => shareReceipt.mutate(id)} loading={shareReceipt.isPending}><Share2 size={15} /> Share</Button>
                {can('pos.void') && sale.data?.status !== 'CANCELLED' && <Button onClick={() => { setRefundId(id); setRefundAmount(''); setRefundReason(''); }}><Undo2 size={15} /> Refund</Button>}
                {can('pos.void') && sale.data?.status !== 'CANCELLED' && <Button variant="danger" onClick={() => { if (confirm('Void this sale and refund the payment?')) voidSale.mutate(id); }}><XCircle size={15} /> Void sale</Button>}
              </div>
            </Card>
            <Card>
              <CardHeader title="Summary" />
              <div className="p-5 space-y-3">
                <div className="flex justify-between text-sm"><span className="text-muted">Bill</span><span className="font-medium">{sale.data?.number || '—'}</span></div>
                <div className="flex justify-between text-sm"><span className="text-muted">Status</span><span className="font-medium">{titleCase(sale.data?.status || '—')}</span></div>
                <div className="flex justify-between border-t border-line pt-2 text-sm font-semibold"><span>Total</span><span>{inr(sale.data?.total_paise || 0)}</span></div>
              </div>
            </Card>
          </div>
        )}
        <Modal open={!!refundId} onClose={() => setRefundId(null)} title="Refund sale" width="max-w-sm">
          <form onSubmit={(e) => { e.preventDefault(); refundSale.mutate(); }} className="space-y-4">
            <Field label="Refund amount (₹)"><Input type="number" step="0.01" min="0.01" value={refundAmount} onChange={(e) => setRefundAmount(e.target.value)} required autoFocus /></Field>
            <Field label="Reason"><Input value={refundReason} onChange={(e) => setRefundReason(e.target.value)} placeholder="e.g. wrong item" /></Field>
            <div className="flex justify-end gap-2 border-t border-line pt-4">
              <Button type="button" onClick={() => setRefundId(null)}>Cancel</Button>
              <Button type="submit" variant="primary" loading={refundSale.isPending} disabled={refundSale.isPending || Number(refundAmount || 0) <= 0}>Record refund</Button>
            </div>
          </form>
        </Modal>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Counter sales"
        subtitle="Search, view, reprint and void counter sales."
        actions={<>
          <div className="flex gap-2">
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search bill number…" className="w-64 pl-9" />
            <select value={payment} onChange={(e) => setPayment(e.target.value)} className="rounded-lg border border-line bg-white px-3 py-2 text-sm">
              <option value="">All payment modes</option>
              <option value="CASH">Cash</option>
              <option value="UPI">UPI</option>
              <option value="CARD">Card</option>
            </select>
            <Button variant="primary" onClick={() => { setDateFrom(''); setDateTo(''); }}><ArrowLeft size={14} /> Reset</Button>
          </div>
          <div className="flex gap-2">
            <Field label="From"><Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></Field>
            <Field label="To"><Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></Field>
          </div>
        </>} />
      <div className="grid gap-5 lg:grid-cols-4">
        <Card className="p-5">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Sales</div>
          <div className="mt-2 text-2xl font-semibold tracking-tight text-ink">{count}</div>
        </Card>
        <Card className="p-5">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Gross collected</div>
          <div className="mt-2 text-2xl font-semibold tracking-tight text-ink">{inr(gross)}</div>
        </Card>
        <Card className="p-5">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Average bill</div>
          <div className="mt-2 text-2xl font-semibold tracking-tight text-ink">{inr(count ? Math.round(gross / count) : 0)}</div>
        </Card>
        <Card className="p-5">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Top item</div>
          <div className="mt-2 text-2xl font-semibold tracking-tight text-ink">{report.data?.top_items?.[0]?.description || '—'}</div>
          <div className="text-[11px] text-muted">{report.data?.top_items?.[0]?.amount_paise != null ? inr(report.data.top_items[0].amount_paise) : ''}</div>
        </Card>
      </div>
      {sales.isLoading ? <Skeleton rows={8} /> : (
        <Card>
          <CardHeader
            title={`${count} sales`}
            action={
              <Button size="sm" onClick={() => {
                const rows = (sales.data || []).map((row) => [row.number, shortDate(row.created_at || row.issue_date), row.pos_meta?.method, row.total_paise / 100, row.status]);
                const csv = [['Bill', 'Date', 'Payment', 'Total (₹)', 'Status'], ...rows].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
                const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
                const link = document.createElement('a');
                link.href = url;
                link.download = 'counter-sales.csv';
                link.click();
                URL.revokeObjectURL(url);
              }}>Export CSV</Button>
            }
          />
          {sales.data?.length === 0 ? <div className="py-12 text-center text-sm text-muted">No counter sales found.</div> : (
            <DataTable columns={columns} rows={sales.data || []} empty="No counter sales found." onRowClick={(row) => navigate(`/pos/sales/${row.id}`)} />
          )}
        </Card>
      )}

      {/* Range / item / cashier reports */}
      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Card className="p-5">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Range gross ({rangeFrom} → {rangeTo})</div>
          <div className="mt-2 text-2xl font-semibold text-ink">{inr(rangeReport.data?.gross_paise || 0)}</div>
          <div className="mt-1 text-[11px] text-muted">
            {rangeReport.data?.sales_count || 0} sales · vs previous {inr(rangeReport.data?.previous?.gross_paise || 0)}
            {rangeReport.data ? ` (${rangeReport.data.gross_delta_paise >= 0 ? '+' : ''}{inr(rangeReport.data.gross_delta_paise)})` : ''}
          </div>
        </Card>
        <Card className="p-5">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Top items</div>
          <div className="space-y-1">
            {(itemReport.data || []).slice(0, 5).map((item) => (
              <div key={item.description} className="flex justify-between text-xs"><span className="truncate text-ink">{item.description}</span><span className="text-muted">{inr(item.amount_paise)}</span></div>
            ))}
            {(itemReport.data?.length ?? 0) === 0 && <div className="text-xs text-muted">No items in range.</div>}
          </div>
        </Card>
        <Card className="p-5">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">By cashier</div>
          <div className="space-y-1">
            {(cashierReport.data || []).slice(0, 5).map((c) => (
              <div key={c.cashier} className="flex justify-between text-xs"><span className="truncate text-ink">{c.cashier}</span><span className="text-muted">{c.sales} · {inr(c.amount_paise)}</span></div>
            ))}
            {(cashierReport.data?.length ?? 0) === 0 && <div className="text-xs text-muted">No sales in range.</div>}
          </div>
        </Card>
      </div>

      <Modal open={!!refundId} onClose={() => setRefundId(null)} title="Refund sale" width="max-w-sm">
        <form onSubmit={(e) => { e.preventDefault(); refundSale.mutate(); }} className="space-y-4">
          <Field label="Refund amount (₹)"><Input type="number" step="0.01" min="0.01" value={refundAmount} onChange={(e) => setRefundAmount(e.target.value)} required autoFocus /></Field>
          <Field label="Reason"><Input value={refundReason} onChange={(e) => setRefundReason(e.target.value)} placeholder="e.g. wrong item" /></Field>
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <Button type="button" onClick={() => setRefundId(null)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={refundSale.isPending} disabled={refundSale.isPending || Number(refundAmount || 0) <= 0}>Record refund</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
