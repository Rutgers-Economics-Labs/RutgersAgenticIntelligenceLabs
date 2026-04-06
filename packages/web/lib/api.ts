const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
  } catch (e) {
    const isNetwork =
      e instanceof TypeError &&
      (e.message === "Failed to fetch" || e.message.includes("fetch") || e.message.includes("NetworkError"));
    const hint = isNetwork
      ? ` Cannot reach ${API_BASE}. Start the FastAPI server (e.g. \`make api\` from the repo root) and ensure NEXT_PUBLIC_API_URL matches it.`
      : "";
    throw new Error(
      e instanceof Error ? `${e.message}.${hint}` : `Request failed: ${String(e)}${hint}`,
    );
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function isSyncRequiredError(error: any): boolean {
  return error?.message?.includes("API 428");
}

// ── Ontology ──────────────────────────────────────────────────────────────────

export type OntologyClass = { name: string; instanceCount: number };
export type EntitySummary = {
  id: string; iri: string; class: string;
  properties: Record<string, unknown>;
};
export type EntityDetail = EntitySummary & {
  relationships: { property: string; targetId: string; targetName: string }[];
};
export type GraphData = {
  nodes: { id: string; label: string; group: string; properties: Record<string, unknown> }[];
  links: { source: string; target: string; label: string }[];
};
export type SeriesPoint = { date: string; value: number };

/** FastAPI uses Query(..., alias="projectId") — query string must be `projectId`, not `project_id`. */
function withProject(params: URLSearchParams, projectId?: string) {
  if (projectId) params.set("projectId", projectId);
}

export const ontology = {
  classes: (projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    return req<OntologyClass[]>(`/ontology/classes${params.size ? `?${params}` : ""}`);
  },
  instances: (cls: string, page = 1, limit = 50, search = "", projectId?: string) => {
    const params = new URLSearchParams({ page: String(page), limit: String(limit), search });
    withProject(params, projectId);
    return req<{ total: number; page: number; limit: number; items: EntitySummary[] }>(
      `/ontology/classes/${cls}/instances?${params}`
    );
  },
  entity: (uri: string, projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    return req<EntityDetail>(`/ontology/entities/${encodeURIComponent(uri)}${params.size ? `?${params}` : ""}`);
  },
  entityGraph: (uri: string, projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    return req<GraphData>(`/ontology/entities/${encodeURIComponent(uri)}/graph${params.size ? `?${params}` : ""}`);
  },
  graph: (types: string[], stateFips?: string, limit = 500, projectId?: string) => {
    const params = new URLSearchParams({ types: types.join(","), limit: String(limit) });
    if (stateFips) params.set("state_fips", stateFips);
    withProject(params, projectId);
    return req<GraphData>(`/ontology/graph?${params}`);
  },
  search: (q: string, types?: string[], projectId?: string) => {
    const params = new URLSearchParams({ q });
    if (types) params.set("types", types.join(","));
    withProject(params, projectId);
    return req<EntitySummary[]>(`/ontology/search?${params}`);
  },
  semanticSearch: (q: string, types?: string[], limit = 20, projectId?: string) => {
    const params = new URLSearchParams({ q, limit: String(limit) });
    if (types) params.set("types", types.join(","));
    withProject(params, projectId);
    return req<EntitySummary[]>(`/ontology/semantic-search?${params}`);
  },
  series: (projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    return req<string[]>(`/ontology/series${params.size ? `?${params}` : ""}`);
  },
  seriesData: (id: string, projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    return req<SeriesPoint[]>(`/ontology/series/${encodeURIComponent(id)}/data${params.size ? `?${params}` : ""}`);
  },
};

// ── Analysis ──────────────────────────────────────────────────────────────────

export type AnalysisPlugin = { slug: string; name: string; description: string };
export type AnalysisResult = { title: string; sections: AnalysisSection[] };
export type AnalysisSection =
  | { type: "metrics"; title?: string; items: { label: string; value: unknown }[] }
  | { type: "table"; title?: string; columns: string[]; data: Record<string, unknown>[] }
  | { type: "chart"; title?: string; data: Record<string, unknown>[]; x: string; y: string }
  | { type: "text"; title?: string; content: string }
  | { type: "divider" }
  | { type: "group"; title?: string; items: AnalysisSection[] };

export const analysis = {
  plugins: () => req<AnalysisPlugin[]>("/analysis/plugins"),
  run: (slug: string, config = {}, projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    const qs = params.size ? `?${params}` : "";
    return req<AnalysisResult>(`/analysis/plugins/${slug}/run${qs}`, {
      method: "POST",
      body: JSON.stringify({ config }),
    });
  },
  runCode: (code: string, projectId?: string, options?: { timeout?: number }) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    const qs = params.size ? `?${params}` : "";
    return req<{ jobId: string; status: string }>(`/analysis/run-code${qs}`, {
      method: "POST",
      body: JSON.stringify({ code, ...options }),
    });
  },
};

