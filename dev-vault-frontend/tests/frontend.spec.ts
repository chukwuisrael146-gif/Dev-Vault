import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { setupApi, signIn } from './mock-api';

test('protected pages require sign-in and reloading clears the in-memory session', async ({
  page,
}) => {
  await setupApi(page);
  await page.goto('/workspace');
  await expect(page).toHaveURL(/login/);
  await signIn(page);
  await expect(page.getByLabel('Organization', { exact: true }).first()).toHaveValue('org1');
  expect(
    await page.evaluate(() => ({
      local: Object.keys(localStorage),
      session: Object.keys(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] });
  await page.reload();
  await expect(page).toHaveURL(/login/);
});
test('all workspace destinations use API data without runtime errors', async ({ page }) => {
  await setupApi(page);
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await signIn(page);
  for (const label of [
    'Projects',
    'API keys',
    'Access policies',
    'Usage & analytics',
    'Audit log',
    'Team members',
    'Webhooks',
    'Settings',
    'Overview',
  ]) {
    await page
      .getByRole('navigation', { name: 'Workspace', exact: true })
      .getByRole('link', { name: label, exact: true })
      .click();
    await expect(page.locator('main h1')).toBeVisible();
    await expect(page.locator('video')).toHaveCount(1);
  }
  expect(errors).toEqual([]);
});
test('project creation uses the real contract and a per-operation idempotency key', async ({
  page,
}) => {
  const state = await setupApi(page);
  await signIn(page);
  await page.getByRole('link', { name: 'Projects', exact: true }).click();
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByLabel('Project name').fill('Payments API');
  await page.getByLabel('Project slug').fill('payments-api');
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Payments API', exact: true }).first(),
  ).toBeVisible();
  const write = state.writes.find((w) => w.path.endsWith('/projects/'))!;
  expect(write.body).toEqual({ name: 'Payments API', slug: 'payments-api' });
  expect(write.key).toMatch(/^[a-f0-9-]{36}$/);
});
test('key creation shows the server secret once and revocation is confirmed', async ({ page }) => {
  const state = await setupApi(page);
  await signIn(page);
  await page.getByRole('link', { name: 'API keys', exact: true }).click();
  await page.getByRole('button', { name: 'Create API key' }).click();
  await page.getByLabel('Key name').fill('Browser key');
  await page.getByLabel('Permissions', { exact: true }).selectOption(['permission1']);
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(page.locator('.secret-panel code')).toHaveText('test-only-one-time-secret');
  await page.getByRole('button', { name: 'I’ve saved it — hide value' }).click();
  await expect(page.locator('.secret-panel')).toHaveCount(0);
  await page.getByRole('button', { name: 'Revoke Browser key', exact: true }).click();
  await page.getByRole('button', { name: 'Revoke key', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: 'Browser key' })).toContainText('revoked');
  expect(state.writes.find((w) => w.path.endsWith('/keys/'))?.body).toEqual({
    name: 'Browser key',
    service_id: 'service1',
    permission_ids: ['permission1'],
  });
});
test('stale policy edits display the backend conflict without a false success', async ({
  page,
}) => {
  const state = await setupApi(page);
  state.policyConflict = true;
  await signIn(page);
  await page.getByRole('link', { name: 'Access policies', exact: true }).click();
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm policy change' }).click();
  await expect(page.getByRole('alert')).toContainText('Reload before editing');
  expect(state.policies[0].is_active).toBe(true);
});
test('registration submits confirmation and exposes field errors', async ({ page }) => {
  await setupApi(page);
  await page.goto('/register');
  await page.getByLabel('Work email').fill('new@example.com');
  await page.getByLabel('Password', { exact: true }).fill('One-password');
  await page.getByLabel('Confirm password').fill('Other-password');
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('alert')).toContainText('The passwords do not match');
});
test('simultaneous expired requests rotate the refresh token only once', async ({ page }) => {
  const state = await setupApi(page);
  await signIn(page);
  await expect(page.getByLabel('API service')).toHaveValue('service1');
  state.expired = true;
  await page.getByRole('link', { name: 'API keys', exact: true }).click();
  await expect(page.getByRole('cell', { name: 'Existing key', exact: true })).toBeVisible();
  expect(state.refreshes).toBe(1);
});
test('logout revokes the refresh session and protects workspace routes', async ({ page }) => {
  const state = await setupApi(page);
  await signIn(page);
  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/login/);
  expect(state.writes.find((w) => w.path === 'auth/logout/')?.body).toEqual({
    refresh_token: 'refresh-old',
  });
});

test('foreign pagination links never receive dashboard credentials', async ({ page }) => {
  await setupApi(page);
  let contactedForeignHost = false;
  await page.route('https://untrusted.example/**', async (route) => {
    contactedForeignHost = true;
    await route.abort();
  });
  await page.route('**/api/v1/organizations/org1/projects/', async (route) => {
    await route.fulfill({
      json: { results: [], previous: null, next: 'https://untrusted.example/api/v1/projects/' },
    });
  });
  await signIn(page);
  await expect(page.getByRole('alert')).toContainText('invalid API address');
  expect(contactedForeignHost).toBe(false);
});
test('invitations are queued through the backend', async ({ page }) => {
  const state = await setupApi(page);
  await signIn(page);
  await page.getByRole('link', { name: 'Team members', exact: true }).click();
  await page.getByRole('button', { name: 'Invite member' }).click();
  await page.getByLabel('Work email').fill('teammate@example.com');
  await page.getByRole('button', { name: 'Send invitation' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'queued for delivery' })).toBeVisible();
  expect(state.invitations).toHaveLength(1);
});
test('audit exports are queued and downloaded with authentication', async ({ page }) => {
  await setupApi(page);
  await signIn(page);
  await page.getByRole('link', { name: 'Audit log', exact: true }).click();
  await page.getByRole('button', { name: 'Request CSV export' }).click();
  await page.getByRole('button', { name: 'Queue export' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download CSV' }).click();
  expect((await download).suggestedFilename()).toBe('devvault-audit-logs-export1.csv');
});
test('backend outages show errors rather than fixture metrics', async ({ page }) => {
  const state = await setupApi(page);
  await signIn(page);
  state.unavailable = true;
  await page.getByRole('link', { name: 'Usage & analytics', exact: true }).click();
  await expect(page.getByRole('alert').first()).toContainText('temporarily unavailable');
  await expect(page.locator('main')).not.toContainText('133,189');
});
test('mobile layout, navigation, video pause and accessibility', async ({ page }) => {
  await setupApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await page.getByRole('button', { name: 'Pause background video' }).click();
  expect(await page.locator('video').evaluate((video: HTMLVideoElement) => video.paused)).toBe(
    true,
  );
  for (const name of ['Projects', 'API keys', 'Audit log', 'Settings']) {
    await page.getByRole('button', { name: 'Open navigation' }).click();
    await page.getByRole('dialog').getByRole('link', { name, exact: true }).click();
    await expect(page.locator('main h1')).toBeVisible();
    expect(
      await page.locator('body').evaluate((body) => body.scrollWidth <= innerWidth),
      name,
    ).toBe(true);
  }
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
test('dialogs preserve keyboard focus and registration respects reduced motion', async ({
  page,
}) => {
  await setupApi(page);
  await signIn(page);
  await page.getByRole('link', { name: 'Projects', exact: true }).click();
  const button = page.getByRole('button', { name: 'New project', exact: true });
  await button.click();
  await page.keyboard.press('Escape');
  await expect(button).toBeFocused();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/register');
  expect(await page.locator('video').evaluate((video: HTMLVideoElement) => video.paused)).toBe(
    true,
  );
});
