"use client";

/** Browser-only M4 run control boundary. Durable workflow truth remains in KRAIL. */

export type RunStatus = "queued" | "running" | "waiting_approval" | "succeeded" | "failed" | "cancelled" | string;

export type WorkflowRun = {
  runId: string;
  projectId: string;
  workflowId: string | null;
  status: RunStatus;
  dryRun: boolean;
  permissionProfile: string;
  createdAt: string;
  updatedAt: string;
  result: Record<string, unknown>;
};

export type RunEvent = {
  eventId: string;
  runId: string;
  kind: string;
  message: string;
  at: string;
  data: Record<string, unknown>;
};

export type RunRequest = {
  workflowId: string;
  dryRun: boolean;
  force: boolean;
  inputs: Record<string, unknown>;
  permissionProfile?: string;
};

export type ApiFailure = Error & { code?: string; requestId?: string; status?: number };

const DEFAULT_API_ROOT = "http://127.0.0.1:8000/api/v1";
const terminalStatuses = new Set(["succeeded", "failed", "cancelled"]);

function apiRoot() {
  return (process.env.NEXT_PUBLIC_KRAIL_API_URL ?? process.env.NEXT_PUBLIC_RAIL_API_URL ?? DEFAULT_API_ROOT).replace(/\/$/, "");
}

function runPath(projectId: string, suffix = "") {
  return `${apiRoot()}/projects/${encodeURIComponent(projectId)}/runs${suffix}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers: { accept: "application/json", "content-type": "application/json", ...init?.headers } });
  } catch {
    throw failure("network_error", "The KRAIL platform API could not be reached.");
  }
  const payload = await response.json().catch(() => undefined) as { error?: { code?: string; message?: string; requestId?: string } } | undefined;
  if (!response.ok) throw failure(payload?.error?.code ?? "http_error", payload?.error?.message ?? `Request failed (${response.status}).`, payload?.error?.requestId ?? response.headers.get("x-request-id") ?? undefined, response.status);
  return payload as T;
}

function failure(code: string, message: string, requestId?: string, status?: number): ApiFailure {
  const error = new Error(message) as ApiFailure;
  error.code = code; error.requestId = requestId; error.status = status;
  return error;
}

export const isTerminal = (status: RunStatus) => terminalStatuses.has(status);

export async function listRuns(projectId: string) {
  return (await request<{ runs: WorkflowRun[] }>(runPath(projectId))).runs;
}

export async function createRun(projectId: string, body: RunRequest) {
  return (await request<{ run: WorkflowRun }>(runPath(projectId), { method: "POST", body: JSON.stringify(body) })).run;
}

export async function cancelRun(projectId: string, runId: string) {
  return (await request<{ run: WorkflowRun }>(runPath(projectId, `/${encodeURIComponent(runId)}/cancel`), { method: "POST" })).run;
}

export async function snapshotEvents(projectId: string, runId: string) {
  return (await request<{ events: RunEvent[] }>(runPath(projectId, `/${encodeURIComponent(runId)}/events`))).events;
}

/** EventSource preserves Last-Event-ID across automatic reconnects; snapshots close any gap on mount. */
export function streamEvents(projectId: string, runId: string, handlers: { onEvent: (event: RunEvent) => void; onConnection: (connected: boolean) => void; onError: () => void }) {
  const source = new EventSource(runPath(projectId, `/${encodeURIComponent(runId)}/events/stream`));
  source.onopen = () => handlers.onConnection(true);
  source.onerror = () => { handlers.onConnection(false); handlers.onError(); };
  source.onmessage = (message) => receive(message.data, handlers.onEvent);
  ["queued", "running", "waiting_approval", "succeeded", "failed", "cancelled", "progress", "stdout", "stderr"].forEach((kind) => {
    source.addEventListener(kind, (message) => receive((message as MessageEvent<string>).data, handlers.onEvent));
  });
  return () => source.close();
}

function receive(raw: string, onEvent: (event: RunEvent) => void) {
  try { onEvent(JSON.parse(raw) as RunEvent); } catch { /* Ignore malformed stream frames; the durable snapshot remains authoritative. */ }
}
