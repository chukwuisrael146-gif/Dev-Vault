import { Link } from 'react-router';
import { ArrowRight, ArrowUpRight, Fingerprint, Layers3, ShieldCheck } from 'lucide-react';
import { Brand } from '../components/ui';

export function Landing() {
  return (
    <div className="public-page">
      <header className="public-header">
        <Link to="/" aria-label="DevVault home">
          <Brand />
        </Link>
        <nav aria-label="Main navigation">
          <Link to="/workspace/integration">How it works</Link>
          <Link to="/login">Sign in</Link>
          <Link className="button" to="/workspace">
            Open workspace
            <ArrowUpRight size={15} />
          </Link>
        </nav>
      </header>
      <main id="main" className="landing-main">
        <div className="landing-kicker">
          <span className="tiny-square" />
          THE ACCESS LAYER FOR YOUR API
        </div>
        <h1>
          Build what’s next.
          <br />
          <span>Know who gets in.</span>
        </h1>
        <p className="landing-description">
          Credentials, permissions and usage limits.
          <br />
          One deliberate boundary between your API
          <br className="desktop-only" /> and everything that depends on it.
        </p>
        <div className="landing-actions">
          <Link to="/workspace" className="button primary large">
            Explore the workspace
            <ArrowUpRight size={19} />
          </Link>
          <Link to="/workspace/integration" className="text-link">
            Understand the architecture
            <ArrowRight size={17} />
          </Link>
        </div>
        <p className="landing-preview-label">Secure workspace · Sign in to manage your APIs</p>
        <div className="landing-index">
          <span>01 — ACCESS, CONSIDERED</span>
          <span>DEVELOPER INFRASTRUCTURE / DEVVAULT</span>
        </div>
        <section className="landing-features" aria-label="DevVault capabilities">
          <div>
            <Fingerprint size={22} />
            <h2>Issue with intention.</h2>
            <p>
              One-time secrets. Exact scopes. Credentials that belong to one service, in one
              environment.
            </p>
          </div>
          <div>
            <ShieldCheck size={22} />
            <h2>Set the boundaries.</h2>
            <p>
              Layer rate limits and durable quotas. Let every applicable policy protect the service.
            </p>
          </div>
          <div>
            <Layers3 size={22} />
            <h2>Keep the evidence.</h2>
            <p>
              Understand consumption and trace meaningful changes through a shared audit history.
            </p>
          </div>
        </section>
      </main>
      <footer className="public-footer">
        <span>devvault. / Built for the boundary.</span>
        <span>DEVVAULT · 2026</span>
      </footer>
    </div>
  );
}
