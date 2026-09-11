import { useState } from 'react';
import { useWorkspace } from '../lib/workspace';
import { mutate } from '../lib/api';
import { useResource } from '../lib/data';
import type { Webhook } from '../lib/data';
import { CopyButton, CreateButton, FormDialog, PageHeading, Status } from '../components/ui';
import { ResourceState } from '../components/Feedback';
export function Webhooks() {
  const { organization } = useWorkspace();
  const base = `organizations/${organization!.id}/webhooks/`;
  const resource = useResource<Webhook[]>(base, true);
  const [create, setCreate] = useState(false);
  const [changing, setChanging] = useState<Webhook | null>(null);
  const [secret, setSecret] = useState('');
  const [message, setMessage] = useState('');
  return (
    <>
      <PageHeading
        eyebrow="INTEGRATIONS / WEBHOOKS"
        title="Your systems, kept in the loop."
        description="Organization-wide endpoint configuration. Network delivery also depends on the backend delivery switch and worker."
        action={<CreateButton onClick={() => setCreate(true)}>Add endpoint</CreateButton>}
      />
      <ResourceState resource={resource} />
      {message && (
        <p role="status" className="inline-success">
          {message}
        </p>
      )}
      {secret && (
        <section className="secret-panel">
          <strong>Save this signing secret now</strong>
          <p>It will not be shown again. Store it only on your receiving server.</p>
          <code>{secret}</code>
          <div className="detail-links">
            <CopyButton value={secret} />
            <button className="button" onClick={() => setSecret('')}>
              Hide signing secret
            </button>
          </div>
        </section>
      )}
      <section className="panel">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Events</th>
                <th>Configured state</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {resource.data?.map((hook) => (
                <tr key={hook.id}>
                  <td className="mono">{hook.url}</td>
                  <td>{hook.event_types.join(', ')}</td>
                  <td>
                    <Status value={hook.is_active ? 'active' : 'paused'} />
                  </td>
                  <td>
                    <button className="button" onClick={() => setChanging(hook)}>
                      {hook.is_active ? 'Pause' : 'Enable'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {resource.data?.length === 0 && (
          <p className="empty-state">No webhook endpoints configured.</p>
        )}
      </section>
      {create && (
        <FormDialog
          title="Add a webhook endpoint"
          description="Use a public HTTPS destination that you control. The backend validates the destination; creation may enable delivery if the global switch is on."
          fields={[
            { name: 'url', label: 'Endpoint URL', type: 'url' },
            {
              name: 'event_types',
              label: 'Subscribed events',
              type: 'multiselect',
              options: ['key.created', 'key.revoked', 'policy.updated', 'quota.threshold_reached'],
            },
          ]}
          onClose={() => setCreate(false)}
          onSubmit={async (v, key) => {
            const result = await mutate<Webhook>(
              base,
              { url: v.url, event_types: v.event_types.split(',') },
              key,
            );
            setSecret(result.data.secret || '');
            setMessage(
              result.data.delivery_enabled
                ? 'Endpoint saved. Backend delivery is enabled.'
                : 'Endpoint saved. Global backend delivery is currently disabled.',
            );
            setCreate(false);
            resource.reload();
          }}
        />
      )}
      {changing && (
        <FormDialog
          title="Change webhook state?"
          description={`This changes the real endpoint ${changing.url}. Enabling it can send events when backend delivery is enabled.`}
          fields={[]}
          submitLabel="Confirm endpoint change"
          onClose={() => setChanging(null)}
          onSubmit={async () => {
            await mutate(base + changing.id + '/status/', {
              confirm: true,
              is_active: !changing.is_active,
            });
            setChanging(null);
            resource.reload();
          }}
        />
      )}
    </>
  );
}
