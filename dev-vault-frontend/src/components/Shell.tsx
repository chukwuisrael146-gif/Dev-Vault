import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Box,
  ChevronRight,
  Command,
  Fingerprint,
  KeyRound,
  LayoutDashboard,
  Menu,
  Search,
  Settings2,
  ShieldCheck,
  Users,
  Webhook,
  X,
} from 'lucide-react';
import { Brand } from './ui';
import { useWorkspace } from '../lib/workspace';
import { useSession } from '../lib/data';
import { ResourceState } from './Feedback';

export const destinations = [
  { label: 'Overview', path: '/workspace', icon: LayoutDashboard },
  { label: 'Projects', path: '/workspace/projects', icon: Box },
  { label: 'API keys', path: '/workspace/keys', icon: KeyRound },
  { label: 'Access policies', path: '/workspace/policies', icon: ShieldCheck },
  { label: 'Usage & analytics', path: '/workspace/usage', icon: Activity },
  { label: 'Audit log', path: '/workspace/audit', icon: Fingerprint },
  { label: 'Team members', path: '/workspace/team', icon: Users },
  { label: 'Webhooks', path: '/workspace/webhooks', icon: Webhook },
  { label: 'Settings', path: '/workspace/settings', icon: Settings2 },
];
function SidebarContent({ close }: { close?: () => void }) {
  const store = useWorkspace();
  const user = useSession()?.user;
  return (
    <>
      <Link to="/" className="sidebar-brand" aria-label="DevVault home">
        <Brand />
      </Link>
      <div className="workspace-label">
        <div className="workspace-avatar">{store.organization?.name.slice(0, 1)}</div>
        <div>
          <label htmlFor={close ? 'mobile-organization' : 'desktop-organization'}>
            Organization
          </label>
          <select
            id={close ? 'mobile-organization' : 'desktop-organization'}
            value={store.organization?.id || ''}
            onChange={(event) => store.chooseOrganization(event.target.value)}
          >
            {store.organizations.data?.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="nav-label">WORKSPACE</p>
      <nav aria-label="Workspace">
        {destinations.map(({ label, path, icon: Icon }, index) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/workspace'}
            onClick={close}
            className={index === 6 ? 'nav-link nav-break' : 'nav-link'}
          >
            <Icon size={18} strokeWidth={1.7} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <Link className="guide-link" to="/workspace/integration" onClick={close}>
          <BookOpen size={18} />
          <span>Integration guide</span>
          <ArrowUpRight size={15} />
        </Link>
        <div className="user-row">
          <span className="user-avatar">{user?.email.slice(0, 2).toUpperCase()}</span>
          <span>
            <strong>{user?.first_name || user?.email}</strong>
            <small>Verified account</small>
          </span>
          <Link to="/workspace/settings" aria-label="Account settings">
            <ChevronRight size={18} />
          </Link>
        </div>
      </div>
    </>
  );
}
function SearchDialog({ close }: { close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const element = ref.current;
    element?.showModal();
    return () => {
      element?.close();
      previous?.focus();
    };
  }, []);
  const results = destinations.filter((item) =>
    item.label.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <dialog
      ref={ref}
      className="dialog search-dialog"
      aria-label="Navigate workspace"
      onCancel={close}
    >
      <div className="search-input">
        <Search size={20} />
        <input
          aria-label="Search pages"
          placeholder="Where would you like to go?"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <button className="icon-button" onClick={close} aria-label="Close search">
          <X size={18} />
        </button>
      </div>
      <p className="eyebrow">PAGES</p>
      {results.map(({ path, label, icon: Icon }) => (
        <button
          key={path}
          className="search-result"
          onClick={() => {
            navigate(path);
            close();
          }}
        >
          <Icon size={18} />
          {label}
          <ChevronRight size={16} />
        </button>
      ))}
      {!results.length && <p className="muted">No matching pages. Try “keys” or “usage”.</p>}
    </dialog>
  );
}
export function Shell() {
  const store = useWorkspace();
  const { environment, setEnvironment } = store;
  const [search, setSearch] = useState(false);
  const [mobile, setMobile] = useState(false);
  const drawer = useRef<HTMLDialogElement>(null);
  const location = useLocation();
  const page =
    destinations.find((item) => item.path === location.pathname)?.label ?? 'Integration guide';
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        setSearch((s) => !s);
      }
    };
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, []);
  useEffect(() => {
    if (mobile) drawer.current?.showModal();
    else drawer.current?.close();
  }, [mobile]);
  return (
    <div className="workspace-shell">
      <aside className="sidebar">
        <SidebarContent />
      </aside>
      <dialog
        ref={drawer}
        className="mobile-drawer"
        aria-label="Workspace navigation"
        onCancel={() => setMobile(false)}
      >
        <button
          className="icon-button drawer-close"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        >
          <X size={20} />
        </button>
        <SidebarContent close={() => setMobile(false)} />
      </dialog>
      <div className="workspace-main">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Open navigation"
            onClick={() => setMobile(true)}
          >
            <Menu size={21} />
          </button>
          <div className="breadcrumbs">
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-actions">
            <button
              className="search-trigger"
              onClick={() => setSearch(true)}
              aria-label="Search workspace"
            >
              <Search size={16} />
              <span>Search anything…</span>
              <kbd>
                <Command size={11} />K
              </kbd>
            </button>
            <label className={`environment-select ${environment}`}>
              <span aria-hidden="true" />
              <select
                aria-label="Environment"
                value={environment}
                onChange={(e) => setEnvironment(e.target.value as 'test' | 'live')}
              >
                <option value="test">Test environment</option>
                <option value="live">Live environment</option>
              </select>
            </label>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          <div className="preview-banner">
            <span className="preview-indicator" />
            API-backed workspace{' '}
            <span className="preview-detail">Changes are saved to DevVault.</span>
            <Link to="/workspace/integration">
              Integration guide
              <ArrowUpRight size={13} />
            </Link>
          </div>
          <div className="scope-controls">
            <label>
              Project
              <select
                value={store.project?.id || ''}
                onChange={(event) => store.chooseProject(event.target.value)}
              >
                <option value="" disabled>
                  Select a project
                </option>
                {store.projects.data?.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              API service
              <select
                value={store.service?.id || ''}
                onChange={(event) => store.chooseService(event.target.value)}
              >
                <option value="" disabled>
                  No service selected
                </option>
                {store.services.data?.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <ResourceState resource={store.projects} />
          <ResourceState resource={store.environments} />
          <ResourceState resource={store.services} />
          <div
            key={`${store.organization?.id}:${store.project?.id}:${store.activeEnvironment?.id}:${store.service?.id}`}
          >
            <Outlet />
          </div>
        </main>
        <footer className="workspace-footer">
          <span>DevVault / Your access layer, considered.</span>
          <span>
            DEVVAULT <span className="footer-dot">·</span> v0.2
          </span>
        </footer>
      </div>
      {search && <SearchDialog close={() => setSearch(false)} />}
    </div>
  );
}