// ── Configs ───────────────────────────────────────────────────────────────────

type ConfigType = "apis" | "ontologies" | "pipelines";

export type ConfigDoc = {
  _id: string; name: string; slug: string; content: string;
  isPublic: boolean; tags?: string[]; updatedAt: number;
};

export type ScrapePreview = {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
};

export type DocumentPreview = {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  source_text?: string;
};

export type RegistryEntry = {
  provider: string;
  id: string;
  name: string;
  description: string;
  unit: string;
  frequency: string;
  geography: string;
  tags: string[];
  exampleYaml: string;
  updatedAt: number;
};

export const configs = {
  validate: (config_type: string, content: string) =>
    req<{ valid: boolean; errors: string[] }>("/configs/validate", {
      method: "POST",
      body: JSON.stringify({ config_type, content }),
    }),
  /** Resolves referenced API/ontology configs in Convex + checks classes, foreach order, transforms. */
  validatePipeline: (content: string) =>
    req<{ valid: boolean; errors: string[] }>("/configs/pipelines/validate", {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  create: (type: ConfigType, body: { name: string; slug: string; content: string; isPublic: boolean; tags: string[] }, projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    const qs = params.size ? `?${params}` : "";
    return req(`/configs/${type}${qs}`, { method: "POST", body: JSON.stringify(body) });
  },
  update: (type: ConfigType, slug: string, body: { name: string; slug: string; content: string; isPublic: boolean; tags: string[] }) =>
    req(`/configs/${type}/${slug}`, { method: "PUT", body: JSON.stringify(body) }),
  delete: (type: ConfigType, slug: string) =>
    req(`/configs/${type}/${slug}`, { method: "DELETE" }),
  scrapePreview: (body: { url: string; table_selector?: string; javascript?: boolean; encoding?: string }) =>
    req<ScrapePreview>("/configs/scrape-preview", { method: "POST", body: JSON.stringify(body) }),
  docPreview: (body: { storage_key: string; extraction_mode: "tables" | "prose" | "both"; pages?: string }) =>
    req<DocumentPreview>("/configs/doc-preview", { method: "POST", body: JSON.stringify(body) }),
};

export type ConnectorTemplate = {
  _id: string;
  name: string;
  slug: string;
  description: string;
  version: string;
  content: string;
  tags: string[];
  usageCount?: number;
};

export const connectors = {
  list: (q?: string, tags?: string[]) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (tags && tags.length > 0) params.set("tags", tags.join(","));
    const qs = params.size ? `?${params}` : "";
    return req<ConnectorTemplate[]>(`/connectors${qs}`);
  },
  get: (slug: string) => req<ConnectorTemplate>(`/connectors/${slug}`),
  create: (data: Partial<ConnectorTemplate>) => req<ConnectorTemplate>("/connectors", { method: "POST", body: JSON.stringify(data) }),
  update: (slug: string, data: Partial<ConnectorTemplate>) => req<ConnectorTemplate>(`/connectors/${slug}`, { method: "PUT", body: JSON.stringify(data) }),
  remove: (slug: string) => req(`/connectors/${slug}`, { method: "DELETE" }),
  validate: (slug: string, content: string) => req<{ valid: boolean; errors: string[] }>(`/connectors/${slug}/validate`, {
    method: "POST",
    body: JSON.stringify({ slug, content, name: "", description: "", version: "" })
  }),
  resolve: (baseContent: string, extendsSlug: string) => req<{ resolved_content: string }>("/connectors/resolve", {
    method: "POST",
    body: JSON.stringify({ base_content: baseContent, extends_slug: extendsSlug })
  }),
};

export const registry = {
  search: (query = "", provider?: string, geography?: string, limit = 20) => {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    if (provider && provider !== "all") params.set("provider", provider);
    if (geography && geography !== "all") params.set("geography", geography);
    return req<RegistryEntry[]>(`/registry/search?${params}`);
  },
  get: (provider: string, id: string) =>
    req<RegistryEntry>(`/registry/${encodeURIComponent(provider)}/${encodeURIComponent(id)}`),
  create: (entry: RegistryEntry) =>
    req<RegistryEntry>("/registry", { method: "POST", body: JSON.stringify(entry) }),
};

// ── Jobs ──────────────────────────────────────────────────────────────────────

export type JobRecord = {
  jobId: string;
  pipelineSlug: string;
  projectId?: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  createdAt: number;
  finishedAt?: number;
  stepResults?: any[];
};

export type JobLog = {
  seq: number;
  message: string;
  level: string;
  timestamp: number;
};

export const jobs = {
  list: (projectId?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (projectId) params.set("projectId", projectId);
    return req<JobRecord[]>(`/jobs?${params}`);
  },
  get: (jobId: string) => req<JobRecord>(`/jobs/${jobId}`),
  getLogs: (jobId: string, afterSeq = 0) =>
    req<JobLog[]>(`/jobs/${jobId}/logs?after_seq=${afterSeq}`),
  trigger: (pipeline_slug: string, project_id?: string) =>
    req<{ jobId: string; status: string }>("/jobs", {
      method: "POST",
      body: JSON.stringify({ pipeline_slug, ...(project_id ? { project_id } : {}) }),
    }),
};

// ── SQL ───────────────────────────────────────────────────────────────────────

export type SqlResult = {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  sql?: string;
  explanation?: string;
};

export const sql = {
  query: (query: string, projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    const qs = params.size ? `?${params}` : "";
    return req<SqlResult>(`/sql${qs}`, { method: "POST", body: JSON.stringify({ query }) });
  },
  translate: (question: string, model?: string, projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    const qs = params.size ? `?${params}` : "";
    return req<SqlResult>(`/sql/translate${qs}`, { method: "POST", body: JSON.stringify({ question, model }) });
  },
  schema: (projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    return req<Record<string, { name: string; type: string }[]>>(`/sql/schema${params.size ? `?${params}` : ""}`);
  },
  tables: (projectId?: string) => {
    const params = new URLSearchParams();
    withProject(params, projectId);
    return req<string[]>(`/sql/tables${params.size ? `?${params}` : ""}`);
  },
};

// ── Project Agent ─────────────────────────────────────────────────────────────

export const projectAgent = {
  /** Streaming project-aware chat. Yields AgentEvent objects. */
  chat: async function* (
    projectId: string,
    message: string,
    history: { role: string; content: string }[] = [],
    model?: string,
  ): AsyncGenerator<AgentEvent> {
    const response = await fetch(`${API_BASE}/project-agent/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId, message, history, model }),
    });
    if (!response.ok || !response.body) {
      const text = await response.text().catch(() => response.statusText);
      throw new Error(`Project agent API ${response.status}: ${text}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (line.startsWith("data: ")) {
          try { yield JSON.parse(line.slice(6)) as AgentEvent; } catch { /* skip */ }
        }
      }
    }
  },

  /** Fire-and-forget autonomous task. Returns {jobId} to track via Convex. */
  runTask: async (
    projectId: string,
    goal: string,
    model?: string,
  ): Promise<{ jobId: string }> => {
    const res = await fetch(`${API_BASE}/project-agent/task`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId, goal, model }),
    });
    if (!res.ok) throw new Error(`Agent task API ${res.status}`);
    return res.json();
  },
};

