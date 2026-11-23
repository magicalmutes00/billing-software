import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, Plus, Printer, Shield, Users } from 'lucide-react';
import { apiErrorMessage, apiGet, apiSend } from '../lib/api';
import { shortDate, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, Field, Input, Modal, PageHeader, Skeleton, useToast } from '../components/ui';
import type { Tenant } from '../types';

type User = { id: string; email: string; full_name: string; status: string; roles: string[] };
type Role = { id: string; name: string; description?: string; permissions: string[] };

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [profile, setProfile] = useState<Tenant | null>(null);
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState({ email: '', full_name: '', password: '', roles: ['VIEWER'] });
  const [error, setError] = useState('');

  const tenant = useQuery({
    queryKey: ['tenant'],
    queryFn: async () => (await apiGet<Tenant>('/tenants/me')).data,
  });
  const users = useQuery({
    queryKey: ['users'],
    queryFn: async () => (await apiGet<User[]>('/tenants/users')).data,
  });
  const roles = useQuery({
    queryKey: ['roles'],
    queryFn: async () => (await apiGet<Role[]>('/tenants/roles')).data,
  });

  if (profile === null && tenant.data) setProfile(tenant.data);

  const saveTenant = useMutation({
    mutationFn: async (value: Tenant) => apiSend('patch', '/tenants/me', {
      name: value.name, legal_name: value.legal_name || null, gstin: value.gstin || null,
      state_code: value.state_code || null, address_line1: value.address_line1 || null,
      city: value.city || null, pincode: value.pincode || null,
    }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['tenant'] }); notify('Tenant profile saved'); },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  function setSetting(key: string, value: unknown) {
    setProfile((current) => current ? { ...current, settings: { ...current.settings, [key]: value } } : current);
  }

  const saveReceipt = useMutation({
    mutationFn: async (settings: Record<string, unknown>) => apiSend('patch', '/tenants/me', { settings }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['tenant'] }); notify('Counter receipt settings saved'); },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  const [pin, setPin] = useState('');
  const setMyPin = useMutation({
    mutationFn: async () => apiSend('post', '/auth/pin', { pin }),
    onSuccess: () => { setPin(''); notify('Manager PIN set — use it to approve voids/refunds', 'success'); },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  const createUser = useMutation({
    mutationFn: async () => apiSend('post', '/tenants/users', user),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      notify('User created');
      setOpen(false);
      setUser({ email: '', full_name: '', password: '', roles: ['VIEWER'] });
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const runJobs = useMutation({
    mutationFn: async () => apiSend('post', '/ops/jobs/run'),
    onSuccess: (result) => notify(`Jobs complete: ${JSON.stringify(result.data)}`, 'info'),
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  if (tenant.isLoading) return <Skeleton rows={10} />;
  if (!profile) return <div className="text-sm text-rose-600">{apiErrorMessage(tenant.error)}</div>;

  return (
    <div>
      <PageHeader title="Settings" subtitle="Tenant profile, team access and scheduled jobs." actions={<Button onClick={() => runJobs.mutate()} loading={runJobs.isPending}><Play size={15} /> Run jobs now</Button>} />
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Business profile" subtitle="Appears on invoices and portal" />
          <form onSubmit={(e) => { e.preventDefault(); saveTenant.mutate(profile); }} className="space-y-4 p-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Business name"><Input value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} /></Field>
              <Field label="Legal name"><Input value={profile.legal_name || ''} onChange={(e) => setProfile({ ...profile, legal_name: e.target.value })} /></Field>
              <Field label="GSTIN"><Input value={profile.gstin || ''} onChange={(e) => setProfile({ ...profile, gstin: e.target.value.toUpperCase() })} /></Field>
              <Field label="State code"><Input maxLength={2} value={profile.state_code || ''} onChange={(e) => setProfile({ ...profile, state_code: e.target.value.toUpperCase() })} /></Field>
              <Field label="Address"><Input value={profile.address_line1 || ''} onChange={(e) => setProfile({ ...profile, address_line1: e.target.value })} /></Field>
              <Field label="City"><Input value={profile.city || ''} onChange={(e) => setProfile({ ...profile, city: e.target.value })} /></Field>
              <Field label="PIN code"><Input value={profile.pincode || ''} onChange={(e) => setProfile({ ...profile, pincode: e.target.value })} /></Field>
              <Field label="Slug"><Input value={profile.slug} readOnly /></Field>
            </div>
            <div className="flex justify-end border-t border-line pt-4"><Button type="submit" variant="primary" loading={saveTenant.isPending}>Save profile</Button></div>
          </form>
        </Card>
        <Card>
          <CardHeader title="Counter receipt" subtitle="Printed on 80 mm counter receipts" />
          <div className="space-y-4 p-5">
            <Field label="Receipt header"><Input value={String(profile.settings.pos_receipt_header || '')} onChange={(e) => setSetting('pos_receipt_header', e.target.value)} placeholder={profile.name} /></Field>
            <Field label="Receipt footer"><Input value={String(profile.settings.pos_receipt_footer || '')} onChange={(e) => setSetting('pos_receipt_footer', e.target.value)} placeholder="Thank you! Visit again." /></Field>
            <Field label="Phone on receipt"><Input value={String(profile.settings.pos_phone || '')} onChange={(e) => setSetting('pos_phone', e.target.value)} placeholder="080-1234 5678" /></Field>
            <Field label="UPI ID (VPA) for checkout QR"><Input value={String(profile.settings.pos_upi_id || '')} onChange={(e) => setSetting('pos_upi_id', e.target.value)} placeholder="shopname@upi" /></Field>
            <Field label="UPI payee name"><Input value={String(profile.settings.pos_upi_name || '')} onChange={(e) => setSetting('pos_upi_name', e.target.value)} placeholder={profile.name} /></Field>
            <Field label="Tax mode for counter sales">
              <select value={String(profile.settings.pos_tax_mode || 'INCLUSIVE')} onChange={(e) => setSetting('pos_tax_mode', e.target.value)} className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm">
                <option value="INCLUSIVE">Inclusive — tile price is customer price</option>
                <option value="EXCLUSIVE">Exclusive — GST added at billing</option>
              </select>
            </Field>
            <label className="flex items-center gap-2 text-xs text-ink"><input type="checkbox" checked={profile.settings.pos_show_gstin !== false} onChange={(e) => setSetting('pos_show_gstin', e.target.checked)} className="rounded border-line text-brand-600 focus:ring-brand-500" /> Show GSTIN on receipt</label>
            <label className="flex items-center gap-2 text-xs text-ink"><input type="checkbox" checked={profile.settings.pos_round_off !== false} onChange={(e) => setSetting('pos_round_off', e.target.checked)} className="rounded border-line text-brand-600 focus:ring-brand-500" /> Round off totals to the nearest rupee</label>
            <div className="flex justify-end border-t border-line pt-4"><Button variant="primary" loading={saveReceipt.isPending} onClick={() => saveReceipt.mutate(profile.settings)}><Printer size={15} /> Save receipt settings</Button></div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Roles & permissions" subtitle={`${roles.data?.length || 0} roles`} />
          <div className="space-y-4 p-5">
            {(roles.data || []).map((role) => (
              <div key={role.id} className="rounded-lg border border-line p-3">
                <div className="flex items-center justify-between"><div className="flex items-center gap-2 text-sm font-medium text-ink"><Shield size={15} className="text-brand-600" />{role.name}</div><Badge>{role.permissions.length} perms</Badge></div>
                {role.description && <div className="mt-1 text-[11px] text-muted">{role.description}</div>}
                <div className="mt-2 flex flex-wrap gap-1">{role.permissions.map((permission) => <span key={permission} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-muted">{permission}</span>)}</div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Manager PIN" subtitle="Approve voids & refunds at the counter without a full owner login" />
          <form onSubmit={(e) => { e.preventDefault(); setMyPin.mutate(); }} className="space-y-4 p-5">
            <Field label="Your PIN (4–12 digits)"><Input type="password" inputMode="numeric" value={pin} onChange={(e) => setPin(e.target.value)} minLength={4} maxLength={12} required placeholder="••••" /></Field>
            <p className="text-[11px] text-muted">A cashier can enter this PIN to approve a protected action. Only staff with the relevant permission can set a working PIN.</p>
            <div className="flex justify-end border-t border-line pt-4"><Button type="submit" variant="primary" loading={setMyPin.isPending} disabled={pin.length < 4}><Shield size={15} /> Set PIN</Button></div>
          </form>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader title="Team members" subtitle={`${users.data?.length || 0} users`} action={<Button size="sm" variant="primary" onClick={() => { setError(''); setOpen(true); }}><Plus size={15} /> Invite user</Button>} />
        {users.isLoading ? <Skeleton rows={5} /> : (
          <div className="divide-y divide-line">
            {(users.data || []).map((item) => (
              <div key={item.id} className="flex flex-wrap items-center gap-4 px-5 py-3">
                <div className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100 text-xs font-semibold text-ink">{item.full_name?.slice(0, 2).toUpperCase() || item.email.slice(0, 2).toUpperCase()}</div>
                <div className="min-w-0 flex-1"><div className="text-sm font-medium text-ink">{item.full_name || '—'}</div><div className="text-[11px] text-muted">{item.email}</div></div>
                <div className="flex gap-1">{item.roles.map((role) => <Badge key={role} tone="bg-brand-50 text-brand-700 ring-brand-100">{role}</Badge>)}</div>
                <Badge tone={item.status === 'ACTIVE' ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-slate-100 text-slate-600 ring-slate-200'}>{titleCase(item.status)}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="Invite a team member">
        <form onSubmit={(e) => { e.preventDefault(); createUser.mutate(); }} className="space-y-4">
          <Field label="Full name"><Input value={user.full_name} onChange={(e) => setUser({ ...user, full_name: e.target.value })} required /></Field>
          <Field label="Email"><Input type="email" value={user.email} onChange={(e) => setUser({ ...user, email: e.target.value })} required /></Field>
          <Field label="Temporary password"><Input type="password" value={user.password} onChange={(e) => setUser({ ...user, password: e.target.value })} required minLength={8} /></Field>
          <Field label="Role"><select value={user.roles[0]} onChange={(e) => setUser({ ...user, roles: [e.target.value] })} className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm">{(roles.data || []).map((role) => <option key={role.id} value={role.name}>{role.name}</option>)}</select></Field>
          {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={createUser.isPending}>Create user</Button></div>
        </form>
      </Modal>
      <p className="mt-4 text-[11px] text-muted">Tenant created {shortDate(tenant.data?.id ? '2026-01-01' : null)} · All data is scoped by tenant ID and PostgreSQL row-level security.</p>
    </div>
  );
}
