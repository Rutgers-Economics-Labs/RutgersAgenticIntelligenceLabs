import type {
  ApiError, ApiErrorShape, ApprovalInventoryResponse, ApprovalResponse, FindRequest, FindResponse,
  GraphResponse, IntegrityResponse, Project, ProjectHealthResponse, ProjectListResponse,
  ProjectManifestResponse, SourceCheckResponse, SourceImpactResponse, SourcesResponse,
  ExecutionCapabilityInventory, WorkflowInventoryResponse, WorkflowResponse, WorkflowValidationResponse,
} from "./types";

export class KrailApiClientError extends Error implements ApiError {
  constructor(
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
    public readonly status?: number,
    public readonly details?: Record<string, unknown>,
  ) { super(message); this.name = "KrailApiClientError"; }
}

export interface KrailApiClientOptions {
  baseUrl: string;
  fetch?: typeof fetch;
}

/**
 * The only web boundary for the versioned platform API. It intentionally has no
 * knowledge of local project files or legacy RAIL endpoints. Event streaming can
 * be added here later as a separate EventSource/run-control capability.
 */
export class KrailApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;

  constructor({ baseUrl, fetch: fetcher = fetch }: KrailApiClientOptions) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetcher = fetcher;
  }

  async listProjects(): Promise<Project[]> {
    return (await this.request<ProjectListResponse>("/api/v1/projects")).projects;
  }

  getProject(projectId: string): Promise<Project> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}`);
  }

  getHealth(projectId: string): Promise<ProjectHealthResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/health`);
  }

  getManifest(projectId: string): Promise<ProjectManifestResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/manifest`);
  }

  getSources(projectId: string): Promise<SourcesResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/sources`);
  }

  find(projectId: string, query: FindRequest): Promise<FindResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/find`, {
      method: "POST", body: JSON.stringify(query),
    });
  }

  getGraph(projectId: string, query: { entityType?: string; entity?: string; relationType?: string; topic?: string; limit?: number } = {}): Promise<GraphResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/graph${queryString(query)}`);
  }

  checkSources(projectId: string): Promise<SourceCheckResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/sources/check`, { method: "POST" });
  }

  getAffectedSources(projectId: string, sourceIds: string[] = []): Promise<SourceImpactResponse> {
    const params = new URLSearchParams();
    sourceIds.slice(0, 50).forEach((sourceId) => params.append("sourceId", sourceId));
    const suffix = params.size ? `?${params.toString()}` : "";
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/sources/affected${suffix}`);
  }

  getIntegrity(projectId: string): Promise<IntegrityResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/integrity`);
  }

  getWorkflows(projectId: string): Promise<WorkflowInventoryResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/workflows`);
  }

  getWorkflow(projectId: string, workflowId: string): Promise<WorkflowResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}`);
  }

  validateWorkflow(projectId: string, workflowId: string): Promise<WorkflowValidationResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/validate`, { method: "POST" });
  }

  getApprovals(projectId: string): Promise<ApprovalInventoryResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/approvals`);
  }

  getApproval(projectId: string, approvalId: string): Promise<ApprovalResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/approvals/${encodeURIComponent(approvalId)}`);
  }

  decideApproval(projectId: string, approvalId: string, decision: "approved" | "rejected" | "changes_requested", comment = "", resume = false): Promise<ApprovalResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/approvals/${encodeURIComponent(approvalId)}/decision`, { method: "POST", body: JSON.stringify({ decision, comment, resume }) });
  }

  getExecutionCapabilities(): Promise<ExecutionCapabilityInventory> {
    return this.request("/api/v1/operator/execution-capabilities");
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response;
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        ...init,
        cache: "no-store",
        headers: { accept: "application/json", "content-type": "application/json", ...init.headers },
      });
    } catch (cause) {
      throw new KrailApiClientError("network_error", "The KRAIL platform API could not be reached.", undefined, undefined, { cause: String(cause) });
    }
    const requestId = response.headers.get("x-request-id") ?? undefined;
    const contentType = response.headers.get("content-type") ?? "";
    const payload: unknown = contentType.includes("application/json")
      ? await response.json().catch(() => undefined)
      : undefined;
    if (!response.ok) {
      const body = payload as ApiErrorShape | undefined;
      throw new KrailApiClientError(
        body?.error?.code ?? "http_error",
        body?.error?.message ?? `Request failed (${response.status}).`,
        body?.error?.requestId ?? requestId,
        response.status,
        body?.error?.details,
      );
    }
    if (!contentType.includes("application/json")) {
      throw new KrailApiClientError("invalid_response", "The KRAIL platform API returned a non-JSON response.", requestId, response.status);
    }
    if (payload === undefined) {
      throw new KrailApiClientError("invalid_response", "The KRAIL platform API returned invalid JSON.", requestId, response.status);
    }
    return payload as T;
  }
}

function queryString(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
  return params.size ? `?${params.toString()}` : "";
}
