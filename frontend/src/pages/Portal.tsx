import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Boxes, Check, CreditCard, FileText, LogOut, Mail, X } from 'lucide-react';
import { apiErrorMessage, apiGet, apiSend, clearTokens, PORTAL_KEY } from '../lib/api';
import { inr, shortDate, statusTone, titleCase } from '../lib/format';
import { Badge, Button, Card, CardHeader, Field, Input, Skeleton, useToast } from '../components/ui';
import type { Invoice, Quote } from '../types';

export default function Portal() {
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(PORTAL_KEY));
  const [email, setEmail] = useState('');
  const [slug, setSlug] = useState('acme');
  const [error, setError] = useState('');
  const [active, setActive] = useState<'invoices' | 'quotes'>('invoices');

  const request = useMutation({
    mutationFn: async () => apiSend<{ access_token: string }>('post', '/portal/token', { email, tenant_slug: slug || null }),
    onSuccess: (result) => {
      localStorage.setItem(PORTAL_KEY, result.data.access_token);
      setToken(result.data.access_token);
      setError('');
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const me = useQuery({
    queryKey: ['portal', 'me'],
    enabled: !!token,
    queryFn: async () => (await apiGet<{ id: string; display_name: string; email: string; tenant_name: string }>('/portal/me')).data,
  });

  const invoices = useQuery({
    queryKey: ['portal', 'invoices'],
    enabled: !!token && active === 'invoices',
    queryFn: async () => (await apiGet<Invoice[]>('/portal/invoices')).data,
  });

  const quotes = useQuery({
    queryKey: ['portal', 'quotes'],
    enabled: !!token && active === 'quotes',
    queryFn: async () => (await apiGet<Quote[]>('/portal/quotes')).data,
  });

  const quoteAction = useMutation({
    mutationFn: async ({ id, verb }: { id: string; verb: string }) => apiSend('post', `/portal/quotes/${id}/${verb}`),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['portal', 'quotes'] });
      notify(`Quote ${variables.verb === 'accept' ? 'accepted' : 'rejected'}`);
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  const pay = useMutation({
    mutationFn: async (invoice: Invoice) => {
      const result = await apiSend<{ payment_id: string; checkout_url: string }>('post', `/portal/invoices/${invoice.id}/pay`);
      await apiSend('post', `/portal/payments/${result.data.payment_id}/simulate`);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portal', 'invoices'] });
      notify('Payment simulated successfully');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  function logout() {
    clearTokens();
    setToken(null);
    queryClient.clear();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    request.mutate();
  }

  if (!token) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#f7f8fa] p-5">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex items-center justify-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 text-white"><Boxes size={20} /></div>
            <div className="text-lg font-semibold text-ink">Billing · Client portal</div>
          </div>
          <Card className="p-6">
            <h1 className="text-lg font-semibold text-ink">Access your documents</h1>
            <p className="mt-1 text-sm text-muted">Enter the email address on your account and your tenant slug to get a secure single-use style access link.</p>
            <form onSubmit={submit} className="mt-6 space-y-4">
              <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="you@company.com" /></Field>
              <Field label="Tenant slug"><Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="acme" /></Field>
              {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
              <Button type="submit" variant="primary" className="w-full" loading={request.isPending}><Mail size={16} /> Send portal link</Button>
            </form>
            <div className="mt-5 border-t border-line pt-4 text-xs text-muted">Demo: <b className="text-ink">billing@bengaluru.example.com</b> / tenant <b className="text-ink">acme</b></div>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f7f8fa]">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-5 py-4">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600 text-white"><Boxes size={18} /></div>
          <div>
            <div className="text-sm font-semibold text-ink">Client portal</div>
            <div className="text-[11px] text-muted">{me.data?.tenant_name || 'Loading…'}</div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block"><div className="text-xs font-medium text-ink">{me.data?.display_name}</div><div className="text-[11px] text-muted">{me.data?.email}</div></div>
            <Button size="sm" onClick={logout}><LogOut size={14} /> Sign out</Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl p-5 lg:p-8">
        {me.isLoading ? <Skeleton rows={5} /> : (
          <>
            <div className="mb-6"><h1 className="text-xl font-semibold text-ink">Hello, {me.data?.display_name}</h1><p className="mt-1 text-sm text-muted">Review quotes, invoices and make payments.</p></div>
            <div className="mb-5 flex gap-2">
              <button onClick={() => setActive('invoices')} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${active === 'invoices' ? 'bg-brand-600 text-white' : 'bg-white text-muted ring-1 ring-line'}`}><FileText size={15} /> Invoices</button>
              <button onClick={() => setActive('quotes')} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${active === 'quotes' ? 'bg-brand-600 text-white' : 'bg-white text-muted ring-1 ring-line'}`}><FileText size={15} /> Quotes</button>
            </div>
            {active === 'invoices' && (
              <div className="space-y-4">
                {invoices.isLoading && <Skeleton rows={4} />}
                {(invoices.data || []).map((invoice) => (
                  <Card key={invoice.id}>
                    <div className="flex flex-wrap items-center gap-4 p-5">
                      <div className="grid h-10 w-10 place-items-center rounded-lg bg-brand-50 text-brand-700"><FileText size={18} /></div>
                      <div className="min-w-0 flex-1"><div className="font-medium text-ink">{invoice.number || 'Draft invoice'}</div><div className="text-xs text-muted">Issued {shortDate(invoice.issue_date)} · Due {shortDate(invoice.due_date)}</div></div>
                      <div className="text-right"><div className="text-sm font-semibold text-ink">{inr(invoice.total_paise)}</div><div className="text-[11px] text-muted">Balance {inr(invoice.balance_paise)}</div></div>
                      <Badge tone={statusTone(invoice.status)}>{titleCase(invoice.status)}</Badge>
                      <a href={`/api/v1/invoices/${invoice.id}/pdf`} target="_blank" rel="noreferrer"><Button size="sm">View PDF</Button></a>
                      {invoice.balance_paise > 0 && invoice.status !== 'CANCELLED' && <Button size="sm" variant="primary" loading={pay.isPending} onClick={() => pay.mutate(invoice)}><CreditCard size={14} /> Pay now</Button>}
                    </div>
                  </Card>
                ))}
                {!invoices.isLoading && !invoices.data?.length && <Card className="p-12 text-center text-sm text-muted">No invoices for your account.</Card>}
              </div>
            )}
            {active === 'quotes' && (
              <div className="space-y-4">
                {quotes.isLoading && <Skeleton rows={4} />}
                {(quotes.data || []).map((quote) => (
                  <Card key={quote.id}>
                    <CardHeader title={quote.number || `Quote ${quote.id.slice(0, 6)}`} subtitle={`Valid until ${shortDate(quote.valid_until)}`} action={<Badge tone={statusTone(quote.status)}>{titleCase(quote.status)}</Badge>} />
                    <div className="flex flex-wrap items-center gap-4 p-5">
                      <div className="flex-1 text-sm text-muted">{quote.items.length} line items · {inr(quote.total_paise)} total</div>
                      {quote.status === 'SENT' && <>
                        <Button size="sm" variant="primary" onClick={() => quoteAction.mutate({ id: quote.id, verb: 'accept' })}><Check size={14} /> Accept</Button>
                        <Button size="sm" onClick={() => quoteAction.mutate({ id: quote.id, verb: 'reject' })}><X size={14} /> Decline</Button>
                      </>}
                    </div>
                  </Card>
                ))}
                {!quotes.isLoading && !quotes.data?.length && <Card className="p-12 text-center text-sm text-muted">No quotes for your account.</Card>}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
