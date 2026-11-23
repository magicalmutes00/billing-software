import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, RotateCcw, Search } from 'lucide-react';
import { apiErrorMessage, apiGet, apiSend } from '../lib/api';
import { inr, shortDate, statusTone, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, DataTable, Field, Input, Modal, PageHeader, Select, Skeleton, useToast, type Column } from '../components/ui';
import { CustomerSelect } from '../components/CustomerSelect';
import type { Allocation, Invoice, Payment } from '../types';

type Draft = { customer_id: string; amount: string; method: string; reference_no: string; notes: string; allocations: Allocation[] };
const blank = (): Draft => ({ customer_id: '', amount: '', method: 'BANK', reference_no: '', notes: '', allocations: [] });

export default function Payments() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank());
  const [error, setError] = useState('');

  const payments = useQuery({
    queryKey: ['payments', search],
    queryFn: async () => (await apiGet<Payment[]>(`/payments?limit=100&customer_id=${search}`)).data,
  });

  const invoices = useQuery({
    queryKey: ['invoices', 'open', draft.customer_id],
    enabled: !!draft.customer_id,
    queryFn: async () => (await apiGet<Invoice[]>(`/invoices?customer_id=${draft.customer_id}&limit=100`)).data,
  });

  const openInvoices = (invoices.data || []).filter((invoice) => invoice.balance_paise > 0 && invoice.status !== 'CANCELLED');

  const save = useMutation({
    mutationFn: async (value: Draft) => apiSend<Payment>('post', '/payments', {
      customer_id: value.customer_id,
      amount_paise: Math.round(Number(value.amount) * 100),
      method: value.method,
      reference_no: value.reference_no || null,
      notes: value.notes || null,
      allocations: value.allocations.filter((a) => a.amount_paise > 0).map((a) => ({
        invoice_id: a.invoice_id, amount_paise: a.amount_paise,
      })),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payments'] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify('Payment recorded');
      setOpen(false);
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const refund = useMutation({
    mutationFn: async (payment: Payment) => apiSend('post', `/payments/${payment.id}/refund`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payments'] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify('Payment refunded');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  function addAllocation(invoiceId: string) {
    if (!invoiceId || draft.allocations.some((a) => a.invoice_id === invoiceId)) return;
    const invoice = openInvoices.find((i) => i.id === invoiceId);
    setDraft({ ...draft, allocations: [...draft.allocations, { invoice_id: invoiceId, amount_paise: invoice?.balance_paise || 0 }] });
  }

  const columns: Column<Payment>[] = [
    { key: 'number', header: 'Receipt', render: (row) => <div><div className="font-medium text-ink">{row.number || 'Pending'}</div><div className="text-[11px] text-muted">{shortDate(row.created_at)}</div></div> },
    { key: 'method', header: 'Method', render: (row) => <div><div className="text-xs font-medium text-ink">{titleCase(row.method)}</div><div className="text-[11px] text-muted">{row.provider || row.reference_no || '—'}</div></div> },
    { key: 'paid', header: 'Paid on', render: (row) => <span className="text-xs text-muted">{shortDate(row.paid_at)}</span> },
    { key: 'amount', header: 'Amount', render: (row) => <span className="font-medium text-ink">{inr(row.amount_paise)}</span>, className: 'text-right' },
    { key: 'allocated', header: 'Allocated', render: (row) => <span className="text-xs text-muted">{inr(row.allocated_paise)}</span>, className: 'text-right' },
    { key: 'status', header: 'Status', render: (row) => <Badge tone={statusTone(row.status)}>{titleCase(row.status)}</Badge> },
    {
      key: 'actions', header: '', className: 'text-right',
      render: (row) => row.status === 'CAPTURED' ? <button onClick={(e) => { e.stopPropagation(); if (confirm(`Refund ${inr(row.amount_paise)}?`)) refund.mutate(row); }} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted hover:bg-rose-50 hover:text-rose-600"><RotateCcw size={13} /> Refund</button> : null,
    },
  ];

  return (
    <div>
      <PageHeader title="Payments" subtitle="Record receipts, allocate them to invoices and issue refunds." actions={<Button variant="primary" onClick={() => { setDraft(blank()); setError(''); setOpen(true); }}><Plus size={16} /> Record payment</Button>} />
      <Card>
        <CardHeader title={`${payments.data?.length || 0} payments`} action={<div className="relative w-64"><Search size={15} className="absolute left-3 top-2.5 text-muted" /><Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter by customer ID…" className="pl-9" /></div>} />
        {payments.isLoading ? <Skeleton rows={8} /> : <DataTable columns={columns} rows={payments.data || []} empty="No payments recorded yet." />}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="Record a payment" width="max-w-2xl">
        <form onSubmit={(e) => { e.preventDefault(); setError(''); save.mutate(draft); }} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Customer" className="sm:col-span-2"><CustomerSelect value={draft.customer_id} onChange={(v) => setDraft({ ...draft, customer_id: v, allocations: [] })} /></Field>
            <Field label="Amount (₹)"><Input type="number" step="0.01" min="0.01" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} required /></Field>
            <Field label="Method"><Select value={draft.method} onChange={(e) => setDraft({ ...draft, method: e.target.value })}><option value="BANK">Bank transfer</option><option value="UPI">UPI</option><option value="CASH">Cash</option><option value="CHEQUE">Cheque</option><option value="GATEWAY">Gateway</option><option value="OTHER">Other</option></Select></Field>
            <Field label="Reference no."><Input value={draft.reference_no} onChange={(e) => setDraft({ ...draft, reference_no: e.target.value })} placeholder="UTR / cheque no." /></Field>
            <Field label="Notes"><Input value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} /></Field>
          </div>
          <div className="border-t border-line pt-4">
            <div className="mb-2 flex items-center justify-between"><span className="text-xs font-semibold uppercase tracking-wide text-muted">Allocate to invoices</span><span className="text-xs text-muted">Amount: {inr(Math.round(Number(draft.amount || 0) * 100))}</span></div>
            {!draft.customer_id && <p className="text-xs text-muted">Select a customer to see open invoices.</p>}
            {draft.customer_id && openInvoices.length === 0 && <p className="text-xs text-muted">This customer has no open invoices. You can record an unallocated payment.</p>}
            <div className="space-y-2">
              {draft.allocations.map((allocation, index) => {
                const invoice = openInvoices.find((i) => i.id === allocation.invoice_id);
                return (
                  <div key={allocation.invoice_id} className="flex items-center gap-2 rounded-lg border border-line p-2">
                    <div className="flex-1 text-xs"><div className="font-medium text-ink">{invoice?.number || 'Invoice'}</div><div className="text-muted">Balance {inr(invoice?.balance_paise || 0)}</div></div>
                    <Input type="number" step="0.01" min="0" className="w-32 text-right text-xs" value={(allocation.amount_paise / 100).toFixed(2)} onChange={(e) => {
                      const next = [...draft.allocations];
                      next[index] = { ...allocation, amount_paise: Math.round(Number(e.target.value) * 100) };
                      setDraft({ ...draft, allocations: next });
                    }} />
                    <button type="button" onClick={() => setDraft({ ...draft, allocations: draft.allocations.filter((_, i) => i !== index) })} className="rounded-md p-1 text-muted hover:text-rose-600">×</button>
                  </div>
                );
              })}
            </div>
            {draft.customer_id && openInvoices.length > 0 && (
              <Select className="mt-2 text-xs" value="" onChange={(e) => addAllocation(e.target.value)}>
                <option value="">+ Add an open invoice…</option>
                {openInvoices.filter((i) => !draft.allocations.some((a) => a.invoice_id === i.id)).map((invoice) => (
                  <option key={invoice.id} value={invoice.id}>{invoice.number || 'Draft'} · {inr(invoice.balance_paise)}</option>
                ))}
              </Select>
            )}
          </div>
          {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Record payment</Button></div>
        </form>
      </Modal>
    </div>
  );
}
