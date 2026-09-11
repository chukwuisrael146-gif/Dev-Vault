import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useWorkspace } from '../lib/workspace';
import { api, clearSession, logout, mutate, setUser } from '../lib/api';
import type { User } from '../lib/api';
import { useSession } from '../lib/data';
import { FormDialog, PageHeading } from '../components/ui';
import { ErrorMessage } from '../components/Feedback';
export function Settings() {
  const store = useWorkspace();
  const user = useSession()!.user;
  const navigate = useNavigate();
  const [form, setForm] = useState<'profile' | 'password' | 'organization' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function signOut() {
    setBusy(true);
    try {
      await logout();
      navigate('/login');
    } catch {
      navigate('/login?logout=offline');
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE / SETTINGS"
        title="A considered workspace."
        description="Your real account and organization settings."
      />
      <section className="settings-section">
        <div>
          <h2>Organization</h2>
          <p>Selected workspace</p>
        </div>
        <div>
          <h3>{store.organization!.name}</h3>
          <p className="muted">/{store.organization!.slug}</p>
          <button className="button" onClick={() => setForm('organization')}>
            Rename organization
          </button>
        </div>
      </section>
      <section className="settings-section">
        <div>
          <h2>Account</h2>
          <p>{user.email}</p>
        </div>
        <div>
          <p>
            {[user.first_name, user.last_name].filter(Boolean).join(' ') || 'No profile name set'}
          </p>
          <div className="detail-links">
            <button className="button" onClick={() => setForm('profile')}>
              Edit profile
            </button>
            <button className="button" onClick={() => setForm('password')}>
              Change password
            </button>
            <button className="button" onClick={signOut} disabled={busy}>
              {busy ? 'Signing out…' : 'Sign out'}
            </button>
          </div>
          <ErrorMessage error={error} />
        </div>
      </section>
      <section className="settings-section">
        <div>
          <h2>Session privacy</h2>
        </div>
        <p>
          Tokens are kept in this tab’s memory, not browser storage. Reloading or closing the tab
          requires sign-in. Logout revokes the server session when the backend is reachable.
          Password changes revoke all sessions.
        </p>
      </section>
      <section className="settings-section">
        <div>
          <h2>Motion & accessibility</h2>
        </div>
        <p>
          Use the motion button to pause or resume the video. Reduced-motion preferences start
          playback paused. Only that preference is remembered in your browser.
        </p>
      </section>
      {form === 'profile' && (
        <FormDialog
          title="Edit profile"
          description="Only your first and last name are changed."
          fields={[
            { name: 'first_name', label: 'First name', value: user.first_name, optional: true },
            { name: 'last_name', label: 'Last name', value: user.last_name, optional: true },
          ]}
          submitLabel="Save profile"
          onClose={() => setForm(null)}
          onSubmit={async (v) => {
            const result = await api<{ data: { user: User } }>('me/', { method: 'PATCH', body: v });
            setUser(result.data.user);
            setForm(null);
          }}
        />
      )}
      {form === 'organization' && (
        <FormDialog
          title="Rename organization"
          description="The organization slug does not change."
          fields={[{ name: 'name', label: 'Organization name', value: store.organization!.name }]}
          submitLabel="Save name"
          onClose={() => setForm(null)}
          onSubmit={async (v) => {
            await mutate(`organizations/${store.organization!.id}/`, v, undefined, 'PATCH');
            setForm(null);
            store.organizations.reload();
          }}
        />
      )}
      {form === 'password' && (
        <FormDialog
          title="Change password"
          description="All existing sessions will be revoked. Sign in again after saving."
          fields={[
            { name: 'current_password', label: 'Current password', type: 'password' },
            { name: 'new_password', label: 'New password', type: 'password' },
            { name: 'password_confirmation', label: 'Confirm new password', type: 'password' },
          ]}
          submitLabel="Change password"
          onClose={() => {
            setError(null);
            setForm(null);
          }}
          onSubmit={async (v) => {
            await api('me/password/', { method: 'POST', body: v });
            clearSession();
            navigate('/login');
          }}
        />
      )}
    </>
  );
}
