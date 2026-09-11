import { Link } from 'react-router';
import { ApiError } from '../lib/api';
export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const known = error instanceof ApiError;
  return (
    <div className="form-feedback" role="alert">
      <p>{error instanceof Error ? error.message : 'Something went wrong. Please try again.'}</p>
      {known &&
        Object.entries(error.details).map(([name, messages]) => (
          <p key={name}>
            {name.replaceAll('_', ' ')}:{' '}
            {Array.isArray(messages) ? messages.join(' ') : String(messages)}
          </p>
        ))}
      {known && error.retryAfter && <p>Try again after {error.retryAfter} seconds.</p>}
      {known && error.requestId && <p className="small">Support request: {error.requestId}</p>}
      {known && (error.code.includes('recent') || error.code.includes('reauth')) && (
        <Link to="/login">Sign in again to confirm your identity</Link>
      )}
    </div>
  );
}
export function ResourceState({
  resource,
}: {
  resource: { loading: boolean; error: unknown; reload: () => void };
}) {
  if (resource.loading)
    return (
      <p role="status" className="security-note">
        Loading from DevVault…
      </p>
    );
  if (resource.error)
    return (
      <div>
        <ErrorMessage error={resource.error} />
        <button className="button" onClick={resource.reload}>
          Try again
        </button>
      </div>
    );
  return null;
}
