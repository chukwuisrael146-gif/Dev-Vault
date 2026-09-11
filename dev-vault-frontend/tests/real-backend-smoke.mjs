// Invoked by Django's isolated live_server test, never against the development database.
import { spawn } from 'node:child_process';
import { chromium, expect as baseExpect } from '@playwright/test';
const expect = baseExpect.configure({ timeout: 15000 });

const backend = process.env.DEVVAULT_E2E_BACKEND_URL;
if (!backend || !process.env.DEVVAULT_E2E_PASSWORD) {
  throw new Error('Run this through the opt-in Django browser test.');
}
if (!['127.0.0.1', 'localhost'].includes(new URL(backend).hostname))
  throw new Error('The test requires an isolated loopback Django server.');
const url = 'http://127.0.0.1:5174';
const server = spawn(
  process.execPath,
  ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5174', '--strictPort'],
  {
    env: { ...process.env, DEVVAULT_API_PROXY_TARGET: backend, VITE_API_BASE_URL: '/api/v1/' },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  },
);
let startup = '';
server.stdout.on('data', (chunk) => {
  startup += chunk.toString();
});
server.stderr.resume();
let browser;
let stage = 'starting the isolated frontend';
try {
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    if (server.exitCode !== null)
      throw new Error('The test frontend could not start; check port 5174.');
    try {
      ready =
        startup.includes('5174') && (await fetch(url, { signal: AbortSignal.timeout(500) })).ok;
    } catch {
      /* Server startup is asynchronous. */
    }
    if (ready) break;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  if (!ready) throw new Error('The test frontend did not become ready.');
  browser = await chromium.launch({ channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  page.setDefaultTimeout(15000);
  const runtimeErrors = [];
  page.on('pageerror', (error) => {
    runtimeErrors.push(error.name);
    console.error(`Browser runtime error: ${error.name}`);
  });
  page.on('response', async (response) => {
    if (response.url().includes('/audit-logs/?') && response.status() === 200) {
      const audit = await response.json().catch(() => null);
      console.log(`Audit actions: ${audit?.results?.map((row) => row.action).join(',')}`);
    }
    if (response.url().includes('/api/v1/'))
      console.log(
        `${response.request().method()} ${new URL(response.url()).pathname.split('/').filter(Boolean).at(-1)}: ${response.status()}`,
      );
    if (response.url().includes('/api/v1/') && response.status() >= 400) {
      const body = await response.json().catch(() => null);
      console.error(`API check: HTTP ${response.status()}, code ${body?.error?.code || 'unknown'}`);
    }
  });
  stage = 'signing in';
  await page.goto(`${url}/login`);
  await page.getByLabel('Work email').fill(process.env.DEVVAULT_E2E_EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(process.env.DEVVAULT_E2E_PASSWORD);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  stage = 'creating the organization';
  await page.getByLabel('Organization name').fill('Browser smoke workspace');
  await page.getByLabel('Organization slug').fill('browser-smoke');
  await page.getByRole('button', { name: 'Create organization', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Workspace', exact: true })).toBeVisible();
  stage = 'creating a project';
  await page.getByRole('link', { name: 'Projects', exact: true }).click();
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByLabel('Project name').fill('Browser project');
  await page.getByLabel('Project slug').fill('browser-project');
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  stage = 'creating an API service';
  await page.getByRole('button', { name: 'Add service', exact: true }).click();
  await page.getByLabel('Service name').fill('Browser service');
  await page.getByLabel('Service slug').fill('browser-service');
  await page.getByLabel('Audience', { exact: true }).fill('https://api.example.test');
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  stage = 'creating a permission';
  await page.getByRole('button', { name: 'Add permission to Browser service' }).click();
  await page.getByLabel('Scope name').fill('orders:read');
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Permission created');
  stage = 'issuing an API key';
  await page.getByRole('link', { name: 'API keys', exact: true }).click();
  await page.getByRole('button', { name: 'Create API key', exact: true }).click();
  await page.getByLabel('Key name').fill('Browser integration key');
  await page.getByLabel('Permissions', { exact: true }).selectOption({ label: 'orders:read' });
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(page.locator('.secret-panel code')).not.toBeEmpty();
  await page.getByRole('button', { name: 'I’ve saved it — hide value' }).click();
  stage = 'revoking the API key';
  await page.getByRole('button', { name: 'Revoke Browser integration key', exact: true }).click();
  stage = 'confirming key revocation';
  await page.getByRole('button', { name: 'Revoke key', exact: true }).click();
  stage = 'checking the revoked key list';
  await expect(page.getByRole('row').filter({ hasText: 'Browser integration key' })).toContainText(
    'revoked',
  );
  stage = 'creating a policy';
  await page.getByRole('link', { name: 'Access policies', exact: true }).click();
  await page.getByRole('button', { name: 'New policy', exact: true }).click();
  await page.getByLabel('Policy name').fill('Browser rate limit');
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Browser rate limit', exact: true }),
  ).toBeVisible();
  stage = 'reading usage and audit';
  await page.getByRole('link', { name: 'Usage & analytics', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByRole('link', { name: 'Audit log', exact: true }).click();
  stage = 'waiting for the recorded audit event';
  await expect(page.getByRole('cell', { name: 'key.revoked', exact: true })).toBeVisible();
  stage = 'signing out';
  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  if (runtimeErrors.length) throw new Error('Browser runtime errors were detected.');
  console.log('Browser-to-Django flow passed; all records belong to the isolated test database.');
} catch {
  // Do not print DOM, tokens, passwords, network payloads or one-time secrets on failure.
  console.error(`Browser-to-Django check failed while ${stage}.`);
  process.exitCode = 1;
} finally {
  await browser?.close();
  server.kill();
}
