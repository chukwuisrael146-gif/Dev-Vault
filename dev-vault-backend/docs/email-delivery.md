# Account email delivery

Registration, verification resend and password reset use durable database queues.
An API success response means a request was accepted, not that an email reached an
inbox. Password reset intentionally has the same response for unknown/ineligible
accounts; only active, verified accounts receive reset links. Unverified users
should request another verification email instead.

## Local SMTP delivery

Development defaults to `DJANGO_EMAIL_MODE=file`, saving email in `var/emails`.
SMTP settings alone do not change that mode. For Gmail, enable Google 2-Step
Verification and create a dedicated App Password for DevVault. Do not use your
normal Google password. Put these values in the private backend `.env`, not the
frontend or `.env.example`:

```dotenv
DJANGO_EMAIL_MODE=smtp
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-sending-address@gmail.com
EMAIL_HOST_PASSWORD=your-private-google-app-password
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
DEFAULT_FROM_EMAIL=DevVault <your-sending-address@gmail.com>
ACCOUNT_PUBLIC_BASE_URL=http://127.0.0.1:8000
```

Replace placeholders privately. Never commit or paste the App Password into chat.
For another provider, use its SMTP host, credentials and verified sender. Gmail
App Password availability depends on account security and organization policies.
See [Google's App Password instructions](https://support.google.com/mail/answer/185833)
and [SMTP configuration](https://support.google.com/a/answer/176600).

Restart Django and every mail worker after updating `.env`. In the backend terminal,
with the virtual environment active, check connectivity without sending anything:

```powershell
$env:DJANGO_READ_ENV_FILE='true'
python manage.py check_email_connection
```

Then keep a separate local terminal open:

```powershell
$env:DJANGO_READ_ENV_FILE='true'
python manage.py deliver_account_emails --watch
```

The worker polls both account queues every five seconds until Ctrl+C. It uses the
same retry, expiry and consumed-token safeguards as Celery; it does not bypass
verification or print links/passwords. Without `--watch`, it performs one batch.
Existing Celery worker + beat is the production approach; the local command is
not a production process supervisor. It does not process invitation emails.

Request a **fresh** verification or reset link after switching from file to SMTP:
old file-delivered records are already marked sent, and expired links are not
reactivated. SMTP acceptance is not guaranteed inbox placement: check Gmail spam
and sender/provider delivery logs. Provider authentication and failures are not
proof that an account exists and must not be exposed in public API responses.

The localhost link works only on the development computer. For other devices or
deployment, use an approved reachable HTTPS backend origin. Do not expose Django's
development server publicly just to open email links. Render SMTP/network support
and sender-domain deliverability must be checked before production deployment.
