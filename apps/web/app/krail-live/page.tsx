import { KrailLive } from "@/components/krail-live/krail-live";
import { asResource, createServerKrailApiClient } from "@/lib/krail/api/server";
import type { Project, Resource } from "@/lib/krail/api";

export const dynamic = "force-dynamic";

function selectedProject(projects: Resource<Project[]>, requested?: string): Project | undefined {
  if (projects.state !== "ready") return undefined;
  return projects.data.find((project) => project.projectId === requested) ?? projects.data[0];
}

export default async function KrailLivePage({ searchParams }: { searchParams: Promise<{ project?: string }> }) {
  const { project: requestedProject } = await searchParams;
  const api = createServerKrailApiClient();
  const projects = await asResource(() => api.listProjects());
  const project = selectedProject(projects, requestedProject);

  if (!project) return <KrailLive projects={projects} />;

  const [health, manifest, sources] = await Promise.all([
    asResource(() => api.getHealth(project.projectId)),
    asResource(() => api.getManifest(project.projectId)),
    asResource(() => api.getSources(project.projectId)),
  ]);
  return <KrailLive projects={projects} selectedProjectId={project.projectId} health={health} manifest={manifest} sources={sources} />;
}