// ── Schedules ─────────────────────────────────────────────────────────────────

export type CreateScheduleRequest = {
  project_slug: string;
  pipeline_slug: string;
  frequency: string;
  cron?: string;
  window?: string;
  window_ends_at?: number;
  enabled: boolean;
};

export const schedules = {
  list: (projectSlug: string) => req<any[]>(`/schedules?project=${projectSlug}`),
  create: (data: CreateScheduleRequest) => req<{ id: string }>("/schedules", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: Partial<CreateScheduleRequest>) => req<{ id: string }>(`/schedules/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  remove: (id: string) => req(`/schedules/${id}`, { method: "DELETE" }),
  pause: (id: string) => req(`/schedules/${id}/pause`, { method: "POST" }),
  resume: (id: string) => req(`/schedules/${id}/resume`, { method: "POST" }),
};

// ── GitHub ────────────────────────────────────────────────────────────────────

export const github = {
  publish: (data: { project_slug: string; files: { path: string; content: string }[]; commit_message?: string }) =>
    req<{ published: number; files: any[] }>("/github/publish", { method: "POST", body: JSON.stringify(data) }),
};

// ── Execute ───────────────────────────────────────────────────────────────────

export type ExecuteResult = {
  stdout: string;
  stderr: string;
  dataframes: Record<string, { columns: string[]; rows: Record<string, unknown>[]; rowCount: number }>;
  figures: string[];   // base64 PNG strings
  error: string | null;
};

export const execute = {
  run: (code: string, timeout = 60) =>
    req<ExecuteResult>("/execute", { method: "POST", body: JSON.stringify({ code, timeout }) }),
};

export const storage = {
  upload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/storage/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`API ${res.status}: ${text}`);
    }
    return res.json() as Promise<{ filename: string; storageKey: string; size: number }>;
  },
};

// ── Agent ─────────────────────────────────────────────────────────────────────

export type AgentEvent =
  | { type: "text_delta";   content: string }
  | { type: "tool_call";    id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_result";  id: string; name: string; result: unknown }
  | { type: "done";         new_messages: { role: string; content: string }[] }
  | { type: "error";        message: string }
  | { type: "context_snapshot"; data: any };

export type ModelInfo = { id: string; label: string };

export const agent = {
  models: () => req<{ models: ModelInfo[]; default: string }>("/agent/models"),

  /** Returns an async generator that yields AgentEvent objects. */
  chat: async function* (
    message: string,
    history: { role: string; content: string }[] = [],
    model?: string,
    projectSlug?: string,
  ): AsyncGenerator<AgentEvent> {
    const params = new URLSearchParams();
    if (projectSlug) params.set("project", projectSlug);
    const qs = params.size ? `?${params}` : "";

    const response = await fetch(`${API_BASE}/agent/chat${qs}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history, model, project_id: projectSlug }),
    });
    if (!response.ok || !response.body) {
      throw new Error(`Agent API ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (line.startsWith("data: ")) {
          try {
            yield JSON.parse(line.slice(6)) as AgentEvent;
          } catch { /* skip malformed */ }
        }
      }
    }
  },

  inferSchema: (sample?: string, description?: string, model?: string) =>
    req<{ api_yaml: string; ontology_yaml: string; explanation: string; raw: string }>(
      "/agent/infer-schema",
      { method: "POST", body: JSON.stringify({ sample, description, model }) }
    ),
};

// ── Questions ─────────────────────────────────────────────────────────────────

export type QuestionEvent =
  | { type: "text_delta";   content: string }
  | { type: "tool_call";    id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_result";  id: string; name: string; result: unknown }
  | { type: "done" }
  | { type: "error";        message: string };

export const questions = {
  ask: async function* (
    question: string,
    projectId?: string,
    model?: string,
  ): AsyncGenerator<QuestionEvent> {
    const res = await fetch(`${API_BASE}/questions/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, project_id: projectId, model }),
    });
    if (!res.ok || !res.body) throw new Error(`Questions API ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (line.startsWith("data: ")) {
          try { yield JSON.parse(line.slice(6)) as QuestionEvent; } catch { /* skip */ }
        }
      }
    }
  },
};

// ── Context / Knowledge Base ──────────────────────────────────────────────────

export const projects = {
  context: (slug: string) => req<any>(`/projects/${slug}/context`),
  /** Point Convex project at paths from a successful hydration job (fixes 428 without re-running the pipeline). */
  registerArtifacts: (
    slug: string,
    jobId?: string,
    paths?: { output_db_path?: string; output_owl_path?: string },
  ) => {
    const q = jobId ? `?jobId=${encodeURIComponent(jobId)}` : "";
    const hasPaths = paths && (paths.output_db_path || paths.output_owl_path);
    return req<{ ok: boolean; jobId: string | null; activeOntologyDbPath: string; activeOntologyDuckdbPath: string }>(
      `/projects/${encodeURIComponent(slug)}/register-artifacts${q}`,
      hasPaths ? { method: "POST", body: JSON.stringify(paths) } : { method: "POST" },
    );
  },
};

export const context = {
  uploadFile: async (file: File, projectId?: string, name?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (projectId) form.append("project_id", projectId);
    if (name)      form.append("name", name);
    const res = await fetch(`${API_BASE}/context/upload`, { method: "POST", body: form });
    if (!res.ok) { const t = await res.text(); throw new Error(t); }
    return res.json();
  },

  addUrl: (url: string, name?: string, projectId?: string) =>
    req("/context/url", { method: "POST", body: JSON.stringify({ url, name, project_id: projectId }) }),

  addText: (name: string, content: string, projectId?: string) =>
    req("/context/text", { method: "POST", body: JSON.stringify({ name, content, project_id: projectId }) }),

  list: (projectId?: string) =>
    req<any[]>(`/context/list${projectId ? `?project_id=${projectId}` : ""}`),

  remove: (id: string) =>
    req(`/context/${id}`, { method: "DELETE" }),
};


// ── Quality ───────────────────────────────────────────────────────────────────

export const quality = {
  report: (projectId?: string) =>
    req<any>(`/quality/report${projectId ? `?project_id=${projectId}` : ""}`),

  snapshot: (projectId?: string, label?: string) =>
    req<any>("/quality/snapshot", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, label }),
    }),

  diff: (projectId?: string) =>
    req<any>(`/quality/diff${projectId ? `?project_id=${projectId}` : ""}`),
};
