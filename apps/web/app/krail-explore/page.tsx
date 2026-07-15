import { KrailExplore } from "@/components/krail-explore/krail-explore";
import { asResource, createServerKrailApiClient } from "@/lib/krail/api/server";
import type { Project, Resource } from "@/lib/krail/api";

export const dynamic = "force-dynamic";

type Search = { project?: string; q?: string; type?: string; topic?: string; entity?: string; status?: string; freshness?: string; workflow?: string };
const MAX_IMPACT_SOURCE_IDS = 50;

function selectedProject(projects: Resource<Project[]>, requested?: string) {
  return projects.state === "ready" ? projects.data.find((project) => project.projectId === requested) ?? projects.data[0] : undefined;
}

export default async function KrailExplorePage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const api = createServerKrailApiClient();
  const projects = await asResource(() => api.listProjects());
  const project = selectedProject(projects, search.project);
  if (!project) return <KrailExplore projects={projects} search={search} />;

  const sourceIds = await asResource(() => api.getSources(project.projectId));
  const allSourceIds = sourceIds.state === "ready"
    ? Array.from(new Set(sourceIds.data.inventory.sources.map((source) => source.id))).sort()
    : [];
  const impactSourceIds = allSourceIds.slice(0, MAX_IMPACT_SOURCE_IDS);
  const impactIsPartial = allSourceIds.length > impactSourceIds.length;
  const [find, graph, integrity, affected, workflows, approvals] = await Promise.all([
    search.q?.trim() ? asResource(() => api.find(project.projectId, { text: search.q!.trim(), types: search.type ? [search.type] : [], topic: search.topic, entity: search.entity, status: search.status, freshness: search.freshness, workflow: search.workflow, explain: true })) : Promise.resolve({ state: "empty", message: "Enter a search to query this KRAIL project." } as const),
    asResource(() => api.getGraph(project.projectId, { entity: search.entity, topic: search.topic })),
    asResource(() => api.getIntegrity(project.projectId)),
    impactSourceIds.length ? asResource(() => api.getAffectedSources(project.projectId, impactSourceIds)) : Promise.resolve({ state: "empty", message: "No source impact records are available." } as const),
    asResource(() => api.getWorkflows(project.projectId)),
    asResource(() => api.getApprovals(project.projectId)),
  ]);
  return <KrailExplore projects={projects} selectedProjectId={project.projectId} search={search} find={find} graph={graph} sources={sourceIds} integrity={integrity} affected={affected} impactIsPartial={impactIsPartial} impactSourceCount={impactSourceIds.length} workflows={workflows} approvals={approvals} />;
}
