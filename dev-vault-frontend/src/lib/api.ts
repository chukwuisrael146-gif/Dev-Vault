export type User = {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  email_is_verified: boolean;
};
type Pair = { access_token: string; refresh_token: string };
type Session = Pair & { user: User };
export type Page<T> = { results: T[]; next: string | null; previous: string | null };
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public requestId = '',
    public retryAfter = '',
  ) {
    super(message);
  }
}
const configuredBase = import.meta.env.VITE_API_BASE_URL || '/api/v1/';
const base = new URL(
  configuredBase.endsWith('/') ? configuredBase : configuredBase + '/',
  location.origin,
);
if (base.username || base.password || base.search || base.hash)
  throw new Error('The API base must not contain credentials, a query or a fragment.');
if (
  base.protocol !== 'https:' &&
  !(base.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname))
)
  throw new Error('The API requires HTTPS outside local development.');
let session: Session | null = null;
let epoch = 0;
let refreshPromise: Promise<void> | null = null;
const listeners = new Set<() => void>();
export const sessionStore = {
  get: () => session,
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};
function emit() {
  listeners.forEach((listener) => listener());
}
export function clearSession() {
  epoch += 1;
  session = null;
  emit();
}
export function setUser(user: User) {
  if (session) {
    session = { ...session, user };
    emit();
  }
}
function endpoint(path: string) {
  const url = new URL(path, base);
  // Never forward credentials to an off-origin pagination link.
  if (
    url.username ||
    url.password ||
    url.origin !== base.origin ||
    !url.pathname.startsWith(base.pathname)
  )
    throw new ApiError(0, 'unsafe_api_url', 'The server returned an invalid API address.');
  return url;
}
type Options = {
  method?: string;
  body?: unknown;
  public?: boolean;
  key?: string;
  signal?: AbortSignal;
  blob?: boolean;
};
async function send(path: string, options: Options, token?: string): Promise<Response> {
  const signal = options.signal
    ? AbortSignal.any([options.signal, AbortSignal.timeout(20000)])
    : AbortSignal.timeout(20000);
  try {
    return await fetch(endpoint(path), {
      method: options.method || 'GET',
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      referrerPolicy: 'no-referrer',
      signal,
      headers: {
        Accept: options.blob ? 'text/csv' : 'application/json',
        ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.key ? { 'Idempotency-Key': options.key } : {}),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch (error) {
    if (options.signal?.aborted || error instanceof ApiError) throw error;
    throw new ApiError(
      0,
      'connection_unavailable',
      options.method && options.method !== 'GET'
        ? 'The connection was interrupted. The operation may have completed. Check the resource before retrying; one-time secrets cannot be recovered.'
        : 'Cannot reach DevVault. Check that Django and Redis are running, then try again.',
    );
  }
}
async function decode<T>(response: Response, blob = false): Promise<T> {
  if (!response.ok) {
    const envelope = await response.json().catch(() => null);
    const error = envelope?.error;
    throw new ApiError(
      response.status,
      error?.code || 'request_failed',
      error?.message || `Request failed (${response.status}).`,
      error?.details || {},
      error?.request_id || '',
      response.headers.get('Retry-After') || '',
    );
  }
  if (response.status === 204) return undefined as T;
  try {
    return (await (blob ? response.blob() : response.json())) as T;
  } catch {
    throw new ApiError(
      0,
      'invalid_response',
      'DevVault returned an unreadable response. Check the resource before retrying an update.',
    );
  }
}
async function refresh() {
  if (refreshPromise) return refreshPromise;
  const original = session;
  const originalEpoch = epoch;
  if (!original) throw new ApiError(401, 'signed_out', 'Please sign in again.');
  const pending = (async () => {
    try {
      const result = await decode<{ data: Pair }>(
        await send('auth/refresh/', {
          method: 'POST',
          public: true,
          body: { refresh_token: original.refresh_token },
        }),
      );
      if (epoch !== originalEpoch) throw new ApiError(401, 'signed_out', 'The session has ended.');
      session = { ...original, ...result.data };
      emit();
    } catch (error) {
      if (epoch === originalEpoch) clearSession();
      throw error;
    }
  })();
  refreshPromise = pending;
  try {
    await pending;
  } finally {
    if (refreshPromise === pending) refreshPromise = null;
  }
}
export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const originalEpoch = epoch;
  const token = options.public ? undefined : session?.access_token;
  if (!options.public && !token) throw new ApiError(401, 'signed_out', 'Please sign in.');
  let response = await send(path, options, token);
  if (response.status === 401 && !options.public && epoch === originalEpoch && session) {
    if (session.access_token === token) await refresh();
    if (epoch !== originalEpoch || !session)
      throw new ApiError(401, 'signed_out', 'Please sign in again.');
    response = await send(path, options, session.access_token);
  }
  if (!options.public && epoch !== originalEpoch)
    throw new ApiError(401, 'signed_out', 'The session has changed.');
  if (response.status === 401 && !options.public) clearSession();
  return decode<T>(response, options.blob);
}
export async function login(email: string, password: string) {
  clearSession();
  const originalEpoch = epoch;
  const result = await api<{ data: Session }>('auth/login/', {
    method: 'POST',
    public: true,
    body: { email, password },
  });
  if (originalEpoch !== epoch) return;
  session = result.data;
  emit();
  const profile = await api<{ data: { user: User } }>('me/');
  setUser(profile.data.user);
}
export async function logout() {
  if (refreshPromise) await refreshPromise.catch(() => undefined);
  const token = session?.refresh_token;
  clearSession();
  if (token)
    await api('auth/logout/', { method: 'POST', public: true, body: { refresh_token: token } });
}
export async function listAll<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const result: T[] = [];
  let next: string | null = path;
  for (let page = 0; next && page < 20; page += 1) {
    const rows: Page<T> = await api(next, { signal });
    result.push(...rows.results);
    next = rows.next;
  }
  if (next)
    throw new ApiError(
      0,
      'collection_limit',
      'This collection is too large for this view. Narrow its scope.',
    );
  return result;
}
export function mutate<T>(
  path: string,
  body: unknown,
  key: string = crypto.randomUUID(),
  method = 'POST',
) {
  return api<{ data: T }>(path, { method, body, key });
}
export function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
