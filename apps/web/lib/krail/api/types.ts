/** RAIL-owned HTTP shapes. KRAIL runtime dictionaries never enter UI code directly. */

export interface ApiErrorShape {
  error?: {
    code?: string;
    message?: string;
    requestId?: string;
    details?: Record<string, unknown>;
  };
}

export interface ApiError {
  code: string;
  message: string;
  requestId?: string;
  status?: number;
  details?: Record<string, unknown>;
}

export type Resource<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "empty"; message: string }
  | { state: "unavailable"; message: string }
  | { state: "error"; error: ApiError };

export interface GitMetadata {
  isRepository: boolean;
  repositoryRoot?: string | null;
  headCommit?: string | null;
  branch?: string | null;
  isDirty: boolean;
  baselineCommit?: string | null;
}

export interface Project {
  projectId: string;
  displayName: string;
  canonicalPath: string;
  workspaceMode: "managed" | "linked_local" | string;
  access: "read_only" | "read_write" | string;
  git: GitMetadata;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectListResponse { projects: Project[] }

export interface ProjectHealth {
  ok: boolean;
  checks: Array<{ name: string; ok: boolean; detail: string }>;
  warnings: string[];
  krailVersion: string;
}

export interface ProjectHealthResponse { projectId: string; health: ProjectHealth }

export interface ProjectManifest {
  version: number;
  slug: string;
  name: string;
  defaultBranch: string;
  knowledgeMode: string;
  paths: Record<string, string>;
}

export interface ProjectManifestResponse { projectId: string; manifest: ProjectManifest }

export interface SourceRecord {
  id: string;
  kind: string;
  path?: string | null;
  url?: string | null;
  documents: string[];
  metadata: Record<string, unknown>;
}

/** M3 nests canonical adapter fields without changing their snake_case names. */
export interface SourceInventory { manifest_path?: string | null; sources: SourceRecord[] }

export interface SourcesResponse { projectId: string; inventory: SourceInventory }

export interface FindResult {
  query: string;
  items: Array<{ id: string; kind: string; title: string; path?: string | null; score?: number | null; snippet?: string | null; metadata: Record<string, unknown> }>;
  total: number;
  facets: Record<string, unknown>;
  explanation?: Record<string, unknown> | null;
}

export interface FindResponse { projectId: string; result: FindResult }

export interface FindRequest {
  text: string;
  limit?: number;
  types?: string[];
  topic?: string;
  entity?: string;
  status?: string;
  freshness?: string;
  workflow?: string;
  explain?: boolean;
}

export interface GraphNode { id: string; label: string; kind: string; metadata: Record<string, unknown> }
export interface GraphEdge { id: string; source: string; target: string; relation: string; metadata: Record<string, unknown> }
export interface GraphDocument { id: string; path: string; title: string; kind: string; topics: string[]; entities: string[] }
export interface GraphResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  documents: GraphDocument[];
  counts: Record<string, number>;
  warnings: string[];
}
export interface GraphResponse { projectId: string; graph: GraphResult }

export interface SourceCheck { status: string; changed_source_ids: string[]; errors: string[] }
export interface SourceCheckResponse { projectId: string; check: SourceCheck }
export interface SourceImpact { source_ids: string[]; documents: string[] }
export interface SourceImpactResponse { projectId: string; impact: SourceImpact }

export interface IntegritySummary {
  status: string;
  sources: number;
  claims: number;
  assumptions: number;
  artifacts: number;
  verification_runs: number;
  details: Record<string, unknown>;
}
export interface IntegrityResponse { projectId: string; integrity: IntegritySummary }

export interface Workflow { id: string; path?: string | null; valid?: boolean | null; steps?: number | null; status?: string | null; metadata: Record<string, unknown> }
export interface WorkflowInventory { workflows: Workflow[]; pack?: string | null; mode?: string | null }
export interface WorkflowInventoryResponse { projectId: string; inventory: WorkflowInventory }

export interface Approval { id: string; status?: string | null; description?: string | null; workflow_run_id?: string | null; workflow_step_id?: string | null; metadata: Record<string, unknown> }
export interface ApprovalInventory { approvals: Approval[] }
export interface ApprovalInventoryResponse { projectId: string; inventory: ApprovalInventory }
export interface ApprovalResponse { projectId: string; approval: Approval }
