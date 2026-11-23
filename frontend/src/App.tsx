import { lazy, Suspense, useState, type FormEvent, type ReactNode } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  BarChart3, Boxes, CircleDollarSign, ClipboardList, FileText, History, LayoutDashboard,
  LogOut, Menu, Package, Receipt, RefreshCw, Settings, ShieldCheck, ShoppingCart, Store, Users, X,
} from 'lucide-react';
import { useAuth } from './context/AuthContext';
import { Button, Card, Field, Input, Skeleton } from './components/ui';
import { apiErrorMessage } from './lib/api';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Customers = lazy(() => import('./pages/Customers'));
const Quotes = lazy(() => import('./pages/Quotes'));
const Invoices = lazy(() => import('./pages/Invoices'));
const Payments = lazy(() => import('./pages/Payments'));
const CreditNotes = lazy(() => import('./pages/CreditNotes'));
const Recurring = lazy(() => import('./pages/Recurring'));
const Reports = lazy(() => import('./pages/Reports'));
const AuditLog = lazy(() => import('./pages/AuditLog'));
const SettingsPage = lazy(() => import('./pages/Settings'));
const Portal = lazy(() => import('./pages/Portal'));
const Pos = lazy(() => import('./pages/Pos'));
const Catalog = lazy(() => import('./pages/Catalog'));
const PosSales = lazy(() => import('./pages/PosSales'));

const nav = [
  { to: '/pos', label: 'Counter', icon: ShoppingCart, permission: 'pos.sell' },
  { to: '/', label: 'Overview', icon: LayoutDashboard, permission: 'reports.read' },
  { to: '/pos/sales', label: 'Counter sales', icon: Receipt, permission: 'pos.reports' },
  { to: '/catalog', label: 'Products', icon: Package, permission: 'catalog.read' },
  { to: '/customers', label: 'Customers', icon: Users, permission: 'customers.read' },
  { to: '/quotes', label: 'Quotes', icon: ClipboardList, permission: 'quotes.read' },
  { to: '/invoices', label: 'Invoices', icon: FileText, permission: 'invoices.read' },
  { to: '/payments', label: 'Payments', icon: CircleDollarSign, permission: 'payments.read' },
  { to: '/credit-notes', label: 'Credit notes', icon: Receipt, permission: 'credit_notes.read' },
  { to: '/recurring', label: 'Recurring', icon: RefreshCw, permission: 'recurring.read' },
  { to: '/reports', label: 'Reports', icon: BarChart3, permission: 'reports.read' },
  { to: '/audit', label: 'Audit log', icon: History, permission: 'audit.read' },
  { to: '/settings', label: 'Settings', icon: Settings, permission: 'settings.read' },
];

function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('owner@acme.example.com');
  const [password, setPassword] = useState('Password123!');
  const [shop, setShop] = useState(() => localStorage.getItem('billing_shop') || '');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      localStorage.setItem('billing_shop', shop);
      const loggedIn = await login(email, password, shop || undefined);
      const counterOnly = loggedIn?.permissions.includes('pos.sell') && !loggedIn.permissions.includes('reports.read');
      navigate(counterOnly ? '/pos' : '/');
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 text-white"><Boxes size={20} /></div>
            <div>
              <div className="text-lg font-semibold tracking-tight text-ink">Billing</div>
              <div className="text-xs text-muted">Multi-tenant invoicing workspace</div>
            </div>
          </div>
          <Card className="p-6">
            <h1 className="text-lg font-semibold text-ink">Welcome back</h1>
            <p className="mt-1 text-sm text-muted">Sign in to manage your tenants, invoices and payments.</p>
            <form onSubmit={submit} className="mt-6 space-y-4">
              <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" /></Field>
              <Field label="Password"><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" /></Field>
              <Field label="Shop code" hint="Required only when the same email is used by more than one shop."><Input value={shop} onChange={(e) => setShop(e.target.value)} placeholder="e.g. chai-indiranagar" autoComplete="organization" /></Field>
              {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
              <Button type="submit" variant="primary" loading={busy} className="w-full">Sign in</Button>
            </form>
            <div className="mt-5 space-y-1 border-t border-line pt-4 text-xs text-muted">
              <div>Demo: <span className="font-medium text-ink">owner@acme.example.com</span> / <span className="font-medium text-ink">Password123!</span></div>
              <div>Retail: <span className="font-medium text-ink">owner@chaicorner.example.com</span> · shop <span className="font-medium text-ink">chai-indiranagar</span> or <span className="font-medium text-ink">chai-koramangala</span></div>
              <div>Counter: <span className="font-medium text-ink">cashier@chaicorner.example.com</span> · shop <span className="font-medium text-ink">chai-indiranagar</span></div>
            </div>
          </Card>
        </div>
      </div>
      <div className="hidden bg-gradient-to-br from-brand-700 via-brand-600 to-indigo-900 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-2 text-sm font-medium"><ShieldCheck size={18} /> Built for GST-compliant billing</div>
        <div className="max-w-md">
          <h2 className="text-3xl font-semibold leading-tight">Everything from quote to cash, in one clean workspace.</h2>
          <p className="mt-4 text-sm text-white/75">Track receivables, issue tax invoices, record payments and give customers a self-service portal — with tenant isolation built in.</p>
          <div className="mt-8 grid grid-cols-2 gap-3 text-sm">
            {['Quotes → invoices', 'Payments & refunds', 'GST summaries', 'Audit trail'].map((item) => (
              <div key={item} className="rounded-lg bg-white/10 px-3 py-2 ring-1 ring-white/15">{item}</div>
            ))}
          </div>
        </div>
        <div className="text-xs text-white/50">© 2026 Billing Systems</div>
      </div>
    </div>
  );
}

function AdminLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#f7f8fa]">
      {open && <button aria-label="Close navigation" onClick={() => setOpen(false)} className="fixed inset-0 z-30 bg-ink/30 lg:hidden" />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-line bg-white transition-transform lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex h-16 items-center justify-between px-5">
          <div className="flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white"><Boxes size={17} /></div>
            <div className="text-sm font-semibold tracking-tight text-ink">Billing</div>
          </div>
          <button onClick={() => setOpen(false)} className="text-muted lg:hidden"><X size={18} /></button>
        </div>
        <div className="mx-4 mb-4 rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-line">
          <div className="flex items-center gap-1.5 truncate text-xs font-medium text-ink"><Store size={13} className="shrink-0 text-brand-600" />{user?.tenant_name || 'Tenant'}</div>
          <div className="truncate text-[11px] text-muted">Shop: {user?.tenant_slug || '—'}</div>
          <div className="truncate text-[11px] text-muted">{user?.roles.join(', ')}</div>
        </div>
        <nav className="scroll-thin flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
          {nav.filter((item) => !item.permission || user?.permissions.includes(item.permission)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/' || item.to === '/pos'}
              onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${isActive || (item.to !== '/' && location.pathname.startsWith(item.to)) ? 'bg-brand-50 font-medium text-brand-700' : 'text-muted hover:bg-slate-50 hover:text-ink'}`}
            >
              <item.icon size={17} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-line p-3">
          <div className="mb-2 truncate px-2 text-xs text-muted">{user?.email}</div>
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => { logout(); navigate('/login'); }}><Store size={15} /> Switch shop</Button>
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => { logout(); navigate('/login'); }}><LogOut size={15} /> Sign out</Button>
        </div>
      </aside>
      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-line bg-white/90 px-5 backdrop-blur">
          <button onClick={() => setOpen(true)} className="text-muted lg:hidden"><Menu size={20} /></button>
          <div className="text-sm font-medium text-ink">{nav.find((n) => n.to === location.pathname)?.label || 'Workspace'}</div>
          <div className="ml-auto text-xs text-muted">{new Date().toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}</div>
        </header>
        <main className="mx-auto max-w-[1400px] p-5 lg:p-7">{children}</main>
      </div>
    </div>
  );
}

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="grid min-h-screen place-items-center"><Skeleton rows={8} /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return <AdminLayout>{children}</AdminLayout>;
}

function Landing() {
  const { user, loading } = useAuth();
  if (loading) return <div className="grid min-h-screen place-items-center"><Skeleton rows={6} /></div>;
  if (!user) return <Login />;
  return <Navigate to={user.permissions.includes('pos.sell') && !user.permissions.includes('reports.read') ? '/pos' : '/'} replace />;
}

function DashboardRoute() {
  const { user } = useAuth();
  if (user?.permissions.includes('pos.sell') && !user.permissions.includes('reports.read')) {
    return <Navigate to="/pos" replace />;
  }
  return <Dashboard />;
}

export default function App() {
  return (
    <Suspense fallback={<div className="grid min-h-screen place-items-center"><Skeleton rows={8} /></div>}>
      <Routes>
        <Route path="/portal/*" element={<Portal />} />
        <Route path="/login" element={<Landing />} />
        <Route path="/" element={<Protected><DashboardRoute /></Protected>} />
        <Route path="/pos" element={<Protected><Pos /></Protected>} />
        <Route path="/pos/sales" element={<Protected><PosSales /></Protected>} />
        <Route path="/pos/sales/:id" element={<Protected><PosSales /></Protected>} />
        <Route path="/catalog" element={<Protected><Catalog /></Protected>} />
        <Route path="/customers" element={<Protected><Customers /></Protected>} />
        <Route path="/quotes" element={<Protected><Quotes /></Protected>} />
        <Route path="/invoices" element={<Protected><Invoices /></Protected>} />
        <Route path="/invoices/:id" element={<Protected><Invoices /></Protected>} />
        <Route path="/payments" element={<Protected><Payments /></Protected>} />
        <Route path="/credit-notes" element={<Protected><CreditNotes /></Protected>} />
        <Route path="/recurring" element={<Protected><Recurring /></Protected>} />
        <Route path="/reports" element={<Protected><Reports /></Protected>} />
        <Route path="/audit" element={<Protected><AuditLog /></Protected>} />
        <Route path="/settings" element={<Protected><SettingsPage /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
