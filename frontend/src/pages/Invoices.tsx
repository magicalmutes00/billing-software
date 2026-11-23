import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Eye, Plus, Printer, Search, Send, XCircle } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { apiErrorMessage, apiGet, apiSend, printAuthenticatedHtml } from '../lib/api';
import { inr, shortDate, statusTone, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, DataTable, Field, Input, Modal, PageHeader, Skeleton, Textarea, useToast, type Column } from '../components/ui';
import { CustomerSelect } from '../components/CustomerSelect';
import { ItemEditor, newItem } from '../components/ItemEditor';
import type { Invoice, Item, Payment } from '../types';

type Draft = { customer_id: string; issue_date: string; due_date: string; notes: string; terms: string; tax_mode: string; items: Item[] };
const today = () => new Date().toISOString().slice(0, 10);
const blank = (): Draft => ({ customer_id: '', issue_date: today(), due_date: '', notes: '', terms: '', tax_mode: 'EXCLUSIVE', items: [newItem()] });

function InvoiceDetail({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [payOpen, setPayOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [reference, setReference] = useState('');

  const invoice = useQuery({
    queryKey: ['invoice', id],
    queryFn: async () => (await apiGet<Invoice>(`/invoices/${id}`)).data,
  });

  const record = useMutation({
    mutationFn: async () => apiSend<Payment>('post', '/payments', {
      customer_id: invoice.data!.customer_id,
      amount_paise: Math.round(Number(amount) * 100),
      method: 'BANK',
      reference_no: reference || null,
      allocations: [{ invoice_id: id, amount_paise: Math.round(Number(amount) * 100) }],
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoice', id] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify('Payment recorded');
      setPayOpen(false);
      setAmount('');
      setReference('');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  if (invoice.isLoading) return <Skeleton rows={10} />;
  if (invoice.isError || !invoice.data) return <div className="text-sm text-rose-600">{apiErrorMessage(invoice.error)}</div>;
  const value = invoice.data;

  return (
    <div>
      <PageHeader
        title={value.number || 'Draft invoice'}
        subtitle={`Issued ${shortDate(value.issue_date)} · Due ${shortDate(value.due_date)}`}
        actions={<>
          <Link to="/invoices"><Button size="sm"><ArrowLeft size={15} /> Back</Button></Link>
          {value.channel === 'POS' ? (
            <Button size="sm" onClick={() => { void printAuthenticatedHtml(`/api/v1/pos/sales/${value.id}/receipt`); }}><Printer size={15} /> Print receipt</Button>
          ) : (
            <Button size="sm" onClick={() => { void printAuthenticatedHtml(`/api/v1/invoices/${value.id}/pdf`); }}><Printer size={15} /> Print / PDF</Button>
          )}
          {value.channel !== 'POS' && value.balance_paise > 0 && value.status !== 'CANCELLED' && <Button size="sm" variant="primary" onClick={() => { setAmount((value.balance_paise / 100).toFixed(2)); setPayOpen(true); }}><Plus size={15} /> Record payment</Button>}
        </>}
      />
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Line items" subtitle={`${value.items.length} items · ${value.tax_mode.toLowerCase()} GST`} />
          <div className="overflow-x-auto"><table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-[11px] uppercase text-muted"><tr><th className="px-5 py-3 font-semibold">Description</th><th className="px-3 py-3 text-right font-semibold">Qty</th><th className="px-3 py-3 text-right font-semibold">Rate</th><th className="px-3 py-3 text-right font-semibold">Tax</th><th className="px-5 py-3 text-right font-semibold">Amount</th></tr></thead>
            <tbody className="divide-y divide-line">{value.items.map((item) => <tr key={item.id}><td className="px-5 py-3"><div className="font-medium text-ink">{item.description}</div>{item.hsn_sac && <div className="text-[11px] text-muted">HSN {item.hsn_sac}</div>}</td><td className="px-3 py-3 text-right">{item.qty}</td><td className="px-3 py-3 text-right">{inr(item.unit_price_paise)}</td><td className="px-3 py-3 text-right">{inr(item.tax_paise)}</td><td className="px-5 py-3 text-right font-medium">{inr(item.total_paise)}</td></tr>)}</tbody>
          </table></div>
          <div className="ml-auto w-full max-w-xs space-y-1 p-5 text-xs">
            <div className="flex justify-between"><span className="text-muted">Subtotal</span><span>{inr(value.subtotal_paise)}</span></div>
            <div className="flex justify-between"><span className="text-muted">Discount</span><span>{inr(value.discount_paise)}</span></div>
            <div className="flex justify-between"><span className="text-muted">GST</span><span>{inr(value.tax_paise)}</span></div>
            <div className="flex justify-between"><span className="text-muted">Round off</span><span>{inr(value.round_off_paise)}</span></div>
            <div className="flex justify-between border-t border-line pt-2 text-sm font-semibold"><span>Total</span><span>{inr(value.total_paise)}</span></div>
          </div>
        </Card>
        <div className="space-y-5">
          <Card className="p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Status</div>
            <div className="mt-2"><Badge tone={statusTone(value.status)}>{titleCase(value.status)}</Badge></div>
            <div className="mt-5 space-y-3 text-xs">
              <div className="flex justify-between"><span className="text-muted">Total</span><span className="font-medium">{inr(value.total_paise)}</span></div>
              <div className="flex justify-between"><span className="text-muted">Paid</span><span className="font-medium text-emerald-600">{inr(value.paid_paise)}</span></div>
              <div className="flex justify-between"><span className="text-muted">Credited</span><span className="font-medium">{inr(value.credited_paise)}</span></div>
              <div className="flex justify-between border-t border-line pt-3 text-sm font-semibold"><span>Balance</span><span>{inr(value.balance_paise)}</span></div>
            </div>
            {value.notes && <div className="mt-5 border-t border-line pt-4"><div className="text-xs font-semibold text-ink">Notes</div><p className="mt-1 text-xs text-muted">{value.notes}</p></div>}
          </Card>
          <Card className="p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Meta</div>
            <div className="mt-3 space-y-2 text-xs text-muted"><div>Channel: <b className="text-ink">{value.channel === 'POS' ? 'Counter sale' : 'Tax invoice'}</b></div><div>Place of supply: <b className="text-ink">{value.place_of_supply || '—'}</b></div><div>Currency: <b className="text-ink">{value.currency}</b></div><div>Version: <b className="text-ink">{value.version}</b></div><div>Created: <b className="text-ink">{shortDate(value.created_at)}</b></div>{value.channel === 'POS' && <div className="rounded bg-amber-50 p-2 text-amber-700">Counter receipts are simple receipts, not GST tax invoices.</div>}</div>
          </Card>
        </div>
      </div>
      <Modal open={payOpen} onClose={() => setPayOpen(false)} title="Record payment">
        <form onSubmit={(e) => { e.preventDefault(); record.mutate(); }} className="space-y-4">
          <Field label="Amount (₹)"><Input type="number" step="0.01" min="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required /></Field>
          <Field label="Reference no."><Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="NEFT / UTR / Cheque no." /></Field>
          <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setPayOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={record.isPending}>Record payment</Button></div>
        </form>
      </Modal>
    </div>
  );
}

export default function Invoices() {
  const { id } = useParams();
  if (id) return <InvoiceDetail id={id} />;
  return <InvoiceList />;
}

function InvoiceList() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [channel, setChannel] = useState('');
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank());
  const [error, setError] = useState('');

  const invoices = useQuery({
    queryKey: ['invoices', search, status, channel],
    queryFn: async () => (await apiGet<Invoice[]>(`/invoices?limit=100&search=${encodeURIComponent(search)}&status=${status}&channel=${channel}`)).data,
  });

  const create = useMutation({
    mutationFn: async (value: Draft) => apiSend<Invoice>('post', '/invoices', {
      customer_id: value.customer_id,
      issue_date: value.issue_date,
      due_date: value.due_date || null,
      notes: value.notes || null,
      terms: value.terms || null,
      tax_mode: value.tax_mode,
      items: value.items.map(({ description, hsn_sac, qty, unit_price_paise, discount_paise, tax_rate_pct }) => ({
        description, hsn_sac: hsn_sac || null, qty, unit_price_paise, discount_paise, tax_rate_pct,
      })),
    }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify('Invoice created as draft');
      setOpen(false);
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const action = useMutation({
    mutationFn: async ({ id, verb }: { id: string; verb: string }) => apiSend('post', `/invoices/${id}/${verb}`),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify(`Invoice ${variables.verb === 'send' ? 'sent and numbered' : 'cancelled'}`);
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  const columns: Column<Invoice>[] = [
    { key: 'number', header: 'Invoice', render: (row) => <div><div className="flex items-center gap-1.5"><span className="font-medium text-ink">{row.number || 'Draft'}</span>{row.channel === 'POS' && <Badge tone="bg-amber-50 text-amber-700 ring-amber-200">Counter</Badge>}</div><div className="text-[11px] text-muted">{shortDate(row.issue_date)}</div></div> },
    { key: 'due', header: 'Due date', render: (row) => <span className="text-xs text-muted">{shortDate(row.due_date)}</span> },
    { key: 'total', header: 'Total', render: (row) => <span className="font-medium text-ink">{inr(row.total_paise)}</span>, className: 'text-right' },
    { key: 'balance', header: 'Balance', render: (row) => <span className={row.balance_paise > 0 ? 'font-medium text-amber-600' : 'font-medium text-emerald-600'}>{inr(row.balance_paise)}</span>, className: 'text-right' },
    { key: 'status', header: 'Status', render: (row) => <Badge tone={statusTone(row.status)}>{titleCase(row.status)}</Badge> },
    {
      key: 'actions', header: '', className: 'text-right',
      render: (row) => (
        <div className="flex justify-end gap-1">
          <Link to={`/invoices/${row.id}`} onClick={(e) => e.stopPropagation()} className="rounded-md p-1.5 text-muted hover:bg-slate-100" title="View"><Eye size={15} /></Link>
          {row.status === 'DRAFT' && <button onClick={(e) => { e.stopPropagation(); action.mutate({ id: row.id, verb: 'send' }); }} className="rounded-md p-1.5 text-muted hover:bg-brand-50 hover:text-brand-600" title="Send & number"><Send size={15} /></button>}
          {!['CANCELLED', 'PAID'].includes(row.status) && <button onClick={(e) => { e.stopPropagation(); if (confirm('Cancel this invoice?')) action.mutate({ id: row.id, verb: 'cancel' }); }} className="rounded-md p-1.5 text-muted hover:bg-rose-50 hover:text-rose-600" title="Cancel"><XCircle size={15} /></button>}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Invoices" subtitle="Create, send and track tax invoices and their balances." actions={<Button variant="primary" onClick={() => { setDraft(blank()); setError(''); setOpen(true); }}><Plus size={16} /> New invoice</Button>} />
      <Card>
        <CardHeader title={`${invoices.data?.length || 0} invoices`} action={<div className="flex gap-2"><div className="relative w-64"><Search size={15} className="absolute left-3 top-2.5 text-muted" /><Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by number…" className="pl-9" /></div><select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="">All statuses</option>{['DRAFT', 'SENT', 'PARTIALLY_PAID', 'PAID', 'OVERDUE', 'CANCELLED'].map((s) => <option key={s}>{s}</option>)}</select><select value={channel} onChange={(e) => setChannel(e.target.value)} className="rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="">All channels</option><option value="INVOICE">Invoice</option><option value="POS">Counter</option></select></div>} />
        {invoices.isLoading ? <Skeleton rows={8} /> : <DataTable columns={columns} rows={invoices.data || []} empty="No invoices yet." onRowClick={(row) => window.location.assign(`/invoices/${row.id}`)} />}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="New invoice" width="max-w-4xl">
        <form onSubmit={(e) => { e.preventDefault(); setError(''); create.mutate(draft); }} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="Customer" className="sm:col-span-2"><CustomerSelect value={draft.customer_id} onChange={(v) => setDraft({ ...draft, customer_id: v })} /></Field>
            <Field label="Issue date"><Input type="date" value={draft.issue_date} onChange={(e) => setDraft({ ...draft, issue_date: e.target.value })} /></Field>
            <Field label="Due date" hint="Blank uses customer terms"><Input type="date" value={draft.due_date} onChange={(e) => setDraft({ ...draft, due_date: e.target.value })} /></Field>
            <Field label="Tax mode"><select value={draft.tax_mode} onChange={(e) => setDraft({ ...draft, tax_mode: e.target.value })} className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="EXCLUSIVE">Exclusive (add GST)</option><option value="INCLUSIVE">Inclusive (GST included)</option></select></Field>
          </div>
          <div><div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Line items</div><ItemEditor items={draft.items} onChange={(items) => setDraft({ ...draft, items })} /></div>
          <div className="grid gap-4 sm:grid-cols-2"><Field label="Notes"><Textarea value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} /></Field><Field label="Terms"><Textarea value={draft.terms} onChange={(e) => setDraft({ ...draft, terms: e.target.value })} /></Field></div>
          {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={create.isPending}>Create draft invoice</Button></div>
        </form>
      </Modal>
    </div>
  );
}
