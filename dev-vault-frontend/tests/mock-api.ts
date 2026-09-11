import type { Page } from '@playwright/test';
export async function setupApi(page: Page) {
  const state = {
    organizations: [
      { id: 'org1', name: 'Connected organization', slug: 'connected', status: 'active' },
    ],
    projects: [{ id: 'project1', name: 'Commerce API', slug: 'commerce', archived_at: null }],
    services: [
      {
        id: 'service1',
        name: 'Orders API',
        slug: 'orders',
        audience: 'orders-api',
        is_active: true,
      },
    ],
    keys: [
      {
        id: 'key1',
        service_id: 'service1',
        name: 'Existing key',
        display_prefix: 'dv_test_',
        last_four: 'abcd',
        status: 'active',
        expires_at: null,
      },
    ],
    policies: [
      {
        id: 'policy1',
        name: 'Daily budget',
        environment_kind: 'test',
        algorithm: 'daily',
        dimension: 'shared',
        config: { limit: 500 },
        version: 1,
        is_active: true,
        project_id: null,
        service_id: 'service1',
      },
    ],
    invitations: [] as Record<string, unknown>[],
    jobs: [] as Record<string, unknown>[],
    expired: false,
    refreshes: 0,
    policyConflict: false,
    unavailable: false,
    writes: [] as { path: string; body: Record<string, unknown>; key: string | undefined }[],
  };
  const user = {
    id: 'user1',
    email: 'owner@example.com',
    first_name: 'Owner',
    last_name: '',
    email_is_verified: true,
  };
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace('/api/v1/', '');
    const method = request.method();
    const body = request.postDataJSON() || {};
    const json = (value: unknown, status = 200) => route.fulfill({ status, json: value });
    const list = (results: unknown[]) => json({ results, next: null, previous: null });
    const error = (code: string, message: string, status = 400, details = {}) =>
      json({ error: { code, message, details, request_id: 'test-request-id' } }, status);
    if (method !== 'GET')
      state.writes.push({ path, body, key: request.headers()['idempotency-key'] });
    if (path === 'auth/login/')
      return json({ data: { access_token: 'access-old', refresh_token: 'refresh-old', user } });
    if (path === 'auth/refresh/') {
      state.refreshes += 1;
      await new Promise((resolve) => setTimeout(resolve, 100));
      return json({ data: { access_token: 'access-new', refresh_token: 'refresh-new' } });
    }
    if (path === 'auth/logout/') return route.fulfill({ status: 204 });
    if (path === 'auth/register/') {
      if (body.password !== body.password_confirmation)
        return error('validation_error', 'The request contains invalid data.', 400, {
          password_confirmation: ['The passwords do not match.'],
        });
      return json(
        { message: 'Account created successfully. Email verification is required.' },
        201,
      );
    }
    if (path.startsWith('auth/')) return json({ message: 'Request accepted.' });
    if (state.expired && request.headers().authorization === 'Bearer access-old')
      return error('invalid_token', 'Session expired.', 401);
    if (state.unavailable)
      return error('temporarily_unavailable', 'The backend is temporarily unavailable.', 503);
    if (path === 'me/') return json({ data: { user: { ...user, ...body } } });
    if (path === 'organizations/') {
      if (method === 'POST') {
        state.organizations.push({
          ...state.organizations[0],
          id: 'org2',
          name: body.name,
          slug: body.slug,
          status: 'active',
        });
        return json({ data: state.organizations.at(-1) }, 201);
      }
      return list(state.organizations);
    }
    if (/organizations\/[^/]+\/projects\/$/.test(path)) {
      if (method === 'POST') {
        const project = { id: 'project2', name: body.name, slug: body.slug, archived_at: null };
        state.projects.push(project);
        return json({ data: project }, 201);
      }
      return list(state.projects);
    }
    if (/projects\/[^/]+\/environments\/$/.test(path))
      return json({
        data: [
          { id: 'env-test', kind: 'test', is_active: true },
          { id: 'env-live', kind: 'live', is_active: true },
        ],
      });
    if (/environments\/[^/]+\/services\/$/.test(path)) {
      if (method === 'POST') {
        const service = { id: 'service2', ...body };
        state.services.push(service);
        return json({ data: service }, 201);
      }
      return list(path.includes('env-live') ? [] : state.services);
    }
    if (/services\/[^/]+\/permissions\/$/.test(path))
      return method === 'POST'
        ? json({ data: { id: 'permission2', ...body } }, 201)
        : list([{ id: 'permission1', name: 'orders:read', is_active: true }]);
    if (/environments\/[^/]+\/keys\/$/.test(path)) {
      if (method === 'POST') {
        const key = {
          id: 'key2',
          service_id: body.service_id,
          name: body.name,
          display_prefix: 'dv_test_',
          last_four: 'xyzz',
          status: 'active',
          expires_at: null,
        };
        state.keys.push(key);
        return json({ data: { ...key, secret: 'test-only-one-time-secret' } }, 201);
      }
      return list(state.keys);
    }
    if (/keys\/[^/]+\/revoke\/$/.test(path)) {
      const key = state.keys.find((key) => path.includes(key.id));
      if (key) key.status = 'revoked';
      return json({ data: key });
    }
    if (/organizations\/[^/]+\/policies\/$/.test(path)) {
      if (method === 'POST') {
        const policy = { id: 'policy2', ...body, version: 1, is_active: true };
        state.policies.push(policy);
        return json({ data: policy }, 201);
      }
      return list(state.policies);
    }
    if (/policies\/[^/]+\/$/.test(path)) {
      if (state.policyConflict)
        return error('conflict', 'This policy changed. Reload before editing.', 409);
      const policy = state.policies.find((p) => path.includes(p.id));
      if (policy) {
        policy.is_active = body.is_active;
        policy.version += 1;
      }
      return json({ data: policy });
    }
    if (path.endsWith('/members/'))
      return list([
        { id: 'member1', user_id: user.id, email: user.email, role: 'owner', is_active: true },
      ]);
    if (path.endsWith('/invitations/')) {
      if (method === 'POST') {
        const invitation = {
          id: 'invite1',
          ...body,
          accepted_at: null,
          revoked_at: null,
          expires_at: new Date(Date.now() + 86400000).toISOString(),
        };
        state.invitations.push(invitation);
        return json({ data: invitation }, 201);
      }
      return list(state.invitations);
    }
    if (path.endsWith('/webhooks/')) return list([]);
    if (path.endsWith('/usage/'))
      return json({
        data: {
          summary: { requests: 17, units: 34, mean_latency_ms: 2 },
          series: [{ hour: new Date().toISOString(), requests: 17 }],
          aggregation_pending: 0,
        },
      });
    if (path.endsWith('/audit-logs/'))
      return list([
        {
          id: 'audit1',
          action: 'key.created',
          actor_id: user.id,
          target_id: 'key1',
          target_type: 'credentials.APIKey',
          outcome: 'success',
          created_at: new Date().toISOString(),
          request_id: 'audit-request',
          changes: {},
        },
      ]);
    if (path.endsWith('/exports/')) {
      if (method === 'POST') {
        const job = {
          id: 'export1',
          status: 'ready',
          row_count: 1,
          failure_code: null,
          expires_at: new Date(Date.now() + 86400000).toISOString(),
        };
        state.jobs.push(job);
        return json({ data: job }, 202);
      }
      return list(state.jobs);
    }
    if (path.endsWith('/download/'))
      return route.fulfill({
        status: 200,
        contentType: 'text/csv',
        body: 'event_id,action\naudit1,key.created\n',
      });
    return error('not_found', 'Unknown test endpoint.', 404);
  });
  return state;
}
export async function signIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Work email').fill('owner@example.com');
  await page.getByLabel('Password', { exact: true }).fill('Fixture-only-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('heading', { name: 'Your API. Under control.' }).waitFor();
}
