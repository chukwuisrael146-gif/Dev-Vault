import { useState } from 'react';
import { useWorkspace } from '../lib/workspace';
import { mutate } from '../lib/api';
import { useResource } from '../lib/data';
import type { Policy } from '../lib/data';
import { CreateButton, EmptyState, FormDialog, PageHeading, Status } from '../components/ui';
import { ResourceState } from '../components/Feedback';
const names: Record<string, string> = {
  fixed_window: 'Fixed window',
  token_bucket: 'Token bucket',
  daily: 'Daily quota',
  monthly: 'Monthly quota',
};
export function Policies() {
  const store = useWorkspace();
  const [create, setCreate] = useState(false);
  const [toggle, setToggle] = useState<Policy | null>(null);
  const resource = useResource<Policy[]>(`organizations/${store.organization!.id}/policies/`, true);
  const policies = (resource.data || []).filter((p) => p.environment_kind === store.environment);
  return (
    <>
      <PageHeading
        eyebrow="ACCESS / POLICIES"
        title="Define the limits. Keep the trust."
        description={`Organization policies · ${store.environment} environment. All applicable policies must allow access.`}
        action={
          store.service && <CreateButton onClick={() => setCreate(true)}>New policy</CreateButton>
        }
      />
      <ResourceState resource={resource} />
      <div className="policy-list">
        {policies.map((p) => (
          <article className="policy-row" key={p.id}>
            <div className="policy-name">
              <span className="eyebrow">
                {names[p.algorithm]} / VERSION {p.version}
              </span>
              <h2>{p.name}</h2>
              <span className="muted small">
                {p.dimension === 'key' ? 'Per key family' : 'Shared budget'} ·{' '}
                {p.service_id ? 'Service' : p.project_id ? 'Project' : 'Organization'}
              </span>
            </div>
            <div className="policy-limit">
              <strong>{(p.config.limit ?? p.config.capacity).toLocaleString()}</strong>
              <span>
                {p.algorithm === 'daily'
                  ? 'units / day'
                  : p.algorithm === 'monthly'
                    ? 'units / month'
                    : p.algorithm === 'token_bucket'
                      ? `refill ${p.config.refill_tokens} / ${p.config.refill_seconds}s`
                      : `requests / ${p.config.window_seconds}s`}
              </span>
            </div>
            <Status value={p.is_active ? 'active' : 'paused'} />
            <button className="button" onClick={() => setToggle(p)}>
              {p.is_active ? 'Pause' : 'Enable'}
            </button>
          </article>
        ))}
      </div>
      {!resource.loading && !resource.error && !policies.length && (
        <EmptyState title="No policies in this environment.">
          Add a boundary to the selected API service.
        </EmptyState>
      )}
      {create && (
        <FormDialog
          title="Create an access policy"
          description={`Apply a policy to ${store.service!.name}. Token buckets refill the configured capacity every 60 seconds; fixed windows also use 60 seconds.`}
          fields={[
            { name: 'name', label: 'Policy name' },
            {
              name: 'algorithm',
              label: 'Policy family',
              options: Object.entries(names).map(([value, label]) => ({ value, label })),
            },
            {
              name: 'dimension',
              label: 'Budget dimension',
              options: [
                { value: 'key', label: 'Per key family' },
                { value: 'shared', label: 'Shared service budget' },
              ],
            },
            {
              name: 'limit',
              label: 'Limit / capacity',
              type: 'number',
              min: 1,
              max: 1000000000,
              value: '1000',
            },
          ]}
          onClose={() => setCreate(false)}
          onSubmit={async (v, key) => {
            const limit = Number(v.limit);
            const config =
              v.algorithm === 'fixed_window'
                ? { limit, window_seconds: 60 }
                : v.algorithm === 'token_bucket'
                  ? { capacity: limit, refill_tokens: limit, refill_seconds: 60 }
                  : { limit };
            await mutate(
              `organizations/${store.organization!.id}/policies/`,
              {
                name: v.name,
                algorithm: v.algorithm,
                dimension: v.dimension,
                config,
                environment_kind: store.environment,
                service_id: store.service!.id,
              },
              key,
            );
            setCreate(false);
            resource.reload();
          }}
        />
      )}
      {toggle && (
        <FormDialog
          title="Change policy state?"
          description="This affects real access decisions. A conflicting update requires reloading the policy list."
          fields={[]}
          submitLabel="Confirm policy change"
          onClose={() => {
            setToggle(null);
            resource.reload();
          }}
          onSubmit={async () => {
            await mutate(
              `policies/${toggle.id}/`,
              { confirm: true, expected_version: toggle.version, is_active: !toggle.is_active },
              undefined,
              'PATCH',
            );
            setToggle(null);
            resource.reload();
          }}
        />
      )}
    </>
  );
}
