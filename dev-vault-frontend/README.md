# DevVault frontend

React, TypeScript and Vite dashboard connected to the adjacent Django backend.
Workspace screens use API responses, not sample records. Creating, updating and
revoking resources now changes the connected database. Test/live selects a real
project environment; **test does not mean a disposable preview**.

## Run both applications

Use the existing backend virtual environment and private configuration.
PostgreSQL and Redis must be running. In the backend PowerShell terminal:

```powershell
cd "C:\Users\Israel Chukwu\Desktop\dev-vault\dev-vault-backend"
$env:DJANGO_READ_ENV_FILE = 'true'
docker compose up -d redis
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

In a separate frontend terminal:

```powershell
cd "C:\Users\Israel Chukwu\Desktop\dev-vault\dev-vault-frontend"
npm.cmd ci
npm.cmd run dev
```

Open [DevVault](http://127.0.0.1:5173/). Node 22.12+ is required; verified with Node
24.18. If port 5173 is occupied, check whether your DevVault server is already
running. Do not stop an unidentified process.

Vite forwards `/api` to `http://127.0.0.1:8000` and preserves the incoming host
for pagination. No frontend .env or CORS change is needed for this local proxy.
`DEVVAULT_API_PROXY_TARGET` overrides the development-server target for testing.

Sign in with your verified account, or register and confirm the verification email.
Development email stays in the backend's private `var/emails` directory; follow
the backend README for email delivery/preview commands. Email links open the
existing backend confirmation page. `/verify-email` also supports manual token
verification and resending a link. Password-reset emails use the backend form.

New users create an organization, then a project, service and permissions before
issuing keys. Save the one-time key value securely: hiding it or leaving its view
discards the displayed value.

## Connected screens

| Screen   | Implemented interactions                                                             |
| -------- | ------------------------------------------------------------------------------------ |
| Accounts | Register, verify/resend, login, automatic refresh, reset request, logout             |
| Overview | Selected-service usage, key counts and environment policy counts                     |
| Projects | Project list/create, environment selection, service list/create, permission creation |
| API keys | Environment list, service filtering, scoped issuance, confirmed revocation           |
| Policies | Environment list, service policy creation, version-checked pause/enable              |
| Usage    | Real 24-hour/seven-day UTC summaries and series, CSV export jobs                     |
| Audit    | Seven-day cursor-paginated log, current-page search, details, CSV export jobs        |
| Team     | Membership/invitation lists, queued invitations                                      |
| Webhooks | Endpoint list/create, one-time signing value, activation changes                     |
| Settings | Organization name, profile names, password change, sign-out                          |

Django enforces roles on every request. The UI displays authorization failures,
validation details, stale-update conflicts, request IDs and service outages.
Empty traffic remains empty; this dashboard does not generate customer requests.

Aggregation, exports and queued email/webhook delivery need the backend workers
described in its operations documentation. Export jobs have a manual status check;
only ready, unexpired files can be downloaded. Creating a webhook can activate it
when global delivery is enabled. This connection work does not enable global
outbound delivery. Review ownership before adding a real destination.

Not every administration endpoint has a screen yet. Member role/removal/ownership
changes, invitation acceptance, key rotation/grant editing, integration credential
management, policy revisions/quota adjustments and webhook retry/secret rotation
remain API operations. This connection work is not a completed production
deployment or security certification.

## Sessions and secrets

- Access and rotating refresh tokens stay in this tab's memory, never local or
  session storage. Reloading or opening another tab requires signing in again.
- Concurrent expired requests share one refresh operation. Responses from a
  previous session cannot overwrite a changed session.
- Logout clears tab memory even offline, with a warning if server revocation
  could not be confirmed.
- Creation retries retain a per-operation idempotency key while the form stays
  open. Lost one-time secrets cannot be recovered by retrying.
- Requests refuse foreign pagination URLs and redirects. Never put server
  integration credentials or JWT signing keys in frontend source or VITE variables.
- Sensitive changes may require signing in again after 15 minutes. Password
  changes invalidate all sessions.

## Hosted configuration

The development proxy is **not** included in the compiled build. For separate
frontend hosting, set public build-time `VITE_API_BASE_URL` to the backend's HTTPS
`/api/v1/` URL, as shown in .env.example, then rebuild. Alternatively configure
a same-origin production reverse proxy.

Set exact frontend HTTPS origins in backend `CORS_ALLOWED_ORIGINS` and the
backend hostname in `DJANGO_ALLOWED_HOSTS`. No wildcard origins or browser
database credentials. Frontend hosting must serve index.html for application
routes. Render-specific backend hardening and deployment remain separate work.

## Checks

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
npm.cmd test
```

Normal browser tests use contract fixtures for errors, refresh races, mutations,
navigation, mobile layout, focus and accessibility. They launch an isolated
headless Microsoft Edge instance, not a personal profile, and do not write to
your development database. Failure traces contain fixture data only.

For the real browser-to-Django check, install frontend dependencies and Edge,
leave port 5174 free, then run from the backend folder:

```powershell
$env:DEVVAULT_BROWSER_TEST = '1'
.\scripts\test_postgresql.ps1
Remove-Item Env:DEVVAULT_BROWSER_TEST
```

This requires local PostgreSQL 18 binaries and Redis. The script starts a disposable
PostgreSQL cluster and runs the backend suite, including the browser check. SQLite's
shared in-memory test connection is not used for concurrent browser requests.
This uses an isolated Django test database and temporary frontend process to check
sign-in, organization/project/service creation, permissions, key issuance/revocation,
policies, reporting and logout. No external email or credential screenshots/traces.
Normal backend tests skip this opt-in browser check.

## Design and code map

The original graphite/ivory/lime design and local architectural video remain on
every page. The bottom-right control pauses video; reduced-motion preferences
start it paused. Only the motion preference is persisted. Local assets provide
a poster fallback without external media URLs.

- `src/lib/api.ts`: request/errors and in-memory authentication.
- `src/lib/data.ts`: abortable resources and response types.
- `src/lib/workspace.tsx`: organization/project/environment/service selection.
- `src/components/`: shell, feedback, dialogs, chart and export jobs.
- `src/pages/`: connected screens.
- `tests/`: contract tests and real-backend smoke script.
- `src/lib/demo.ts`: unused legacy fixtures; not imported by the application.

The original local 10-second 1600×900 VP9 loop is in
`public/media/vault-motion.webm`; `vault-poster.svg` is its fallback. Optional
`npm.cmd run media` regenerates these assets using Edge. No third-party footage
or analytics are loaded. The monogram and background were created for DevVault;
Manrope uses OFL-1.1 and Lucide ISC. The supplied frontend-design skill informed
the original design; this connection work preserves it.
