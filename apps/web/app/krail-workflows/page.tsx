import { KrailWorkflows } from "@/components/krail-workflows/krail-workflows";
import { asResource, createServerKrailApiClient } from "@/lib/krail/api/server";
import type { Project, Resource } from "@/lib/krail/api";

export const dynamic = "force-dynamic";

type Search = { project?: string; workflow?: string; run?: string };

function selectProject(projects: Resource<Project[]>, projectId?: string) {
  return projects.state === "ready" ? projects.data.find((project) => project.projectId === projectId) ?? projects.data[0] : undefined;
}

export default async function KrailWorkflowsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const api = createServerKrailApiClient();
  const projects = await asResource(() => api.listProjects());
  const project = selectProject(projects, search.project);
  if (!project) return <KrailWorkflows projects={projects} search={search} />;
  const [workflows, approvals, capabilities] = await Promise.all([
    asResource(() => api.getWorkflows(project.projectId)),
    asResource(() => api.getApprovals(project.projectId)),
    asResource(() => api.getExecutionCapabilities()),
  ]);
  return <KrailWorkflows projects={projects} selectedProjectId={project.projectId} workflows={workflows} approvals={approvals} capabilities={capabilities} search={search} />;
}
