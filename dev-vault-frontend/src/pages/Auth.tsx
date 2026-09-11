import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { ArrowLeft, ArrowUpRight, Eye, EyeOff } from 'lucide-react';
import { Brand } from '../components/ui';
import { api, login } from '../lib/api';
import { ErrorMessage } from '../components/Feedback';

export function Auth({ mode }: { mode: 'login' | 'register' | 'reset' }) {
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const heading =
    mode === 'login'
      ? 'Welcome back.'
      : mode === 'register'
        ? 'Build on a clear boundary.'
        : 'Let’s get you back in.';
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form)) as Record<string, string>;
    setBusy(true);
    setError(null);
    setMessage('');
    try {
      if (mode === 'login') {
        await login(data.email, data.password);
        form.reset();
        navigate('/workspace');
      } else {
        const result = await api<{ message: string }>(
          mode === 'register' ? 'auth/register/' : 'auth/password-reset/',
          { method: 'POST', public: true, body: data },
        );
        form.reset();
        setMessage(result.message);
      }
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="public-page auth-page">
      <header className="public-header">
        <Link to="/" aria-label="DevVault home">
          <Brand />
        </Link>
        <Link to="/" className="text-link">
          <ArrowLeft size={15} />
          Back to home
        </Link>
      </header>
      <main id="main" className="auth-layout">
        <div className="auth-statement">
          <p className="eyebrow">API ACCESS, CONSIDERED.</p>
          <h1>
            Your next idea.
            <br />
            <span>A stronger foundation.</span>
          </h1>
          <p>
            Give your services a clear boundary.
            <br />
            Give your team a clearer picture.
          </p>
          <div className="auth-caption">PRIVATE BY DESIGN / PRECISE BY DEFAULT</div>
        </div>
        <section className="auth-form-panel">
          <p className="eyebrow">
            {mode === 'login'
              ? 'SIGN IN TO DEVVAULT'
              : mode === 'register'
                ? 'CREATE YOUR WORKSPACE'
                : 'PASSWORD RECOVERY'}
          </p>
          <h2>{heading}</h2>
          <p className="muted">
            {mode === 'reset'
              ? 'Request a secure link to reset your password.'
              : 'A quieter place to manage your access layer.'}
          </p>
          <div className="auth-preview-notice">
            Connected to DevVault. Sessions stay in this tab’s memory; reloading requires sign-in.
          </div>
          {mode === 'login' && searchParams.get('logout') === 'offline' && (
            <p className="form-error" role="alert">
              You are signed out of this tab, but the server could not confirm session revocation.
              Sign in again and revoke the session, or change your password to end all sessions.
            </p>
          )}
          <form onSubmit={submit}>
            <label className="field">
              Work email
              <input
                type="email"
                name="email"
                autoComplete="username"
                placeholder="you@example.com"
                required
                maxLength={254}
              />
            </label>
            {mode !== 'reset' && (
              <div className="field">
                <label htmlFor="auth-password">Password</label>
                <div className="password-input">
                  <input
                    id="auth-password"
                    name="password"
                    type={visible ? 'text' : 'password'}
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    placeholder="Enter your password"
                    required
                    minLength={mode === 'register' ? 8 : undefined}
                    maxLength={1024}
                  />
                  <button
                    className="icon-button"
                    type="button"
                    aria-label={visible ? 'Hide password' : 'Show password'}
                    onClick={() => setVisible(!visible)}
                  >
                    {visible ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                {mode === 'register' && (
                  <span className="small muted">Use a strong, unique password.</span>
                )}
              </div>
            )}
            {mode === 'register' && (
              <label className="field">
                Confirm password
                <input
                  name="password_confirmation"
                  type="password"
                  autoComplete="new-password"
                  required
                  maxLength={1024}
                />
              </label>
            )}
            {mode === 'login' && (
              <Link className="forgot-link" to="/reset-password">
                Forgot password?
              </Link>
            )}
            <ErrorMessage error={error} />
            <button className="button primary full-width" type="submit" disabled={busy}>
              {busy
                ? 'Please wait…'
                : mode === 'login'
                  ? 'Sign in'
                  : mode === 'register'
                    ? 'Create account'
                    : 'Send reset link'}
              <ArrowUpRight size={17} />
            </button>
            {message && (
              <p className="form-feedback" role="status">
                {message}
              </p>
            )}
          </form>
          <div className="auth-switch">
            {mode === 'login' ? (
              <>
                New to DevVault? <Link to="/register">Create an account</Link>
              </>
            ) : (
              <Link to="/login">Back to sign in</Link>
            )}
          </div>
          <Link className="button full-width" to="/verify-email">
            Verify email / resend link
            <ArrowUpRight size={16} />
          </Link>
        </section>
      </main>
      <footer className="public-footer">
        <span>One workspace. Clearer boundaries.</span>
        <span>DEVVAULT / SECURE ACCOUNT ACCESS</span>
      </footer>
    </div>
  );
}
