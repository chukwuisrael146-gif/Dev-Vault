import { useState } from 'react';
import { Box, Plus, Search } from 'lucide-react';
import { useWorkspace } from '../lib/workspace';
import { mutate } from '../lib/api';
import type { Project, Service } from '../lib/data';
import { CreateButton, EmptyState, FormDialog, PageHeading, Status } from '../components/ui';

export function Projects() {
  const store = useWorkspace();
  const [search, setSearch] = useState('');
  const [create, setCreate] = useState(false);
  const [serviceForm, setServiceForm] = useState(false);
  const [permissionForm, setPermissionForm] = useState(false);
  const [message, setMessage] = useState('');
  const projects = (store.projects.data || []).filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE / PROJECTS"
        title="A place for every service."
        description="Projects contain separate test and live environments."
        action={<CreateButton onClick={() => setCreate(true)}>New project</CreateButton>}
      />
      <div className="toolbar">
        <label className="filter-search">
          <Search size={16} />
          <input
            aria-label="Search projects"
            placeholder="Find a project…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <span className="small muted">{projects.length} projects</span>
      </div>
      {message && (
        <p className="inline-success" role="status">
          {message}
        </p>
      )}
      <div className="project-grid">
        {projects.map((p) => (
          <article className="project-card" key={p.id}>
            <div className="project-top">
              <Box size={24} />
              <Status value={p.archived_at ? 'archived' : 'active'} />
            </div>
            <span className="eyebrow">/{p.slug}</span>
            <h2>
              <button onClick={() => store.chooseProject(p.id)}>{p.name}</button>
            </h2>
            <p>Test and live environments</p>
            <footer>
              {store.project?.id === p.id ? 'Selected project' : 'Select to manage services'}
            </footer>
          </article>
        ))}
        <button className="project-create" onClick={() => setCreate(true)}>
          <Plus size={23} />
          <strong>Create a project</strong>
        </button>
      </div>
      {!store.projects.loading && !store.projects.error && !projects.length && (
        <EmptyState title="No projects yet.">
          Create your first project to start organizing APIs.
        </EmptyState>
      )}
      {store.project && (
        <section className="panel project-detail">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">{store.environment.toUpperCase()} / SERVICES</p>
              <h2>{store.project.name}</h2>
            </div>
            {store.activeEnvironment && (
              <CreateButton onClick={() => setServiceForm(true)}>Add service</CreateButton>
            )}
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Audience</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {store.services.data?.map((service) => (
                  <tr key={service.id}>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => store.chooseService(service.id)}
                      >
                        {service.name}
                      </button>
                    </td>
                    <td className="mono">{service.audience}</td>
                    <td>
                      <Status value={service.is_active ? 'active' : 'disabled'} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!store.services.loading && !store.services.data?.length && (
            <p className="muted">No services in this environment yet.</p>
          )}
          {store.service && (
            <div className="detail-links">
              <button className="button" onClick={() => setPermissionForm(true)}>
                Add permission to {store.service.name}
              </button>
            </div>
          )}
        </section>
      )}
      {create && (
        <FormDialog
          title="Create a project"
          description="Both test and live environments are created automatically."
          fields={[
            { name: 'name', label: 'Project name' },
            {
              name: 'slug',
              label: 'Project slug',
              hint: 'Lowercase letters, numbers and hyphens.',
            },
          ]}
          onClose={() => setCreate(false)}
          onSubmit={async (v, key) => {
            const result = await mutate<Project>(
              `organizations/${store.organization!.id}/projects/`,
              v,
              key,
            );
            setCreate(false);
            store.chooseProject(result.data.id);
            store.projects.reload();
          }}
        />
      )}
      {serviceForm && (
        <FormDialog
          title="Add an API service"
          description={`Create a service in the ${store.environment} environment.`}
          fields={[
            { name: 'name', label: 'Service name' },
            { name: 'slug', label: 'Service slug' },
            {
              name: 'audience',
              label: 'Audience',
              hint: 'The exact API audience expected by your server.',
            },
          ]}
          onClose={() => setServiceForm(false)}
          onSubmit={async (v, key) => {
            const result = await mutate<Service>(
              `environments/${store.activeEnvironment!.id}/services/`,
              v,
              key,
            );
            setServiceForm(false);
            store.chooseService(result.data.id);
            store.services.reload();
          }}
        />
      )}
      {permissionForm && (
        <FormDialog
          title="Add a permission"
          description={`Define an exact scope for ${store.service!.name}.`}
          fields={[
            { name: 'name', label: 'Scope name', placeholder: 'orders:read' },
            { name: 'description', label: 'Description', optional: true },
          ]}
          onClose={() => setPermissionForm(false)}
          onSubmit={async (v, key) => {
            await mutate(`services/${store.service!.id}/permissions/`, v, key);
            setPermissionForm(false);
            setMessage('Permission created. It can now be selected when issuing a key.');
          }}
        />
      )}
    </>
  );
}
