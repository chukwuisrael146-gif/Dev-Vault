export type Environment = 'test' | 'live';
export type Project = {
  id: string;
  name: string;
  slug: string;
  description: string;
  services: number;
  environment: Environment;
  status: 'active' | 'archived';
};
export type Credential = {
  id: string;
  name: string;
  project: string;
  prefix: string;
  environment: Environment;
  status: 'active' | 'revoked';
  scopes: string;
  expires: string;
};
export type Policy = {
  id: string;
  name: string;
  project: string;
  algorithm: string;
  limit: number;
  environment: Environment;
  status: 'active' | 'paused';
  version: number;
};
export type Member = { id: string; name: string; email: string; role: string; status: string };
export type Webhook = { id: string; url: string; events: string; status: 'paused' | 'active' };
export const projects: Project[] = [
  {
    id: 'orders',
    name: 'Commerce API',
    slug: 'commerce-api',
    description: 'Orders, inventory & checkout.',
    services: 3,
    environment: 'test',
    status: 'active',
  },
  {
    id: 'platform',
    name: 'Platform services',
    slug: 'platform-services',
    description: 'The building blocks behind the product.',
    services: 2,
    environment: 'test',
    status: 'active',
  },
  {
    id: 'analytics',
    name: 'Analytics pipeline',
    slug: 'analytics-pipeline',
    description: 'Events in. Better decisions out.',
    services: 1,
    environment: 'test',
    status: 'active',
  },
  {
    id: 'production',
    name: 'Commerce production',
    slug: 'commerce-production',
    description: 'Customer-facing production services.',
    services: 3,
    environment: 'live',
    status: 'active',
  },
];
export const credentials: Credential[] = [
  {
    id: 'checkout',
    name: 'Checkout service',
    project: 'Commerce API',
    prefix: 'preview_test_••••_a8f2',
    environment: 'test',
    status: 'active',
    scopes: 'orders:read, orders:write',
    expires: '28 Sep 2026',
  },
  {
    id: 'inventory',
    name: 'Inventory sync',
    project: 'Commerce API',
    prefix: 'preview_test_••••_c91b',
    environment: 'test',
    status: 'active',
    scopes: 'inventory:read',
    expires: '30 Sep 2026',
  },
  {
    id: 'events',
    name: 'Event collector',
    project: 'Analytics pipeline',
    prefix: 'preview_test_••••_e720',
    environment: 'test',
    status: 'active',
    scopes: 'events:write',
    expires: '12 Oct 2026',
  },
  {
    id: 'legacy',
    name: 'Legacy integration',
    project: 'Platform services',
    prefix: 'preview_test_••••_021d',
    environment: 'test',
    status: 'revoked',
    scopes: 'users:read',
    expires: 'Revoked',
  },
  {
    id: 'live',
    name: 'Production checkout',
    project: 'Commerce production',
    prefix: 'preview_live_••••_bb32',
    environment: 'live',
    status: 'active',
    scopes: 'orders:read',
    expires: '28 Sep 2026',
  },
];
export const policies: Policy[] = [
  {
    id: 'rate',
    name: 'Standard request limit',
    project: 'Commerce API',
    algorithm: 'Fixed window',
    limit: 1000,
    environment: 'test',
    status: 'active',
    version: 2,
  },
  {
    id: 'quota',
    name: 'Daily consumption',
    project: 'Commerce API',
    algorithm: 'Daily quota',
    limit: 50000,
    environment: 'test',
    status: 'active',
    version: 1,
  },
  {
    id: 'burst',
    name: 'Burst protection',
    project: 'Platform services',
    algorithm: 'Token bucket',
    limit: 100,
    environment: 'test',
    status: 'active',
    version: 3,
  },
];
export const members: Member[] = [
  { id: 'owner', name: 'Alex Morgan', email: 'alex@example.com', role: 'Owner', status: 'Active' },
  { id: 'dev', name: 'Sam Okafor', email: 'sam@example.com', role: 'Developer', status: 'Active' },
  {
    id: 'analyst',
    name: 'Jordan Lee',
    email: 'jordan@example.com',
    role: 'Analyst',
    status: 'Active',
  },
];
export const auditEvents = [
  {
    id: 'evt-1042',
    action: 'Credential created',
    target: 'Checkout service',
    actor: 'Alex Morgan',
    time: '14:42:08',
    outcome: 'Success',
    category: 'Credentials',
  },
  {
    id: 'evt-1041',
    action: 'Policy updated',
    target: 'Standard request limit',
    actor: 'Alex Morgan',
    time: '14:38:51',
    outcome: 'Success',
    category: 'Policies',
  },
  {
    id: 'evt-1040',
    action: 'Request denied',
    target: 'Inventory sync',
    actor: 'Service integration',
    time: '14:32:17',
    outcome: 'Rate limited',
    category: 'Access',
  },
  {
    id: 'evt-1039',
    action: 'Member invited',
    target: 'jordan@example.com',
    actor: 'Alex Morgan',
    time: '13:56:04',
    outcome: 'Success',
    category: 'Team',
  },
  {
    id: 'evt-1038',
    action: 'Credential revoked',
    target: 'Legacy integration',
    actor: 'Sam Okafor',
    time: '13:42:10',
    outcome: 'Success',
    category: 'Credentials',
  },
];
export const activity = [
  18, 24, 21, 31, 29, 34, 25, 39, 33, 41, 36, 38, 26, 30, 43, 54, 47, 62, 51, 42, 48, 38, 44, 51,
  40, 57, 61, 47, 49, 59, 72, 63, 76, 69, 58, 67, 61, 80, 75, 86, 74, 70, 78, 66, 74, 68, 81, 77,
];
