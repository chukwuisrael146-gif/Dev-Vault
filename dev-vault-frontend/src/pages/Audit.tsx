import { useState } from 'react';
import { useWorkspace } from '../lib/workspace';
import { useResource } from '../lib/data';
import type { AuditEvent } from '../lib/data';
import type { Page } from '../lib/api';
import { EmptyState, PageHeading, Status } from '../components/ui';
import { ResourceState } from '../components/Feedback';
import { ExportPanel } from '../components/ExportPanel';
export function Audit() {
  const { organization } = useWorkspace();
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [end, setEnd] = useState(() => new Date().toISOString());
  const start = new Date(Date.parse(end) - 7 * 86400000).toISOString();
  const [page, setPage] = useState<string | null>(null);
  const initial = `organizations/${organization!.id}/audit-logs/?${new URLSearchParams({ start, end })}`;
  const resource = useResource<Page<AuditEvent>>(page || initial);
  const rows = (resource.data?.results || []).filter((row) =>
    `${row.action} ${row.actor_id} ${row.target_id}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <PageHeading
        eyebrow="OBSERVABILITY / AUDIT"
        title="Nothing important, unexplained."
        description="Last seven days · organization-wide, across all environments · UTC"
      />
      <div className="toolbar">
        <input
          aria-label="Search this audit page"
          placeholder="Search this page…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button
          className="button"
          onClick={() => {
            setSelected(null);
            setPage(null);
            setEnd(new Date().toISOString());
          }}
        >
          Refresh
        </button>
      </div>
      <ResourceState resource={resource} />
      <section className="panel">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Event</th>
                <th>Resource</th>
                <th>Actor</th>
                <th>Outcome</th>
                <th>Time (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <button className="text-button" onClick={() => setSelected(row)}>
                      {row.action}
                    </button>
                  </td>
                  <td>
                    {row.target_type}
                    <small className="cell-detail mono">{row.target_id || '—'}</small>
                  </td>
                  <td className="mono">{row.actor_id || 'System'}</td>
                  <td>
                    <Status value={row.outcome} />
                  </td>
                  <td>{row.created_at.replace('T', ' ').slice(0, 19)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!resource.loading && !resource.error && !rows.length && (
          <EmptyState title="No matching audit events.">
            Events appear when changes are recorded in your organization.
          </EmptyState>
        )}
      </section>
      <div className="detail-links">
        <button
          className="button"
          disabled={!resource.data?.previous}
          onClick={() => {
            setSelected(null);
            setPage(resource.data!.previous);
          }}
        >
          Previous
        </button>
        <button
          className="button"
          disabled={!resource.data?.next}
          onClick={() => {
            setSelected(null);
            setPage(resource.data!.next);
          }}
        >
          Next
        </button>
      </div>
      {selected && (
        <section className="panel audit-detail">
          <div className="panel-heading">
            <h2>Event details</h2>
            <button className="button" onClick={() => setSelected(null)}>
              Close details
            </button>
          </div>
          <p>{selected.action}</p>
          <p className="mono">Request: {selected.request_id || '—'}</p>
          <pre className="audit-json">{JSON.stringify(selected.changes, null, 2)}</pre>
        </section>
      )}
      <ExportPanel kind="audit-logs" filters={{ start, end }} />
    </>
  );
}
