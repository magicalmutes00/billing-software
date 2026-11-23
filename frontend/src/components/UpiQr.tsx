import { useQuery } from '@tanstack/react-query';
import { apiText } from '../lib/api';

/** Renders the server-generated UPI intent QR (exact amount) as inline SVG. */
export function UpiQr({ amountPaise, note }: { amountPaise: number; note?: string }) {
  const qr = useQuery({
    queryKey: ['pos', 'upi-qr', amountPaise, note],
    queryFn: () => apiText(`/pos/upi-qr?amount_paise=${amountPaise}&tn=${encodeURIComponent(note || 'Counter sale')}`),
    enabled: amountPaise > 0,
    retry: false,
    staleTime: 60_000,
  });
  if (qr.isLoading) return <div className="py-6 text-center text-xs text-muted">Generating UPI QR…</div>;
  if (qr.isError) return <div className="py-4 text-center text-xs text-muted">Set a UPI ID in Settings → Counter receipt to show the QR.</div>;
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="h-40 w-40 [&>svg]:h-full [&>svg]:w-full" dangerouslySetInnerHTML={{ __html: qr.data || '' }} />
      <div className="text-[11px] text-muted">Scan to pay {`₹${(amountPaise / 100).toFixed(2)}`}</div>
    </div>
  );
}
