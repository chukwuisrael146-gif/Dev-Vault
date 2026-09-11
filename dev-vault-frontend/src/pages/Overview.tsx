import { useState } from 'react';
import { Link } from 'react-router';
import { ArrowUpRight, ShieldCheck } from 'lucide-react';
import { useWorkspace } from '../lib/workspace';
import { useResource } from '../lib/data';
import type { Credential, Policy } from '../lib/data';
import { PageHeading, EmptyState } from '../components/ui';
import { ResourceState } from '../components/Feedback';
import { TrafficChart } from '../components/TrafficChart';
import { ExportPanel } from '../components/ExportPanel';
type Summary = {
  summary: { requests: number; units: number; mean_latency_ms: number | null };
  series: { hour: string; requests: number }[];
  aggregation_pending: number;
};
export function Overview({ analytics = false }: { analytics?: boolean }) {
  const store = useWorkspace();
  const [period, setPeriod] = useState('24h');
  const [now] = useState(() => new Date());
  const end = now.toISOString();
  const start = new Date(now.getTime() - (period === '7d' ? 7 : 1) * 86400000).toISOString();
  const filters = new URLSearchParams({
    start,
    end,
    granularity: period === '7d' ? 'day' : 'hour',
    ...(store.service ? { service_id: store.service.id } : {}),
  });
  const usage = useResource<{ data: Summary }>(
    store.service ? `organizations/${store.organization!.id}/usage/?${filters}` : null,
  );
  const keys = useResource<Credential[]>(
    store.activeEnvironment ? `environments/${store.activeEnvironment.id}/keys/` : null,
    true,
  );
  const policies = useResource<Policy[]>(`organizations/${store.organization!.id}/policies/`, true);
  const counts = keys.data?.filter(
    (key) => key.service_id === store.service?.id && key.status === 'active',
  ).length;
  const activePolicies = policies.data?.filter(
    (policy) => policy.environment_kind === store.environment && policy.is_active,
  ).length;
  return (
    <>
      <PageHeading
        eyebrow={analytics ? 'OBSERVABILITY / USAGE' : 'YOUR WORKSPACE, AT A GLANCE'}
        title={analytics ? 'Every request tells a story.' : 'Your API. Under control.'}
        description={
          store.service
            ? `${store.service.name} · ${store.environment} · UTC reporting`
            : 'Create a project and API service to start measuring usage.'
        }
        action={
          <Link to="/workspace/keys?create=1" className="button primary">
            Create API key
            <ArrowUpRight size={16} />
          </Link>
        }
      />
      <div className="overview-meta">
        <span>{store.organization!.name}</span>
        <div className="period-control" aria-label="Report period">
          {['24h', '7d'].map((value) => (
            <button key={value} aria-pressed={period === value} onClick={() => setPeriod(value)}>
              {value === '24h' ? 'Last 24 hours' : 'Last 7 days'}
            </button>
          ))}
        </div>
      </div>
      <ResourceState resource={usage} />
      <ResourceState resource={keys} />
      <ResourceState resource={policies} />
      <section className="metric-strip" aria-label="Workspace metrics">
        <div>
          <span>Total requests</span>
          <strong>{usage.data ? usage.data.data.summary.requests.toLocaleString() : '—'}</strong>
          <small>Selected service and report period</small>
        </div>
        <div>
          <span>Active API keys</span>
          <strong>{counts ?? '—'}</strong>
          <small>Selected service</small>
        </div>
        <div>
          <span>Access policies</span>
          <strong>{activePolicies ?? '—'}</strong>
          <small>All active {store.environment} organization policies</small>
        </div>
      </section>
      <div className="overview-grid">
        <section className="panel traffic-panel">
          <div className="panel-heading">
            <div>
              <h2>Request activity</h2>
              <p>Durable events recorded by your backend</p>
            </div>
            <button className="button" onClick={usage.reload}>
              Refresh
            </button>
          </div>
          {usage.data?.data.series.length ? (
            <TrafficChart series={usage.data.data.series} />
          ) : (
            !usage.loading &&
            !usage.error && (
              <EmptyState title="No traffic recorded.">
                Requests appear after your trusted server uses the verification endpoint.
              </EmptyState>
            )
          )}
        </section>
        <section className="posture-panel">
          <div className="panel-heading">
            <h2>Usage facts</h2>
            <ShieldCheck size={19} />
          </div>
          <h3>Boundaries by design.</h3>
          <p>Every applicable policy must allow a request.</p>
          <ul>
            <li>
              <span>Consumed units</span>
              <span>{usage.data?.data.summary.units ?? '—'}</span>
            </li>
            <li>
              <span>Awaiting aggregation</span>
              <span>{usage.data?.data.aggregation_pending ?? '—'}</span>
            </li>
          </ul>
          <Link to="/workspace/policies">Review access policies →</Link>
        </section>
      </div>
      {analytics && store.service && (
        <ExportPanel kind="usage" filters={{ start, end, service_id: store.service.id }} />
      )}
      <div className="bottom-guide">
        <span className="guide-number">01 /</span>
        <span>
          <strong>Connect your protected API.</strong>
          <small>Service verification runs on your trusted server, never in this browser.</small>
        </span>
        <Link className="button" to="/workspace/integration">
          Read the guide
        </Link>
      </div>
    </>
  );
}
