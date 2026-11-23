import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pause, Play, Plus, RefreshCw, StopCircle } from 'lucide-react';
import { apiErrorMessage, apiGet, apiSend } from '../lib/api';
import { shortDate, statusTone, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, DataTable, Field, Input, Modal, PageHeader, Select, Skeleton, useToast, type Column } from '../components/ui';
import { CustomerSelect } from '../components/CustomerSelect';
import { ItemEditor, newItem } from '../components/ItemEditor';
import type { Item, Schedule } from '../types';

type Draft = { customer_id: string; name: string; frequency: string; interval: number; start_date: string; end_date: string; items: Item[] };
const today = () => new Date().toISOString().slice(0, 10);
const blank = (): Draft => ({ customer_id: '', name: '', frequency: 'MONTHLY', interval: 1, start_date: today(), end_date: '', items: [newItem()] });

export default function Recurring() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank());
  const [error, setError] = useState('');

  const schedules = useQuery({
    queryKey: ['recurring'],
    queryFn: async () => (await apiGet<Schedule[]>('/recurring?limit=100')).data,
  });

  const save = useMutation({
    mutationFn: async (value: Draft) => apiSend<Schedule>('post', '/recurring', {
      customer_id: value.customer_id,
      name: value.name,
      frequency: value.frequency,
      interval: value.interval,
      start_date: value.start_date,
      end_date: value.end_date || null,
      template: { items: value.items.map(({ description, hsn_sac, qty, unit_price_paise, discount_paise, tax_rate_pct }) => ({ description, hsn_sac: hsn_sac || null, qty, unit_price_paise, discount_paise, tax_rate_pct })) },
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recurring'] });
      notify('Recurring schedule created');
      setOpen(false);
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const action = useMutation({
    mutationFn: async ({ id, verb }: { id: string; verb: string }) => apiSend('post', `/recurring/${id}/${verb}`),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['recurring'] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify(variables.verb === 'generate-now' ? 'Invoice generated from schedule' : `Schedule ${variables.verb === 'pause' ? 'paused' : variables.verb === 'resume' ? 'resumed' : 'cancelled'}`);
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  const columns: Column<Schedule>[] = [
    { key: 'name', header: 'Schedule', render: (row) => <div><div className="font-medium text-ink">{row.name}</div><div className="text-[11px] text-muted">Every {row.interval} {row.frequency.toLowerCase()}{row.interval > 1 ? 's' : ''}</div></div> },
    { key: 'start', header: 'Starts', render: (row) => <span className="text-xs text-muted">{shortDate(row.start_date)}</span> },
    { key: 'next', header: 'Next run', render: (row) => <span className="text-xs font-medium text-ink">{shortDate(row.next_run_at)}</span> },
    { key: 'last', header: 'Last period', render: (row) => <span className="text-xs text-muted">{row.last_period || '—'}</span> },
    { key: 'status', header: 'Status', render: (row) => <Badge tone={statusTone(row.status)}>{titleCase(row.status)}</Badge> },
    {
      key: 'actions', header: '', className: 'text-right',
      render: (row) => (
        <div className="flex justify-end gap-1">
          <button onClick={(e) => { e.stopPropagation(); action.mutate({ id: row.id, verb: 'generate-now' }); }} className="rounded-md p-1.5 text-muted hover:bg-brand-50 hover:text-brand-600" title="Generate now"><RefreshCw size={15} /></button>
          {row.status === 'ACTIVE' ? <button onClick={(e) => { e.stopPropagation(); action.mutate({ id: row.id, verb: 'pause' }); }} className="rounded-md p-1.5 text-muted hover:bg-amber-50 hover:text-amber-600" title="Pause"><Pause size={15} /></button> : row.status === 'PAUSED' ? <button onClick={(e) => { e.stopPropagation(); action.mutate({ id: row.id, verb: 'resume' }); }} className="rounded-md p-1.5 text-muted hover:bg-emerald-50 hover:text-emerald-600" title="Resume"><Play size={15} /></button> : null}
          {row.status !== 'CANCELLED' && <button onClick={(e) => { e.stopPropagation(); if (confirm('Cancel this schedule?')) action.mutate({ id: row.id, verb: 'cancel' }); }} className="rounded-md p-1.5 text-muted hover:bg-rose-50 hover:text-rose-600" title="Cancel"><StopCircle size={15} /></button>}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Recurring invoices" subtitle="Automate repeat invoices on a monthly, quarterly or yearly cadence." actions={<Button variant="primary" onClick={() => { setDraft(blank()); setError(''); setOpen(true); }}><Plus size={16} /> New schedule</Button>} />
      <Card>
        <CardHeader title={`${schedules.data?.length || 0} schedules`} />
        {schedules.isLoading ? <Skeleton rows={6} /> : <DataTable columns={columns} rows={schedules.data || []} empty="No recurring schedules yet." />}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="New recurring schedule" width="max-w-4xl">
        <form onSubmit={(e) => { e.preventDefault(); setError(''); save.mutate(draft); }} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="Customer" className="sm:col-span-2"><CustomerSelect value={draft.customer_id} onChange={(v) => setDraft({ ...draft, customer_id: v })} /></Field>
            <Field label="Name" className="sm:col-span-2"><Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} required placeholder="Monthly retainer" /></Field>
            <Field label="Frequency"><Select value={draft.frequency} onChange={(e) => setDraft({ ...draft, frequency: e.target.value })}><option value="MONTHLY">Monthly</option><option value="QUARTERLY">Quarterly</option><option value="YEARLY">Yearly</option></Select></Field>
            <Field label="Interval"><Input type="number" min={1} value={draft.interval} onChange={(e) => setDraft({ ...draft, interval: Number(e.target.value) })} /></Field>
            <Field label="Start date"><Input type="date" value={draft.start_date} onChange={(e) => setDraft({ ...draft, start_date: e.target.value })} /></Field>
            <Field label="End date (optional)"><Input type="date" value={draft.end_date} onChange={(e) => setDraft({ ...draft, end_date: e.target.value })} /></Field>
          </div>
          <div><div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Template line items</div><ItemEditor items={draft.items} onChange={(items) => setDraft({ ...draft, items })} /></div>
          {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Create schedule</Button></div>
        </form>
      </Modal>
    </div>
  );
}
