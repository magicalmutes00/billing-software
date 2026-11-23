import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Edit2, Plus, Search, Trash2 } from 'lucide-react';
import { apiErrorMessage, apiGet, apiSend } from '../lib/api';
import { inr, shortDate, statusTone, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, DataTable, Field, Input, Modal, PageHeader, Select, Skeleton, Textarea, useToast, type Column } from '../components/ui';
import type { Customer } from '../types';

type CustomerDraft = {
  legal_name: string;
  display_name: string;
  gstin: string;
  tax_type: string;
  state_code: string;
  email: string;
  phone: string;
  payment_terms_days: number;
  credit_limit_paise: number;
  notes: string;
  line1: string;
  city: string;
  pincode: string;
};

const empty: CustomerDraft = {
  legal_name: '', display_name: '', gstin: '', tax_type: 'UNREGISTERED', state_code: 'KA',
  email: '', phone: '', payment_terms_days: 15, credit_limit_paise: 0, notes: '',
  line1: '', city: '', pincode: '',
};

function draftFrom(customer: Customer): CustomerDraft {
  const address = customer.addresses?.[0];
  return {
    legal_name: customer.legal_name,
    display_name: customer.display_name,
    gstin: customer.gstin || '',
    tax_type: customer.tax_type,
    state_code: customer.state_code,
    email: customer.email || '',
    phone: customer.phone || '',
    payment_terms_days: customer.payment_terms_days,
    credit_limit_paise: customer.credit_limit_paise || 0,
    notes: customer.notes || '',
    line1: address?.line1 || '',
    city: address?.city || '',
    pincode: address?.pincode || '',
  };
}

