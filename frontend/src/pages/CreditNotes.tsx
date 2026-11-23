import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, CircleSlash, Plus, Send } from 'lucide-react';
import { apiErrorMessage, apiGet, apiSend } from '../lib/api';
import { inr, shortDate, statusTone, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, DataTable, Field, Input, Modal, PageHeader, Select, Skeleton, Textarea, useToast, type Column } from '../components/ui';
import { CustomerSelect } from '../components/CustomerSelect';
import { ItemEditor, newItem } from '../components/ItemEditor';
import type { CreditNote, Item } from '../types';

type Draft = { customer_id: string; invoice_id: string; reason: string; refund_mode: string; items: Item[] };
const blank = (): Draft => ({ customer_id: '', invoice_id: '', reason: '', refund_mode: 'ADJUSTMENT', items: [newItem()] });

export default function CreditNotes() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank());
  const [error, setError] = useState('');
  const [applyId, setApplyId] = useState<string | null>(null);
  const [applyInvoice, setApplyInvoice] = useState('');
  const [applyAmount, setApplyAmount] = useState('');

  const notes = useQuery({
    queryKey: ['credit-notes'],
    queryFn: async () => (await apiGet<CreditNote[]>('/credit-notes?limit=100')).data,
  });

  const save = useMutation({
    mutationFn: async (value: Draft) => apiSend<CreditNote>('post', '/credit-notes', {
      customer_id: value.customer_id,
      invoice_id: value.invoice_id || null,
      reason: value.reason,
      refund_mode: value.refund_mode,
      items: value.items.map(({ description, hsn_sac, qty, unit_price_paise, discount_paise, tax_rate_pct }) => ({
        description, hsn_sac: hsn_sac || null, qty, unit_price_paise, discount_paise, tax_rate_pct,
      })),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credit-notes'] });
      notify('Credit note created as draft');
      setOpen(false);
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const action = useMutation({
    mutationFn: async ({ id, verb, body }: { id: string; verb: string; body?: unknown }) => apiSend('post', `/credit-notes/${id}/${verb}`, body),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['credit-notes'] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify(`Credit note ${variables.verb === 'apply' ? 'applied' : variables.verb === 'issue' ? 'issued' : 'voided'}`);
      setApplyId(null);
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  const columns: Column<CreditNote>[] = [
    { key: 'number', header: 'Credit note', render: (row) => <div><div className="font-medium text-ink">{row.number || 'Draft'}</div><div className="text-[11px] text-muted">{shortDate(row.created_at)}</div></div> },
    { key: 'reason', header: 'Reason', render: (row) => <div><div className="text-xs text-ink">{row.reason}</div><div className="text-[11px] text-muted">{titleCase(row.refund_mode)}</div></div> },
    { key: 'total', header: 'Amount', render: (row) => <span className="font-medium text-ink">{inr(row.total_paise)}</span>, className: 'text-right' },
    { key: 'applied', header: 'Applied', render: (row) => <span className="text-xs text-muted">{inr(row.applied_paise)}</span>, className: 'text-right' },
    { key: 'status', header: 'Status', render: (row) => <Badge tone={statusTone(row.status)}>{titleCase(row.status)}</Badge> },
    {
      key: 'actions', header: '', className: 'text-right',
      render: (row) => (
        <div className="flex justify-end gap-1">
          {row.status === 'DRAFT' && <button onClick={(e) => { e.stopPropagation(); action.mutate({ id: row.id, verb: 'issue' }); }} className="rounded-md p-1.5 text-muted hover:bg-brand-50 hover:text-brand-600" title="Issue"><Send size={15} /></button>}
          {['ISSUED', 'APPLIED'].includes(row.status) && <button onClick={(e) => { e.stopPropagation(); setApplyId(row.id); setApplyInvoice(row.invoice_id || ''); setApplyAmount(''); }} className="rounded-md p-1.5 text-muted hover:bg-emerald-50 hover:text-emerald-600" title="Apply"><Check size={15} /></button>}
          {!['VOID', 'APPLIED'].includes(row.status) && <button onClick={(e) => { e.stopPropagation(); if (confirm('Void this credit note?')) action.mutate({ id: row.id, verb: 'void' }); }} className="rounded-md p-1.5 text-muted hover:bg-rose-50 hover:text-rose-600" title="Void"><CircleSlash size={15} /></button>}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Credit notes" subtitle="Issue refunds and adjustments, then apply them against invoices." actions={<Button variant="primary" onClick={() => { setDraft(blank()); setError(''); setOpen(true); }}><Plus size={16} /> New credit note</Button>} />
      <Card>
        <CardHeader title={`${notes.data?.length || 0} credit notes`} />
        {notes.isLoading ? <Skeleton rows={6} /> : <DataTable columns={columns} rows={notes.data || []} empty="No credit notes yet." />}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="New credit note" width="max-w-4xl">
        <form onSubmit={(e) => { e.preventDefault(); setError(''); save.mutate(draft); }} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Customer"><CustomerSelect value={draft.customer_id} onChange={(v) => setDraft({ ...draft, customer_id: v, invoice_id: '' })} /></Field>
            <Field label="Link invoice (optional)"><Input value={draft.invoice_id} onChange={(e) => setDraft({ ...draft, invoice_id: e.target.value })} placeholder="Invoice ID" /></Field>
            <Field label="Refund mode"><Select value={draft.refund_mode} onChange={(e) => setDraft({ ...draft, refund_mode: e.target.value })}><option value="ADJUSTMENT">Adjustment</option><option value="REFUND">Cash refund</option></Select></Field>
            <Field label="Reason" className="sm:col-span-3"><Textarea value={draft.reason} onChange={(e) => setDraft({ ...draft, reason: e.target.value })} required placeholder="e.g. Pricing correction / damaged goods" /></Field>
          </div>
          <div><div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Credit items</div><ItemEditor items={draft.items} onChange={(items) => setDraft({ ...draft, items })} /></div>
          {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Create credit note</Button></div>
        </form>
      </Modal>

      <Modal open={!!applyId} onClose={() => setApplyId(null)} title="Apply credit note">
        <form onSubmit={(e) => { e.preventDefault(); if (!applyId) return; action.mutate({ id: applyId, verb: 'apply', body: { invoice_id: applyInvoice || null, amount_paise: applyAmount ? Math.round(Number(applyAmount) * 100) : null } }); }} className="space-y-4">
          <Field label="Invoice ID"><Input value={applyInvoice} onChange={(e) => setApplyInvoice(e.target.value)} placeholder="Leave blank to use linked invoice" /></Field>
          <Field label="Amount (₹)" hint="Leave blank to apply the full remaining credit"><Input type="number" step="0.01" min="0" value={applyAmount} onChange={(e) => setApplyAmount(e.target.value)} /></Field>
          <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setApplyId(null)}>Cancel</Button><Button type="submit" variant="primary" loading={action.isPending}>Apply credit</Button></div>
        </form>
      </Modal>
    </div>
  );
}
