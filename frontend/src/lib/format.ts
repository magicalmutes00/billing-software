export function inr(paise: number | undefined | null): string {
  const value = (paise ?? 0) / 100;
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(value);
}

export function shortDate(value: string | undefined | null): string {
  if (!value) return '—';
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function statusTone(status: string): string {
  switch (status) {
    case 'PAID':
    case 'CAPTURED':
    case 'ACCEPTED':
    case 'ACTIVE':
    case 'DONE':
      return 'bg-emerald-50 text-emerald-700 ring-emerald-200';
    case 'OVERDUE':
    case 'FAILED':
    case 'EXPIRED':
    case 'VOID':
      return 'bg-rose-50 text-rose-700 ring-rose-200';
    case 'PARTIALLY_PAID':
    case 'SENT':
    case 'ISSUED':
    case 'PENDING':
      return 'bg-amber-50 text-amber-700 ring-amber-200';
    case 'CANCELLED':
    case 'REFUNDED':
      return 'bg-slate-100 text-slate-600 ring-slate-200';
    default:
      return 'bg-indigo-50 text-indigo-700 ring-indigo-200';
  }
}

export function titleCase(value: string): string {
  return value.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}
