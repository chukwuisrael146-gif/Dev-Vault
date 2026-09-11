import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router';
import { api } from '../lib/api';
import { Brand } from '../components/ui';
import { ErrorMessage } from '../components/Feedback';
export function Verification() {
  const [message, setMessage] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>, resend: boolean) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    setBusy(true);
    setMessage('');
    setError(null);
    try {
      const result = await api<{ message: string }>(
        resend ? 'auth/resend-verification/' : 'auth/verify-email/',
        { method: 'POST', body, public: true },
      );
      form.reset();
      setMessage(result.message);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="public-page">
      <header className="public-header">
        <Link to="/" aria-label="DevVault home">
          <Brand />
        </Link>
        <Link to="/login">Sign in</Link>
      </header>
      <main id="main" className="verification-panel auth-form-panel">
        <h1>Verify your email.</h1>
        <p>
          Use the confirmation link in your email, or paste its token below. Opening this page never
          consumes a token.
        </p>
        <form onSubmit={(event) => submit(event, false)}>
          <label className="field">
            Verification token
            <input name="token" type="password" autoComplete="off" required maxLength={256} />
          </label>
          <button className="button primary" disabled={busy}>
            Verify email
          </button>
        </form>
        <h2>Need another email?</h2>
        <form onSubmit={(event) => submit(event, true)}>
          <label className="field">
            Work email
            <input name="email" type="email" autoComplete="email" required />
          </label>
          <button className="button" disabled={busy}>
            Resend verification email
          </button>
        </form>
        <ErrorMessage error={error} />
        {message && (
          <p role="status" className="inline-success">
            {message}
          </p>
        )}
      </main>
    </div>
  );
}
