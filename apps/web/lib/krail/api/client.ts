import type {
  ApiError, ApiErrorShape, FindResponse, Project, ProjectHealthResponse,
  ProjectListResponse, ProjectManifestResponse, SourcesResponse,
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

  // M3 contract: call sites use this method only after the API mounts the route.
  getSources(projectId: string): Promise<SourcesResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/sources`);
  }

  find(projectId: string, text: string): Promise<FindResponse> {
    return this.request(`/api/v1/projects/${encodeURIComponent(projectId)}/find`, {
      method: "POST", body: JSON.stringify({ text }),
    });
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
