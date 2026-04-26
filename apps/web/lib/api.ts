import {
  CommandCenter,
  CatalogActivationResponse,
  HydrationStatus,
  HydrationRerunResponse,
  OntologyClassesResponse,
  PlannerBoard,
  PlannerHome,
  ProjectCatalogResponse,
  ProjectArtifact,
  ProjectApprovals,
  ProjectContext,
  ProjectSkill,
  ProjectSource,
  ResearchLaunchPayload,
  ResearchLaunchPreview,
  RepoPathResponse,
  RunnerSession,
  RunnerSessionDetail
} from "@/lib/types";

const API_ROOT = process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchCommandCenter(slug: string): Promise<CommandCenter> {
  return getJson<CommandCenter>(`/projects/${slug}/command-center`);
}

export async function fetchProjectCatalog(): Promise<ProjectCatalogResponse> {
  return getJson<ProjectCatalogResponse>("/projects");
}

export async function activateCatalogProject(slug: string, clone = false): Promise<CatalogActivationResponse> {
  return postJson<CatalogActivationResponse>(`/projects/catalog/${slug}/activate`, { clone });
}

export async function fetchPlannerHome(slug: string): Promise<PlannerHome> {
  return getJson<PlannerHome>(`/projects/${slug}/planner/home`);
}

export async function fetchPlannerBoard(slug: string): Promise<PlannerBoard> {
  return getJson<PlannerBoard>(`/projects/${slug}/planner/board`);
}

export async function fetchPlannerThread(slug: string): Promise<{ threadId: string; messages: unknown[] }> {
  return getJson(`/projects/${slug}/planner/thread`);
}

export async function fetchRunnerSessions(slug: string): Promise<{ sessions: RunnerSession[] }> {
  return getJson(`/projects/${slug}/runner/sessions`);
}

export async function fetchRunnerSession(slug: string, sessionId: string): Promise<RunnerSession> {
  return getJson(`/projects/${slug}/runner/sessions/${sessionId}`);
}

export async function fetchRunnerSessionDetail(slug: string, sessionId: string): Promise<RunnerSessionDetail> {
  return getJson(`/projects/${slug}/runner/sessions/${sessionId}/detail`);
}

export async function fetchProjectContext(slug: string): Promise<ProjectContext> {
  return getJson(`/projects/${slug}/context`);
}

export async function fetchHydrationStatus(slug: string): Promise<HydrationStatus> {
  return getJson(`/projects/${slug}/hydration/status`);
}

export async function rerunHydration(slug: string, pipelineSlug?: string | null): Promise<HydrationRerunResponse> {
  return postJson<HydrationRerunResponse>(`/projects/${slug}/hydration/rerun`, { pipelineSlug: pipelineSlug || null });
}

export async function fetchProjectApprovals(slug: string): Promise<ProjectApprovals> {
  return getJson(`/projects/${slug}/approvals`);
}

export async function fetchProjectSkills(slug: string): Promise<{ skills: ProjectSkill[]; summary: Record<string, unknown> }> {
  return getJson(`/projects/${slug}/skills`);
}

export async function fetchProjectSources(slug: string): Promise<{ sources: ProjectSource[]; summary: Record<string, unknown>; notes?: string }> {
  return getJson(`/projects/${slug}/sources`);
}

export async function fetchProjectArtifacts(slug: string): Promise<{ artifacts: ProjectArtifact[]; summary: Record<string, unknown> }> {
  return getJson(`/projects/${slug}/artifacts`);
}

export async function previewResearchLaunch(slug: string, payload: ResearchLaunchPayload): Promise<ResearchLaunchPreview> {
  return postJson(`/projects/${slug}/research-launch/preview`, payload);
}

export async function approveResearchLaunch(slug: string, payload: ResearchLaunchPayload): Promise<{ preview: ResearchLaunchPreview; tasks: unknown[]; approvalId: string }> {
  return postJson(`/projects/${slug}/research-launch/approve`, payload);
}

export async function fetchRepoPath(slug: string, path: string): Promise<RepoPathResponse> {
  const trimmed = path.replace(/^\/+/, "");
  return getJson(`/projects/${slug}/repo/${trimmed}`);
}

export async function createProjectFromBrief(brief: string): Promise<{ project: { slug: string; name: string }; gitRepoUrl?: string }> {
  return postJson("/projects/from-brief/create", { brief });
}

export async function fetchOntologyClasses(projectId: string): Promise<OntologyClassesResponse> {
  const response = await fetch(`${API_ROOT}/ontology/classes?projectId=${encodeURIComponent(projectId)}`, {
    cache: "no-store"
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    return {
      error: String(payload?.message ?? payload?.detail ?? `Ontology classes failed: ${response.status}`)
    };
  }
  return response.json() as Promise<OntologyClassesResponse>;
}
