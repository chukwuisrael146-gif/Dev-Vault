import { useEffect } from 'react';
import { Link, Route, Routes, useLocation } from 'react-router';
import { Background } from './components/Background';
import { Shell } from './components/Shell';
import { RequireSession, WorkspaceGate, WorkspaceProvider } from './lib/workspace';
import { Landing } from './pages/Landing';
import { Auth } from './pages/Auth';
import { Overview } from './pages/Overview';
import { Projects } from './pages/Projects';
import { Credentials } from './pages/Credentials';
import { Policies } from './pages/Policies';
import { Audit } from './pages/Audit';
import { Team } from './pages/Team';
import { Webhooks } from './pages/Webhooks';
import { Settings } from './pages/Settings';
import { Integration } from './pages/Integration';
import { Verification } from './pages/Verification';

export function App() {
  const location = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
    document.title = `${location.pathname.startsWith('/workspace') ? 'Workspace' : 'API access, under control'} — DevVault`;
  }, [location.pathname]);
  return (
    <>
      <Background />
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Auth key="login" mode="login" />} />
        <Route path="/register" element={<Auth key="register" mode="register" />} />
        <Route path="/reset-password" element={<Auth key="reset" mode="reset" />} />
        <Route path="/verify-email" element={<Verification />} />
        <Route
          path="/workspace"
          element={
            <RequireSession>
              <WorkspaceProvider>
                <WorkspaceGate>
                  <Shell />
                </WorkspaceGate>
              </WorkspaceProvider>
            </RequireSession>
          }
        >
          <Route index element={<Overview />} />
          <Route path="projects" element={<Projects />} />
          <Route path="keys" element={<Credentials />} />
          <Route path="policies" element={<Policies />} />
          <Route path="usage" element={<Overview analytics />} />
          <Route path="audit" element={<Audit />} />
          <Route path="team" element={<Team />} />
          <Route path="webhooks" element={<Webhooks />} />
          <Route path="settings" element={<Settings />} />
          <Route path="integration" element={<Integration />} />
        </Route>
        <Route
          path="*"
          element={
            <main id="main" className="not-found">
              <p className="eyebrow">404 / OUTSIDE THE BOUNDARY</p>
              <h1>This page isn’t in the vault.</h1>
              <p>Check the address or return to your workspace.</p>
              <Link className="button primary" to="/workspace">
                Back to workspace
              </Link>
            </main>
          }
        />
      </Routes>
    </>
  );
}
