import { createContext, useCallback, useContext, useMemo, useState, type ButtonHTMLAttributes, type CSSProperties, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import { CheckCircle2, Info, X, XCircle } from 'lucide-react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  loading?: boolean;
};

export function Button({ variant = 'secondary', size = 'md', loading, className = '', children, disabled, ...props }: ButtonProps) {
  const variants: Record<string, string> = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700 shadow-sm',
    secondary: 'bg-white text-ink ring-1 ring-line hover:bg-slate-50 shadow-sm',
    ghost: 'text-muted hover:bg-slate-100',
    danger: 'bg-rose-600 text-white hover:bg-rose-700 shadow-sm',
  };
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${size === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm'} ${variants[variant]} ${className}`}
    >
      {loading && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
}

export function Card({ children, className = '', style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  return <div className={`rounded-xl border border-line bg-white shadow-card ${className}`} style={style}>{children}</div>;
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Field({ label, hint, children, className = '' }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-xs font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-muted">{hint}</span>}
    </label>
  );
}

const inputClass = 'w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100';
export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputClass} ${props.className || ''}`} />;
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${inputClass} min-h-[80px] resize-y ${props.className || ''}`} />;
}
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputClass} ${props.className || ''}`} />;
}

export function Badge({ children, tone = 'bg-slate-100 text-slate-700 ring-slate-200' }: { children: ReactNode; tone?: string }) {
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${tone}`}>{children}</span>;
}

export type Column<T> = { key: string; header: string; render: (row: T) => ReactNode; className?: string };

export function DataTable<T>({ columns, rows, empty = 'Nothing here yet', onRowClick }: { columns: Column<T>[]; rows: T[]; empty?: string; onRowClick?: (row: T) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50/80 text-[11px] uppercase tracking-wide text-muted">
          <tr>{columns.map((c) => <th key={c.key} className={`whitespace-nowrap px-5 py-3 font-semibold ${c.className || ''}`}>{c.header}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.length === 0 && (
            <tr><td colSpan={columns.length} className="px-5 py-12 text-center text-sm text-muted">{empty}</td></tr>
          )}
          {rows.map((row, index) => (
            <tr key={(row as { id?: string }).id || index} onClick={() => onRowClick?.(row)} className={onRowClick ? 'cursor-pointer hover:bg-slate-50/70' : 'hover:bg-slate-50/50'}>
              {columns.map((c) => <td key={c.key} className={`px-5 py-3 align-middle ${c.className || ''}`}>{c.render(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Modal({ open, onClose, title, children, width = 'max-w-lg' }: { open: boolean; onClose: () => void; title: string; children: ReactNode; width?: string }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4" onMouseDown={onClose}>
      <div className={`w-full ${width} max-h-[90vh] overflow-y-auto rounded-xl bg-white shadow-2xl`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-slate-100"><X size={16} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-5">
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="h-9 animate-pulse rounded-lg bg-slate-100" />)}
    </div>
  );
}

const TabsContext = createContext<{ value: string; onValueChange: (value: string) => void } | null>(null);

export function Tabs({ value, onValueChange, children, className = '' }: { value: string; onValueChange: (value: string) => void; children: ReactNode; className?: string }) {
  return (
    <TabsContext.Provider value={{ value, onValueChange }}>
      <div role="tablist" className={`flex flex-wrap gap-1 border-b border-line ${className}`}>{children}</div>
    </TabsContext.Provider>
  );
}

export function Tab({ value, children }: { value: string; children: ReactNode }) {
  const context = useContext(TabsContext);
  const active = context?.value === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => context?.onValueChange(value)}
      className={`border-b-2 px-3 py-2 text-sm font-medium transition ${active ? 'border-brand-600 text-brand-700' : 'border-transparent text-muted hover:border-line hover:text-ink'}`}
    >
      {children}
    </button>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{actions}</div>
    </div>
  );
}

type Toast = { id: number; message: string; kind: 'success' | 'error' | 'info' };
const ToastContext = createContext<{ notify: (message: string, kind?: Toast['kind']) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const notify = useCallback((message: string, kind: Toast['kind'] = 'success') => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, kind }]);
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 4000);
  }, []);
  const value = useMemo(() => ({ notify }), [notify]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-5 right-5 z-[60] flex w-80 flex-col gap-2">
        {toasts.map((toast) => (
          <div key={toast.id} className="flex items-start gap-2 rounded-xl border border-line bg-white px-4 py-3 text-sm shadow-lg">
            {toast.kind === 'success' ? <CheckCircle2 size={16} className="mt-0.5 text-emerald-600" /> : toast.kind === 'error' ? <XCircle size={16} className="mt-0.5 text-rose-600" /> : <Info size={16} className="mt-0.5 text-blue-600" />}
            <span className="flex-1 text-ink">{toast.message}</span>
            <button onClick={() => setToasts((current) => current.filter((t) => t.id !== toast.id))} className="text-muted"><X size={14} /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used inside ToastProvider');
  return context;
}
