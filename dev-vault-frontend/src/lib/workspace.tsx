import { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import { Navigate } from 'react-router';
import { useResource, useSession } from './data';
import type { Environment, Organization, Project, Service } from './data';
import { mutate } from './api';
import { FormDialog } from '../components/ui';
import { ResourceState } from '../components/Feedback';

function useWorkspaceState() {
  const [orgChoice, chooseOrganization] = useState('');
  const organizations = useResource<Organization[]>('organizations/', true);
  const organization =
    organizations.data?.find((o) => o.id === orgChoice) || organizations.data?.[0];
  const [projectChoice, chooseProject] = useState('');
  const projects = useResource<Project[]>(
    organization ? `organizations/${organization.id}/projects/` : null,
    true,
  );
  const project =
    projects.data?.find((p) => p.id === projectChoice) ||
    projects.data?.find((p) => !p.archived_at);
  const [environment, setEnvironment] = useState<'test' | 'live'>('test');
  const environments = useResource<{ data: Environment[] }>(
    project ? `projects/${project.id}/environments/` : null,
  );
  const activeEnvironment = environments.data?.data.find((e) => e.kind === environment);
  const services = useResource<Service[]>(
    activeEnvironment ? `environments/${activeEnvironment.id}/services/` : null,
    true,
  );
  const [serviceChoice, chooseService] = useState('');
  const service = services.data?.find((s) => s.id === serviceChoice) || services.data?.[0];
  return {
    organizations,
    organization,
    chooseOrganization,
    projects,
    project,
    chooseProject,
    environment,
    setEnvironment,
    environments,
    activeEnvironment,
    services,
    service,
    chooseService,
  };
}
const Context = createContext<ReturnType<typeof useWorkspaceState> | null>(null);
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  return <Context value={useWorkspaceState()}>{children}</Context>;
}
export function WorkspaceGate({ children }: { children: ReactNode }) {
  const store = useWorkspace();
  if (store.organizations.loading || store.organizations.error)
    return (
      <main id="main" className="not-found">
        <ResourceState resource={store.organizations} />
      </main>
    );
  if (!store.organization)
    return (
      <main id="main" className="not-found">
        <h1>Create your workspace.</h1>
        <p>Your account is ready. Create an organization to start.</p>
        <FormDialog
          title="Create an organization"
          description="This creates a real organization owned by your account."
          fields={[
            { name: 'name', label: 'Organization name' },
            {
              name: 'slug',
              label: 'Organization slug',
              hint: 'Lowercase letters, numbers and hyphens.',
            },
          ]}
          onClose={() => {
            window.location.assign('/login');
          }}
          submitLabel="Create organization"
          onSubmit={async (values, key) => {
            const result = await mutate<Organization>('organizations/', values, key);
            store.chooseOrganization(result.data.id);
            store.organizations.reload();
          }}
        />
      </main>
    );
  return <div key={store.organization.id}>{children}</div>;
}
export function RequireSession({ children }: { children: ReactNode }) {
  return useSession() ? children : <Navigate to="/login" replace />;
}
export function useWorkspace() {
  const value = useContext(Context);
  if (!value) throw new Error('Workspace provider missing');
  return value;
}
