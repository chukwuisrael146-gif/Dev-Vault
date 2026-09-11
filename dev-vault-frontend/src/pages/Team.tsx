import { useState } from 'react';
import { useWorkspace } from '../lib/workspace';
import { mutate } from '../lib/api';
import { useResource } from '../lib/data';
import type { Member, Invitation } from '../lib/data';
import { CreateButton, FormDialog, PageHeading, Status } from '../components/ui';
import { ResourceState } from '../components/Feedback';
export function Team() {
  const { organization } = useWorkspace();
  const [invite, setInvite] = useState(false);
  const [message, setMessage] = useState('');
  const base = `organizations/${organization!.id}`;
  const members = useResource<Member[]>(base + '/members/', true);
  const invitations = useResource<Invitation[]>(base + '/invitations/', true);
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE / PEOPLE"
        title="The right access, for each person."
        description="Organization-wide membership. Django enforces every role independently of this screen."
        action={<CreateButton onClick={() => setInvite(true)}>Invite member</CreateButton>}
      />
      <ResourceState resource={members} />
      {message && (
        <p role="status" className="inline-success">
          {message}
        </p>
      )}
      <section className="panel">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {members.data?.map((m) => (
                <tr key={m.id}>
                  <td>{m.email}</td>
                  <td>{m.role}</td>
                  <td>
                    <Status value={m.is_active ? 'active' : 'disabled'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel project-detail">
        <div className="panel-heading">
          <h2>Invitations</h2>
        </div>
        <ResourceState resource={invitations} />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {invitations.data?.map((i) => (
                <tr key={i.id}>
                  <td>{i.email}</td>
                  <td>{i.role}</td>
                  <td>
                    {i.accepted_at
                      ? 'Accepted'
                      : i.revoked_at
                        ? 'Revoked'
                        : Date.parse(i.expires_at) < Date.now()
                          ? 'Expired'
                          : 'Pending'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {invitations.data?.length === 0 && <p className="muted">No invitations yet.</p>}
      </section>
      {invite && (
        <FormDialog
          title="Invite a teammate"
          description="An invitation email will be queued by your backend. Delivery requires the configured mail worker."
          fields={[
            { name: 'email', label: 'Work email', type: 'email' },
            { name: 'role', label: 'Role', options: ['developer', 'admin', 'analyst', 'billing'] },
          ]}
          submitLabel="Send invitation"
          onClose={() => setInvite(false)}
          onSubmit={async (v, key) => {
            await mutate(base + '/invitations/', v, key);
            setInvite(false);
            setMessage('Invitation saved and queued for delivery.');
            invitations.reload();
          }}
        />
      )}
    </>
  );
}
