import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { useWorkspace } from '../lib/workspace';
import { mutate } from '../lib/api';
import { useResource } from '../lib/data';
import type { Credential, Permission } from '../lib/data';
import {
  CopyButton,
  CreateButton,
  EmptyState,
  FormDialog,
  PageHeading,
  Status,
} from '../components/ui';
import { ResourceState } from '../components/Feedback';

export function Credentials() {
  const store = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(params.has('create'));
  const [revoking, setRevoking] = useState<Credential | null>(null);
  const [secret, setSecret] = useState('');
  const [message, setMessage] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const resource = useResource<Credential[]>(
    store.activeEnvironment ? `environments/${store.activeEnvironment.id}/keys/` : null,
    true,
  );
  const permissions = useResource<Permission[]>(
    store.service ? `services/${store.service.id}/permissions/` : null,
    true,
  );
  const keys = (resource.data || []).filter(
    (k) =>
      (!store.service || k.service_id === store.service.id) &&
      k.name.toLowerCase().includes(search.toLowerCase()) &&
      (status === 'all' || k.status === status),
  );
  function close() {
    setCreating(false);
    setParams({});
  }
  return (
    <>
      <PageHeading
        eyebrow="ACCESS / CREDENTIALS"
        title="Keys with clear boundaries."
        description={
          store.service
            ? `${store.service.name} · ${store.environment} environment`
            : 'Create a project and API service before issuing keys.'
        }
        action={
          store.service && (
            <CreateButton onClick={() => setCreating(true)}>Create API key</CreateButton>
          )
        }
      />
      <div className="security-note">
        Real secrets are shown once. Store them securely; metadata cannot recover the original
        value.
      </div>
      <div className="toolbar">
        <input
          aria-label="Search API keys"
          placeholder="Find a key…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Filter key status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="revoked">Revoked</option>
        </select>
      </div>
      <ResourceState resource={resource} />
      <ResourceState resource={permissions} />
      {message && (
        <p role="status" className="inline-success">
          {message}
        </p>
      )}
      {secret && (
        <section className="secret-panel" aria-label="New credential">
          <strong>Save your API key now</strong>
          <p>
            This value will disappear when you leave this view or hide it. Never put it in your
            frontend bundle.
          </p>
          <code>{secret}</code>
          <div className="detail-links">
            <CopyButton value={secret} label="Copy API key" />
            <button className="button" onClick={() => setSecret('')}>
              I’ve saved it — hide value
            </button>
          </div>
        </section>
      )}
      {!resource.loading && !resource.error && (
        <section className="panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Key name</th>
                  <th>Credential</th>
                  <th>Status</th>
                  <th>Expires</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id}>
                    <td>{k.name}</td>
                    <td className="mono">
                      {k.display_prefix}••••{k.last_four}
                    </td>
                    <td>
                      <Status value={k.status} />
                    </td>
                    <td>{k.expires_at ? new Date(k.expires_at).toLocaleString() : 'No expiry'}</td>
                    <td>
                      {k.status === 'active' && (
                        <button
                          className="text-button danger"
                          aria-label={`Revoke ${k.name}`}
                          onClick={() => setRevoking(k)}
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!keys.length && (
            <EmptyState title="No matching credentials.">
              Issue a key for the selected service to get started.
            </EmptyState>
          )}
        </section>
      )}
      {creating && store.service && !permissions.loading && !permissions.error && (
        <FormDialog
          title="Create an API key"
          description={`Issue a real ${store.environment} key for ${store.service.name}. Select only required scopes. No selections means authentication-only access.`}
          fields={[
            { name: 'name', label: 'Key name' },
            {
              name: 'permission_ids',
              label: 'Permissions',
              type: 'multiselect',
              optional: true,
              options: (permissions.data || [])
                .filter((p) => p.is_active)
                .map((p) => ({ value: p.id, label: p.name })),
              hint: 'Use Ctrl/Cmd to select multiple permissions.',
            },
          ]}
          onClose={close}
          onSubmit={async (v, key) => {
            const result = await mutate<Credential>(
              `environments/${store.activeEnvironment!.id}/keys/`,
              {
                name: v.name,
                service_id: store.service!.id,
                permission_ids: v.permission_ids ? v.permission_ids.split(',') : [],
              },
              key,
            );
            close();
            setSecret(result.data.secret || '');
            if (!result.data.secret)
              setMessage(
                'This operation already completed. Its secret cannot be recovered. Revoke this key and create another if you did not save it.',
              );
            resource.reload();
          }}
        />
      )}
      {revoking && (
        <FormDialog
          title="Revoke this API key?"
          description={`${revoking.name} will no longer authorize requests. This changes the real backend.`}
          fields={[]}
          submitLabel="Revoke key"
          onClose={() => setRevoking(null)}
          onSubmit={async () => {
            await mutate(`keys/${revoking.id}/revoke/`, { confirm: true, reason: 'revoked' });
            setRevoking(null);
            setSecret('');
            setMessage('Credential revoked.');
            resource.reload();
          }}
        />
      )}
    </>
  );
}
