import { useEffect, useState, useSyncExternalStore } from 'react';
import { api, listAll, sessionStore } from './api';
export function useSession() {
  return useSyncExternalStore(sessionStore.subscribe, sessionStore.get);
}
export function useResource<T>(path: string | null, collection = false) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{
    key: string | null;
    data: T | null;
    error: unknown;
    loading: boolean;
  }>({ key: null, data: null, error: null, loading: false });
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setState({ key: path, data: null, error: null, loading: true });
    const task = collection
      ? (listAll(path, controller.signal) as Promise<T>)
      : api<T>(path, { signal: controller.signal });
    task
      .then((data) => {
        if (!controller.signal.aborted) setState({ key: path, data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ key: path, data: null, error, loading: false });
      });
    return () => controller.abort();
  }, [path, revision, collection]);
  return {
    data: state.key === path ? state.data : null,
    error: state.key === path ? state.error : null,
    loading: !!path && (state.key !== path || state.loading),
    reload: () => setRevision((value) => value + 1),
  };
}
export type Organization = { id: string; name: string; slug: string; status: string };
export type Project = { id: string; name: string; slug: string; archived_at: string | null };
export type Environment = { id: string; kind: 'test' | 'live'; is_active: boolean };
export type Service = {
  id: string;
  name: string;
  slug: string;
  audience: string;
  is_active: boolean;
};
export type Credential = {
  id: string;
  service_id: string;
  name: string;
  display_prefix: string;
  last_four: string;
  status: string;
  expires_at: string | null;
  secret?: string;
};
export type Permission = { id: string; name: string; is_active: boolean };
export type Policy = {
  id: string;
  name: string;
  environment_kind: string;
  algorithm: string;
  dimension: string;
  config: Record<string, number>;
  version: number;
  is_active: boolean;
  project_id: string | null;
  service_id: string | null;
};
export type Member = {
  id: string;
  user_id: string;
  email: string;
  role: string;
  is_active: boolean;
};
export type Invitation = {
  id: string;
  email: string;
  role: string;
  accepted_at: string | null;
  revoked_at: string | null;
  expires_at: string;
};
export type Webhook = {
  id: string;
  url: string;
  event_types: string[];
  is_active: boolean;
  secret?: string;
  delivery_enabled?: boolean;
};
export type AuditEvent = {
  id: string;
  action: string;
  actor_id: string | null;
  target_id: string | null;
  target_type: string;
  outcome: string;
  created_at: string;
  request_id: string;
  changes: Record<string, unknown>;
};
export type ExportJob = {
  id: string;
  status: string;
  row_count: number;
  failure_code: string | null;
  expires_at: string;
};
