import { Link } from 'react-router';
import { ArrowRight, Code2, ShieldCheck } from 'lucide-react';
import { CopyButton, PageHeading } from '../components/ui';

const example = `POST /api/v1/access/verify/
Authorization: Bearer <customer_api_key>
X-DevVault-Service-Token: <server_only_credential>
Idempotency-Key: <server_owned_operation_uuid>

{
  "service_id": "<service_uuid>",
  "environment": "test",
  "audience": "orders-api",
  "required_scopes": ["orders:read"],
  "method": "GET",
  "units": 1
}`;
export function Integration() {
  return (
    <>
      <PageHeading
        eyebrow="BUILD / INTEGRATION GUIDE"
        title="One boundary. A clearer backend."
        description="Understand the connection before you connect anything."
      />
      <div className="integration-grid">
        <div>
          <div className="guide-step">
            <span>01</span>
            <div>
              <h2>Create your workspace.</h2>
              <p>
                Register and verify an account, then create an organization, project and API
                service. Every project gets test and live environments.
              </p>
              <Link to="/workspace/projects" className="text-link">
                Explore projects
                <ArrowRight size={15} />
              </Link>
            </div>
          </div>
          <div className="guide-step">
            <span>02</span>
            <div>
              <h2>Issue the right credentials.</h2>
              <p>
                A customer API key identifies the consumer. A separate integration credential
                authenticates your backend. They are not interchangeable.
              </p>
            </div>
          </div>
          <div className="guide-step">
            <span>03</span>
            <div>
              <h2>Verify before doing the work.</h2>
              <p>
                Your server chooses scopes, cost and operation IDs. Continue only on an explicit
                allow. A timeout or 503 never means permission.
              </p>
            </div>
          </div>
          <div className="security-note">
            <ShieldCheck size={20} />
            <span>
              Dashboard browsers use access JWTs. Keep integration credentials on trusted
              servers—never in frontend environment variables.
            </span>
          </div>
        </div>
        <section className="code-panel">
          <header>
            <Code2 size={17} />
            <span>SERVER-TO-SERVER / HTTP</span>
            <CopyButton value={example} />
          </header>
          <pre>
            <code>{example}</code>
          </pre>
          <footer>Illustrative request. Replace placeholders only on your server.</footer>
        </section>
      </div>
      <div className="role-guide">
        <h2>Connected dashboard. Server-only enforcement.</h2>
        <p>
          The authoritative endpoint shapes live in <code>dev-vault-backend/docs/openapi.yaml</code>
          . This dashboard calls the management API with your account session. Consumer-key
          verification still belongs in your trusted server, not in this browser.
        </p>
      </div>
    </>
  );
}