export default function Customers() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Customer | null>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<CustomerDraft>(empty);

  const customers = useQuery({
    queryKey: ['customers', search],
    queryFn: async () => (await apiGet<Customer[]>(`/customers?search=${encodeURIComponent(search)}&limit=100`)).data,
  });

  const save = useMutation({
    mutationFn: async (value: CustomerDraft) => {
      const payload = {
        legal_name: value.legal_name,
        display_name: value.display_name,
        gstin: value.gstin || null,
        tax_type: value.tax_type,
        state_code: value.state_code,
        email: value.email || null,
        phone: value.phone || null,
        payment_terms_days: value.payment_terms_days,
        credit_limit_paise: value.credit_limit_paise || null,
        notes: value.notes || null,
        addresses: value.line1 && value.city && value.pincode ? [{
          type: 'BILLING', line1: value.line1, city: value.city, state_code: value.state_code,
          pincode: value.pincode, is_default: true,
        }] : [],
      };
      if (editing) return apiSend('patch', `/customers/${editing.id}`, payload);
      return apiSend('post', '/customers', payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify(editing ? 'Customer updated' : 'Customer created');
      setOpen(false);
      setEditing(null);
    },
    onError: (error) => notify(apiErrorMessage(error), 'error'),
  });

  const remove = useMutation({
    mutationFn: async (customer: Customer) => apiSend('delete', `/customers/${customer.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      notify('Customer archived');
    },
    onError: (error) => notify(apiErrorMessage(error), 'error'),
  });

  function newCustomer() {
    setEditing(null);
    setDraft(empty);
    setOpen(true);
  }

  function editCustomer(customer: Customer) {
    setEditing(customer);
    setDraft(draftFrom(customer));
    setOpen(true);
  }

  const columns: Column<Customer>[] = [
    {
      key: 'name', header: 'Customer',
      render: (row) => (
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-50 text-xs font-semibold text-brand-700">{row.display_name.slice(0, 2).toUpperCase()}</div>
          <div><div className="font-medium text-ink">{row.display_name}</div><div className="text-[11px] text-muted">{row.legal_name}</div></div>
        </div>
      ),
    },
    { key: 'gstin', header: 'GSTIN / State', render: (row) => <div><div className="font-mono text-xs text-ink">{row.gstin || '—'}</div><div className="text-[11px] text-muted">{row.state_code} · {titleCase(row.tax_type)}</div></div> },
    { key: 'email', header: 'Contact', render: (row) => <div><div className="text-xs text-ink">{row.email || '—'}</div><div className="text-[11px] text-muted">{row.phone || '—'}</div></div> },
    { key: 'outstanding', header: 'Outstanding', render: (row) => <span className="font-medium text-ink">{inr(row.outstanding_paise)}</span>, className: 'text-right' },
    { key: 'terms', header: 'Terms', render: (row) => <span className="text-xs text-muted">{row.payment_terms_days} days</span> },
    { key: 'status', header: 'Status', render: (row) => <Badge tone={statusTone(row.status)}>{titleCase(row.status)}</Badge> },
    { key: 'created', header: 'Added', render: (row) => <span className="text-xs text-muted">{shortDate(row.created_at)}</span> },
    {
      key: 'actions', header: '',
      render: (row) => (
        <div className="flex justify-end gap-1">
          <button onClick={(e) => { e.stopPropagation(); editCustomer(row); }} className="rounded-md p-1.5 text-muted hover:bg-slate-100 hover:text-ink" aria-label="Edit"><Edit2 size={15} /></button>
          <button onClick={(e) => { e.stopPropagation(); if (confirm(`Archive ${row.display_name}?`)) remove.mutate(row); }} className="rounded-md p-1.5 text-muted hover:bg-rose-50 hover:text-rose-600" aria-label="Archive"><Trash2 size={15} /></button>
        </div>
      ),
      className: 'text-right',
    },
  ];

  return (
    <div>
      <PageHeader title="Customers" subtitle="Maintain customer master data, GST details and payment terms." actions={<Button variant="primary" onClick={newCustomer}><Plus size={16} /> New customer</Button>} />
      <Card>
        <CardHeader
          title={`${customers.data?.length || 0} customers`}
          action={<div className="relative w-64"><Search size={15} className="absolute left-3 top-2.5 text-muted" /><Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search customers…" className="pl-9" /></div>}
        />
        {customers.isLoading ? <Skeleton rows={8} /> : (
          <DataTable
            columns={columns}
            rows={customers.data || []}
            empty="No customers found. Create one to get started."
            onRowClick={editCustomer}
          />
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? 'Edit customer' : 'New customer'} width="max-w-2xl">
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(draft); }} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Display name"><Input required value={draft.display_name} onChange={(e) => setDraft({ ...draft, display_name: e.target.value })} /></Field>
            <Field label="Legal name"><Input required value={draft.legal_name} onChange={(e) => setDraft({ ...draft, legal_name: e.target.value })} /></Field>
            <Field label="GSTIN" hint="Optional for unregistered customers"><Input value={draft.gstin} onChange={(e) => setDraft({ ...draft, gstin: e.target.value.toUpperCase() })} placeholder="29ABCDE1234F1Z5" /></Field>
            <Field label="Tax type"><Select value={draft.tax_type} onChange={(e) => setDraft({ ...draft, tax_type: e.target.value })}><option value="REGISTERED">Registered</option><option value="UNREGISTERED">Unregistered</option><option value="COMPOSITION">Composition</option></Select></Field>
            <Field label="State code"><Input maxLength={2} value={draft.state_code} onChange={(e) => setDraft({ ...draft, state_code: e.target.value.toUpperCase() })} placeholder="KA" /></Field>
            <Field label="Payment terms (days)"><Input type="number" min={0} value={draft.payment_terms_days} onChange={(e) => setDraft({ ...draft, payment_terms_days: Number(e.target.value) })} /></Field>
            <Field label="Email"><Input type="email" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} /></Field>
            <Field label="Phone"><Input value={draft.phone} onChange={(e) => setDraft({ ...draft, phone: e.target.value })} /></Field>
          </div>
          <div className="border-t border-line pt-4">
            <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Primary billing address</div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Address line" className="sm:col-span-3"><Input value={draft.line1} onChange={(e) => setDraft({ ...draft, line1: e.target.value })} /></Field>
              <Field label="City"><Input value={draft.city} onChange={(e) => setDraft({ ...draft, city: e.target.value })} /></Field>
              <Field label="State code"><Input maxLength={2} value={draft.state_code} readOnly /></Field>
              <Field label="PIN code"><Input value={draft.pincode} onChange={(e) => setDraft({ ...draft, pincode: e.target.value })} /></Field>
            </div>
          </div>
          <Field label="Notes"><Textarea value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} placeholder="Internal notes…" /></Field>
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <Button type="button" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={save.isPending}>{editing ? 'Save changes' : 'Create customer'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
