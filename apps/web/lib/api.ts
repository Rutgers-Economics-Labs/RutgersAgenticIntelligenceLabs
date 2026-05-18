import {
  AutopilotStatus,
  CommandCenter,
  CatalogActivationResponse,
  DashboardResponse,
  HydrationStatus,
  HydrationRerunResponse,
  OntologyClassesResponse,
  PlannerBoard,
  PlannerHome,
  PlannerTaskDraft,
  ProjectCatalogResponse,
  ProjectArtifact,
  ProjectApprovals,
  ProjectContext,
  ProjectIntegrityResponse,
  IntegrityRerunPlan,
  ProjectSkill,
  ProjectSource,
  ResearchLaunchPayload,
  ResearchLaunchPreview,
  RepoPathResponse,
  RunnerSession,
  RunnerSessionDetail,
  ZenResponse
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

export async function fetchZenMode(slug: string): Promise<ZenResponse> {
  return getJson<ZenResponse>(`/projects/${slug}/zen`);
}

export async function fetchCommandCenter(slug: string): Promise<CommandCenter> {
  return getJson<CommandCenter>(`/projects/${slug}/command-center`);
}

export async function reconcileCommandCenter(slug: string): Promise<{
  removedTaskFiles: string[];
  updatedTaskIds: string[];
  repairedSessionIds: string[];
  repairedAuditSessionIds: string[];
  hasChanges: boolean;
}> {
  return postJson(`/projects/${slug}/command-center/reconcile`, {});
}

export async function createOntologyFollowUpTask(
  slug: string,
  payload: { title: string; classification: string },
): Promise<{ created: boolean; task: Record<string, unknown> }> {
  return postJson(`/projects/${slug}/command-center/ontology-follow-ups/expand`, payload);
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

export async function fetchAutopilotStatus(slug: string): Promise<AutopilotStatus> {
  return getJson<AutopilotStatus>(`/projects/${slug}/autopilot/status`);
}

export async function toggleProjectAutopilot(
  slug: string,
  payload: { enabled: boolean; autoApprove: boolean },
): Promise<{ status: string; slug: string; autoApprove?: boolean }> {
  return postJson(`/projects/${slug}/autopilot`, payload);
}

export async function createPlannerTask(
  slug: string,
  payload: PlannerTaskDraft,
): Promise<Record<string, unknown>> {
  return postJson(`/projects/${slug}/planner/tasks`, payload);
}

export async function updatePlannerTask(
  slug: string,
  taskId: string,
  payload: Partial<PlannerTaskDraft> & { status?: string },
): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_ROOT}/projects/${slug}/planner/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API /projects/${slug}/planner/tasks/${taskId} failed: ${response.status}`);
  }
  return response.json();
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

export async function fetchProjectIntegrity(slug: string): Promise<ProjectIntegrityResponse> {
  return getJson(`/projects/${slug}/integrity`);
}

export async function updateIntegrityAssumption(
  slug: string,
  assumptionKey: string,
  payload: {
    title?: string;
    value?: string;
    status?: string;
    notes?: string | null;
    affectedPaths?: string[];
  },
): Promise<{ assumption: Record<string, unknown>; affectedArtifacts: Array<Record<string, unknown>>; rerunPlan: IntegrityRerunPlan }> {
  const response = await fetch(`${API_ROOT}/projects/${slug}/integrity/assumptions/${encodeURIComponent(assumptionKey)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API /projects/${slug}/integrity/assumptions/${assumptionKey} failed: ${response.status}`);
  }
  return response.json();
}

export async function previewIntegrityRerunPlan(slug: string, assumptionKey: string): Promise<IntegrityRerunPlan> {
  return postJson(`/projects/${slug}/integrity/rerun-plan`, { assumptionKey });
}

export async function applyIntegrityRerunPlan(
  slug: string,
  assumptionKey: string,
): Promise<{ rerunPlan: IntegrityRerunPlan; tasks: Array<Record<string, unknown>> }> {
  return postJson(`/projects/${slug}/integrity/rerun-plan/apply`, { assumptionKey });
}

export async function previewBatchIntegrityRerunPlan(slug: string, assumptionKeys: string[]): Promise<IntegrityRerunPlan> {
  return postJson(`/projects/${slug}/integrity/batch-rerun-plan`, { assumptionKeys });
}

export async function applyBatchIntegrityRerunPlan(
  slug: string,
  assumptionKeys: string[],
): Promise<{ rerunPlan: IntegrityRerunPlan; tasks: Array<Record<string, unknown>> }> {
  return postJson(`/projects/${slug}/integrity/batch-rerun-plan/apply`, { assumptionKeys });
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

export async function resolveApproval(slug: string, approvalId: string, status: "granted" | "rejected", note?: string): Promise<Record<string, unknown>> {
  return postJson(`/projects/${slug}/approvals/${encodeURIComponent(approvalId)}/resolve`, {
    status,
    grantedByUserId: "user",
    resolutionNote: note ?? (status === "granted" ? "Approved via dashboard." : "Rejected via dashboard."),
  });
}

export async function fetchRunnerEvents(runner: string, sessionId: string): Promise<{ session_id: string; runner: string; events: unknown[] }> {
  return getJson(`/runners/${runner}/sessions/${encodeURIComponent(sessionId)}/events`);
}

export async function launchTask(
  slug: string,
  task: { _id?: string; title: string; description?: string; agentRole?: string; acceptanceCriteria?: unknown[] },
  runnerName: string,
): Promise<{ convex_session_id?: string; session_id?: string }> {
  return postJson(`/projects/${slug}/runner/sessions`, {
    taskId: task._id ?? null,
    role: task.agentRole ?? "research",
    taskDescription: task.description ?? task.title,
    runnerName,
    acceptanceCriteria: (task.acceptanceCriteria ?? []).map((c) =>
      typeof c === "string" ? c : JSON.stringify(c)
    ),
  });
}

export async function fetchActiveAgents(slug: string): Promise<{ agents: Array<{ sessionId: string; role: string; runner: string; status: string; title: string; startedAt?: number; taskId?: string }> }> {
  return getJson(`/projects/${slug}/agents/active`);
}

export async function runResearchAgents(
  slug: string,
  agents: Array<{ focus: string; queries: string[] }>,
  extraContext?: string,
): Promise<{ ok: boolean; message: string; agents: string[] }> {
  return postJson(`/projects/${slug}/research-agents/run`, {
    agents,
    extra_context: extraContext ?? "",
  });
}

export async function fetchOntologyClasses(projectId: string): Promise<OntologyClassesResponse> {
  try {
    const response = await fetch(`${API_ROOT}/ontology/classes?projectId=${projectId}`, {
      cache: "no-store"
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      return {
        error: String(payload?.message ?? payload?.detail ?? `Ontology classes failed: ${response.status}`)
      };
    }
    return response.json() as Promise<OntologyClassesResponse>;
  } catch (err) {
    return { error: String(err) };
  }
}

export async function fetchOntologyInstances(
  projectId: string,
  className: string,
  options: { page?: number; limit?: number; search?: string } = {}
): Promise<any> {
  const query = new URLSearchParams({
    projectId,
    page: String(options.page ?? 1),
    limit: String(options.limit ?? 10),
  });
  if (options.search) query.append("search", options.search);
  return getJson(`/ontology/classes/${className}/instances?${query.toString()}`);
}

export async function generateDashboard(slug: string): Promise<DashboardResponse> {
  return postJson<DashboardResponse>(`/projects/${slug}/dashboard/generate`, {});
}

export async function fetchDashboard(slug: string): Promise<DashboardResponse | null> {
  const response = await fetch(`${API_ROOT}/projects/${slug}/dashboard`, {
    cache: "no-store",
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`API /projects/${slug}/dashboard failed: ${response.status}`);
  }
  return response.json() as Promise<DashboardResponse>;
}

export async function fetchOntologyGraph(
  projectId: string,
  options: { limit?: number } = {}
): Promise<any> {
  try {
    const query = new URLSearchParams({
      projectId,
      limit: String(options.limit ?? 50),
    });
    const response = await fetch(`${API_ROOT}/ontology/graph?${query.toString()}`, {
      cache: "no-store"
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      return {
        nodes: [],
        links: [],
        error: String(payload?.message ?? payload?.detail ?? `Ontology graph failed: ${response.status}`)
      };
    }
    return response.json() as Promise<any>;
  } catch (err) {
    return {
      nodes: [],
      links: [],
      error: String(err)
    };
  }
}
