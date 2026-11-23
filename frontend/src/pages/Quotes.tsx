import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Eye, FilePlus2, Plus, Search, Send, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiErrorMessage, apiGet, apiSend } from '../lib/api';
import { inr, shortDate, statusTone, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, DataTable, Field, Input, Modal, PageHeader, Skeleton, Textarea, useToast, type Column } from '../components/ui';
import { CustomerSelect } from '../components/CustomerSelect';
import { ItemEditor, newItem } from '../components/ItemEditor';
import type { Item, Quote } from '../types';

type Draft = { customer_id: string; issue_date: string; valid_until: string; notes: string; terms: string; items: Item[] };
const today = () => new Date().toISOString().slice(0, 10);
const blank = (): Draft => ({ customer_id: '', issue_date: today(), valid_until: '', notes: '', terms: '', items: [newItem()] });

export default function Quotes() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank());
  const [detail, setDetail] = useState<Quote | null>(null);
  const [error, setError] = useState('');

  const quotes = useQuery({
    queryKey: ['quotes', search, status],
    queryFn: async () => (await apiGet<Quote[]>(`/quotes?limit=100&search=${encodeURIComponent(search)}&status=${status}`)).data,
  });

  const create = useMutation({
    mutationFn: async (value: Draft) => apiSend<Quote>('post', '/quotes', {
      customer_id: value.customer_id,
      issue_date: value.issue_date,
      valid_until: value.valid_until || null,
      notes: value.notes || null,
      terms: value.terms || null,
      items: value.items.map(({ description, hsn_sac, qty, unit_price_paise, discount_paise, tax_rate_pct }) => ({
        description, hsn_sac: hsn_sac || null, qty, unit_price_paise, discount_paise, tax_rate_pct,
      })),
    }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['quotes'] });
      notify('Quote created as draft');
      setOpen(false);
      setDetail(result.data);
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const action = useMutation({
    mutationFn: async ({ id, verb }: { id: string; verb: string }) => apiSend('post', `/quotes/${id}/${verb}`),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['quotes'] });
      notify(`Quote ${variables.verb === 'convert' ? 'converted to invoice' : `${variables.verb}ed`}`);
      setOpen(false);
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  const columns: Column<Quote>[] = [
    { key: 'number', header: 'Quote', render: (row) => <div><div className="font-medium text-ink">{row.number || `Draft ${row.id.slice(0, 6)}`}</div><div className="text-[11px] text-muted">Issued {shortDate(row.issue_date)}</div></div> },
    { key: 'valid', header: 'Valid until', render: (row) => <span className="text-xs text-muted">{shortDate(row.valid_until)}</span> },
    { key: 'total', header: 'Amount', render: (row) => <span className="font-medium text-ink">{inr(row.total_paise)}</span>, className: 'text-right' },
    { key: 'status', header: 'Status', render: (row) => <Badge tone={statusTone(row.status)}>{titleCase(row.status)}</Badge> },
    { key: 'items', header: 'Items', render: (row) => <span className="text-xs text-muted">{row.items.length} line{row.items.length === 1 ? '' : 's'}</span> },
    {
      key: 'actions', header: '', className: 'text-right',
      render: (row) => (
        <div className="flex justify-end gap-1">
          <button onClick={(e) => { e.stopPropagation(); setDetail(row); }} className="rounded-md p-1.5 text-muted hover:bg-slate-100" title="View"><Eye size={15} /></button>
          {row.status === 'DRAFT' && <button onClick={(e) => { e.stopPropagation(); action.mutate({ id: row.id, verb: 'send' }); }} className="rounded-md p-1.5 text-muted hover:bg-brand-50 hover:text-brand-600" title="Send"><Send size={15} /></button>}
          {row.status === 'SENT' && <button onClick={(e) => { e.stopPropagation(); action.mutate({ id: row.id, verb: 'accept' }); }} className="rounded-md p-1.5 text-muted hover:bg-emerald-50 hover:text-emerald-600" title="Accept"><Check size={15} /></button>}
          {row.status === 'SENT' && <button onClick={(e) => { e.stopPropagation(); action.mutate({ id: row.id, verb: 'reject' }); }} className="rounded-md p-1.5 text-muted hover:bg-rose-50 hover:text-rose-600" title="Reject"><X size={15} /></button>}
          {(['SENT', 'ACCEPTED'] as string[]).includes(row.status) && <button onClick={(e) => { e.stopPropagation(); action.mutate({ id: row.id, verb: 'convert' }); }} className="rounded-md p-1.5 text-muted hover:bg-brand-50 hover:text-brand-600" title="Convert to invoice"><FilePlus2 size={15} /></button>}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Quotes" subtitle="Prepare estimates, send them for approval and convert accepted quotes to invoices." actions={<Button variant="primary" onClick={() => { setDraft(blank()); setError(''); setOpen(true); }}><Plus size={16} /> New quote</Button>} />
      <Card>
        <CardHeader
          title={`${quotes.data?.length || 0} quotes`}
          action={<div className="flex gap-2"><Field label=""><Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search quotes…" /></Field><Field label=""><select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="">All statuses</option>{['DRAFT', 'SENT', 'ACCEPTED', 'REJECTED', 'EXPIRED', 'CONVERTED'].map((s) => <option key={s}>{s}</option>)}</select></Field></div>}
        />
        {quotes.isLoading ? <Skeleton rows={7} /> : <DataTable columns={columns} rows={quotes.data || []} empty="No quotes yet." onRowClick={setDetail} />}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="New quote" width="max-w-4xl">
        <form onSubmit={(e) => { e.preventDefault(); setError(''); create.mutate(draft); }} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Customer" className="sm:col-span-2"><CustomerSelect value={draft.customer_id} onChange={(v) => setDraft({ ...draft, customer_id: v })} /></Field>
            <Field label="Issue date"><Input type="date" value={draft.issue_date} onChange={(e) => setDraft({ ...draft, issue_date: e.target.value })} /></Field>
            <Field label="Valid until"><Input type="date" value={draft.valid_until} onChange={(e) => setDraft({ ...draft, valid_until: e.target.value })} /></Field>
          </div>
          <div><div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Line items</div><ItemEditor items={draft.items} onChange={(items) => setDraft({ ...draft, items })} /></div>
          <div className="grid gap-4 sm:grid-cols-2"><Field label="Notes"><Textarea value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} /></Field><Field label="Terms"><Textarea value={draft.terms} onChange={(e) => setDraft({ ...draft, terms: e.target.value })} /></Field></div>
          {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={create.isPending}>Create quote</Button></div>
        </form>
      </Modal>

      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail?.number || 'Quote details'} width="max-w-3xl">
        {detail && (
          <div className="space-y-5">
            <div className="flex flex-wrap gap-2"><Badge tone={statusTone(detail.status)}>{titleCase(detail.status)}</Badge><span className="text-xs text-muted">Issued {shortDate(detail.issue_date)} · Valid until {shortDate(detail.valid_until)}</span></div>
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full text-left text-xs"><thead className="bg-slate-50 text-[11px] uppercase text-muted"><tr><th className="px-3 py-2">Description</th><th className="px-3 py-2 text-right">Qty</th><th className="px-3 py-2 text-right">Rate</th><th className="px-3 py-2 text-right">Tax</th><th className="px-3 py-2 text-right">Amount</th></tr></thead>
                <tbody className="divide-y divide-line">{detail.items.map((item) => <tr key={item.id}><td className="px-3 py-2">{item.description}</td><td className="px-3 py-2 text-right">{item.qty}</td><td className="px-3 py-2 text-right">{inr(item.unit_price_paise)}</td><td className="px-3 py-2 text-right">{inr(item.tax_paise)}</td><td className="px-3 py-2 text-right font-medium">{inr(item.total_paise)}</td></tr>)}</tbody>
              </table>
            </div>
            <div className="flex justify-end"><div className="w-64 space-y-1 text-xs"><div className="flex justify-between"><span className="text-muted">Subtotal</span><span>{inr(detail.subtotal_paise)}</span></div><div className="flex justify-between"><span className="text-muted">Discount</span><span>{inr(detail.discount_paise)}</span></div><div className="flex justify-between"><span className="text-muted">Tax</span><span>{inr(detail.tax_paise)}</span></div><div className="flex justify-between border-t border-line pt-2 text-sm font-semibold"><span>Total</span><span>{inr(detail.total_paise)}</span></div></div></div>
            {detail.converted_invoice_id && <Link to={`/invoices/${detail.converted_invoice_id}`} className="text-xs font-medium text-brand-600 hover:underline">View converted invoice →</Link>}
            <div className="flex justify-end gap-2 border-t border-line pt-4">
              <Button onClick={() => setDetail(null)}>Close</Button>
              {detail.status === 'DRAFT' && <Button variant="primary" onClick={() => action.mutate({ id: detail.id, verb: 'send' })}><Send size={15} /> Send quote</Button>}
              {detail.status === 'SENT' && <Button variant="primary" onClick={() => action.mutate({ id: detail.id, verb: 'accept' })}><Check size={15} /> Accept</Button>}
              {['SENT', 'ACCEPTED'].includes(detail.status) && <Button variant="primary" onClick={() => action.mutate({ id: detail.id, verb: 'convert' })}><FilePlus2 size={15} /> Convert to invoice</Button>}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
