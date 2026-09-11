import { useState } from 'react';
import { useWorkspace } from '../lib/workspace';
import { api, downloadBlob, mutate } from '../lib/api';
import type { ExportJob } from '../lib/data';
import { useResource } from '../lib/data';
import { ErrorMessage, ResourceState } from './Feedback';
import { FormDialog } from './ui';
export function ExportPanel({
  kind,
  filters,
}: {
  kind: 'usage' | 'audit-logs';
  filters: Record<string, string>;
}) {
  const { organization } = useWorkspace();
  const base = `organizations/${organization!.id}/${kind}/exports/`;
  const jobs = useResource<ExportJob[]>(base, true);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function download(job: ExportJob) {
    setBusy(true);
    setError(null);
    try {
      downloadBlob(
        await api<Blob>(base + job.id + '/download/', { blob: true }),
        `devvault-${kind}-${job.id}.csv`,
      );
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel project-detail">
      <div className="panel-heading">
        <div>
          <h2>CSV exports</h2>
          <p>
            Queued exports require a running background worker. Downloads expire after 24 hours.
          </p>
        </div>
        <button className="button" onClick={() => setConfirm(true)}>
          Request CSV export
        </button>
      </div>
      <ResourceState resource={jobs} />
      <ErrorMessage error={error} />
      <button className="button" onClick={jobs.reload}>
        Check export status
      </button>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Export</th>
              <th>Status</th>
              <th>Rows</th>
              <th>Download</th>
            </tr>
          </thead>
          <tbody>
            {jobs.data?.map((job) => (
              <tr key={job.id}>
                <td className="mono">{job.id.slice(0, 8)}</td>
                <td>
                  {job.status}
                  {job.failure_code ? `: ${job.failure_code}` : ''}
                </td>
                <td>{job.row_count}</td>
                <td>
                  <button
                    className="button"
                    disabled={
                      busy || job.status !== 'ready' || Date.parse(job.expires_at) < Date.now()
                    }
                    onClick={() => download(job)}
                  >
                    Download CSV
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {confirm && (
        <FormDialog
          title="Request CSV export?"
          description={`Export ${kind} records for the selected report range. Files contain private workspace data.`}
          fields={[]}
          submitLabel="Queue export"
          onClose={() => setConfirm(false)}
          onSubmit={async (_, key) => {
            await mutate(base, filters, key);
            setConfirm(false);
            jobs.reload();
          }}
        />
      )}
    </section>
  );
}
