import "server-only";

import { KrailApiClientError } from "@/lib/krail/api";

export const MAX_QUERY_ROWS = 1_000;
export const MAX_SQL_LENGTH = 10_000;

export type QueryColumn = { name: string; type?: string | null };
export type QuerySource = { id: string; kind?: string; path?: string | null; url?: string | null };
export type QueryResult = {
  sql: string;
  columns: QueryColumn[];
  rows: unknown[][];
  rowCount: number;
  truncated: boolean;
  sourceIds: string[];
  sources: QuerySource[];
  metadata: Record<string, unknown>;
  requestId?: string;
  fetchedAt: string;
};

type RawObject = Record<string, unknown>;

function object(value: unknown): RawObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RawObject : {};
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function column(value: unknown, index: number): QueryColumn {
  if (typeof value === "string") return { name: value };
  const raw = object(value);
  return { name: text(raw.name) ?? text(raw.field) ?? `column_${index + 1}`, type: text(raw.type) ?? text(raw.dataType) ?? null };
}

function rows(value: unknown, columns: QueryColumn[]): unknown[][] {
  if (!Array.isArray(value)) return [];
  return value.map((row) => {
    if (Array.isArray(row)) return row;
    const record = object(row);
    return columns.map(({ name }) => record[name] ?? null);
  });
}

function sources(value: unknown): QuerySource[] {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => {
    const raw = object(entry);
    return { id: text(raw.id) ?? text(raw.sourceId) ?? "unknown-source", kind: text(raw.kind), path: text(raw.path) ?? null, url: text(raw.url) ?? null };
  }).filter((entry) => entry.id !== "unknown-source");
}

/**
 * Maps only the public query response into a display model. KRAIL remains the
 * owner of query execution, result limits, and any artifact/source lineage.
 */
function normalize(payload: unknown, requestId: string | undefined, requestedSql: string): QueryResult {
  const root = object(payload);
  const result = object(root.result ?? root.query ?? payload);
  const rawColumns = Array.isArray(result.columns) ? result.columns : Array.isArray(root.columns) ? root.columns : [];
  const normalizedColumns = rawColumns.map(column);
  const rawRows = result.rows ?? result.data ?? root.rows ?? root.data;
  const normalizedRows = rows(rawRows, normalizedColumns);
  const rawSources = sources(result.sources ?? root.sources);
  const rawSourceIds = Array.isArray(result.sourceIds) ? result.sourceIds : Array.isArray(root.sourceIds) ? root.sourceIds : [];
  const sourceIds = Array.from(new Set([...rawSourceIds.filter((id): id is string => typeof id === "string"), ...rawSources.map((source) => source.id)])).sort();
  const rowCount = typeof result.rowCount === "number" ? result.rowCount : typeof root.rowCount === "number" ? root.rowCount : normalizedRows.length;
  const metadata = object(result.metadata ?? root.metadata);
  return {
    sql: text(result.sql) ?? text(root.sql) ?? requestedSql,
    columns: normalizedColumns,
    rows: normalizedRows,
    rowCount,
    truncated: result.truncated === true || root.truncated === true || rowCount > normalizedRows.length,
    sourceIds,
    sources: rawSources,
    metadata,
    requestId,
    fetchedAt: new Date().toISOString(),
  };
}

function apiBaseUrl(): string {
  const configured = process.env.KRAIL_API_BASE_URL?.trim() || "http://127.0.0.1:8000";
  try {
    const url = new URL(configured);
    if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("unsupported protocol");
    return url.toString().replace(/\/$/, "");
  } catch {
    throw new Error("KRAIL_API_BASE_URL must be an absolute http(s) URL.");
  }
}

export async function executeProjectQuery(projectId: string, sql: string, limit: number): Promise<QueryResult> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/projects/${encodeURIComponent(projectId)}/query`, {
    method: "POST",
    cache: "no-store",
    headers: { accept: "application/json", "content-type": "application/json" },
    body: JSON.stringify({ sql, limit }),
  }).catch((cause: unknown) => {
    throw new KrailApiClientError("network_error", "The KRAIL platform API could not be reached.", undefined, undefined, { cause: String(cause) });
  });
  const requestId = response.headers.get("x-request-id") ?? undefined;
  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    const error = object(object(payload).error);
    throw new KrailApiClientError(text(error.code) ?? "http_error", text(error.message) ?? `Query failed (${response.status}).`, text(error.requestId) ?? requestId, response.status, object(error.details));
  }
  if (payload === undefined) throw new KrailApiClientError("invalid_response", "The KRAIL platform API returned invalid JSON.", requestId, response.status);
  return normalize(payload, requestId, sql);
}

export function capabilityMessage(error: unknown): string | undefined {
  if (!(error instanceof KrailApiClientError)) return undefined;
  if (error.status === 404 || error.status === 405 || error.status === 501 || error.code === "capability_unavailable") {
    return "SQL query is not available for this KRAIL project or API version. RAIL did not run a local or legacy fallback.";
  }
  return undefined;
}
