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

/** Planned M3 read contracts. These methods remain at one boundary until M3 mounts them. */
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
