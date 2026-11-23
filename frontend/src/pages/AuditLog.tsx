import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { apiErrorMessage, apiGet } from '../lib/api';
import { shortDate } from '../lib/format';
import { Badge, Card, CardHeader, DataTable, Input, PageHeader, Skeleton, type Column } from '../components/ui';
import type { Audit } from '../types';

export default function AuditLog() {
  const [action, setAction] = useState('');
  const [entity, setEntity] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const logs = useQuery({
    queryKey: ['audit', action, entity],
    queryFn: async () => (await apiGet<Audit[]>(`/audit?limit=100&action=${encodeURIComponent(action)}&entity_type=${encodeURIComponent(entity)}`)).data,
  });

  const columns: Column<Audit>[] = [
    { key: 'when', header: 'When', render: (row) => <div><div className="text-xs text-ink">{shortDate(row.created_at)}</div><div className="text-[11px] text-muted">{row.created_at ? new Date(row.created_at).toLocaleTimeString('en-IN') : ''}</div></div> },
    { key: 'action', header: 'Action', render: (row) => <Badge tone="bg-brand-50 text-brand-700 ring-brand-100">{row.action}</Badge> },
    { key: 'entity', header: 'Entity', render: (row) => <div><div className="text-xs text-ink">{row.entity_type}</div><div className="font-mono text-[10px] text-muted">{row.entity_id?.slice(0, 12) || '—'}</div></div> },
    { key: 'actor', header: 'Actor', render: (row) => <div><div className="text-xs text-ink">{row.actor_type}</div><div className="font-mono text-[10px] text-muted">{row.actor_id?.slice(0, 12) || '—'}</div></div> },
    { key: 'ip', header: 'IP', render: (row) => <span className="font-mono text-[11px] text-muted">{row.ip || '—'}</span> },
    {
      key: 'details', header: '', className: 'text-right',
      render: (row) => <button onClick={(e) => { e.stopPropagation(); setExpanded(expanded === row.id ? null : row.id); }} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted hover:bg-slate-100">{expanded === row.id ? 'Hide' : 'Details'}{expanded === row.id ? <ChevronUp size={13} /> : <ChevronDown size={13} />}</button>,
    },
  ];

  return (
    <div>
      <PageHeader title="Audit log" subtitle="Immutable record of changes across your tenant." />
      <Card>
        <CardHeader title={`${logs.data?.length || 0} events`} action={<div className="flex gap-2"><Input value={action} onChange={(e) => setAction(e.target.value)} placeholder="Filter action…" className="w-44" /><Input value={entity} onChange={(e) => setEntity(e.target.value)} placeholder="Filter entity…" className="w-44" /></div>} />
        {logs.isLoading ? <Skeleton rows={8} /> : (
          <div>
            <DataTable columns={columns} rows={logs.data || []} empty="No audit events." />
            {expanded && (() => {
              const row = (logs.data || []).find((item) => item.id === expanded);
              if (!row) return null;
              return (
                <div className="border-t border-line bg-slate-50/70 p-5">
                  <div className="mb-2 text-xs font-semibold text-ink">Change details</div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div><div className="mb-1 text-[11px] font-semibold uppercase text-muted">Before</div><pre className="overflow-x-auto rounded-lg bg-white p-3 text-[11px] ring-1 ring-line">{JSON.stringify(row.before ?? null, null, 2)}</pre></div>
                    <div><div className="mb-1 text-[11px] font-semibold uppercase text-muted">After</div><pre className="overflow-x-auto rounded-lg bg-white p-3 text-[11px] ring-1 ring-line">{JSON.stringify(row.after ?? null, null, 2)}</pre></div>
                  </div>
                </div>
              );
            })()}
          </div>
        )}
        {logs.isError && <div className="p-5 text-sm text-rose-600">{apiErrorMessage(logs.error)}</div>}
      </Card>
    </div>
  );
}
