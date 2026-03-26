"use client";

import { use, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "convex/react";
import { Id } from "@/convex/_generated/dataModel";
import { api } from "@/convex/_generated/api";
import { AlertCircle, ArrowRight, Loader2, Square } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

const STATUS_COLORS: Record<string, string> = {
  queued: "#8b949e",
  running: "#58a6ff",
  success: "#3fb950",
  failed: "#f85149",
  cancelled: "#8b949e",
};

const STEP_STATUS_COLORS: Record<string, string> = {
  pending: "#8b949e",
  running: "#58a6ff",
  done: "#3fb950",
  failed: "#f85149",
};

function formatDate(ms?: number) {
  if (!ms) return "—";
  return new Date(ms).toLocaleString();
}

function formatDuration(start?: number, end?: number) {
  if (!start) return "—";
  const diff = (end ?? Date.now()) - start;
  if (diff < 1000) return `${diff}ms`;
  if (diff < 60_000) return `${(diff / 1000).toFixed(1)}s`;
  return `${(diff / 60_000).toFixed(1)}m`;
}

export default function JobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const jobId = id as Id<"hydrationJobs">;
  const job = useQuery(api.jobs.get, { jobId });
  const logs = useQuery(api.jobs.getLogs, { jobId, limit: 500 });

  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState("");
  const logContainerRef = useRef<HTMLDivElement>(null);
  const shouldStickToBottomRef = useRef(true);

  useEffect(() => {
    const node = logContainerRef.current;
    if (!node || !logs) return;
    if (shouldStickToBottomRef.current) {
      node.scrollTop = node.scrollHeight;
    }
  }, [logs]);

  const sortedLogs = useMemo(() => {
    return [...(logs ?? [])].sort((a, b) => a.seq - b.seq);
  }, [logs]);

  async function handleCancel() {
    setCancelling(true);
    setCancelError("");
    try {
      const res = await fetch(`${API_BASE}/jobs/${jobId}`, { method: "DELETE" });
      if (!res.ok) {
        throw new Error(await res.text());
      }
    } catch (error) {
      setCancelError(error instanceof Error ? error.message : "Failed to cancel job");
    } finally {
      setCancelling(false);
    }
  }

  if (job === undefined || logs === undefined) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-[--muted-foreground]">
        Loading job…
      </div>
    );
  }

  if (!job) {
    return (
      <div className="space-y-4">
        <Link href="/jobs" className="text-sm text-[--primary] hover:underline">
          ← Back to Jobs
        </Link>
        <div className="rounded-lg border border-red-700 bg-red-900/20 p-4 text-sm text-red-300">
          Job not found.
        </div>
      </div>
    );
  }

  const canCancel = job.status === "queued" || job.status === "running";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <Link href="/jobs" className="text-sm text-[--primary] hover:underline">
            ← Back to Jobs
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="font-mono text-xl text-[--foreground]">{job.pipelineSlug}</h1>
            <span
              className="px-2.5 py-0.5 rounded-full text-xs font-medium"
              style={{
                color: STATUS_COLORS[job.status],
                background: `${STATUS_COLORS[job.status]}22`,
                border: `1px solid ${STATUS_COLORS[job.status]}44`,
              }}
            >
              {job.status}
            </span>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-[--muted-foreground]">
            <span>Started: {formatDate(job.startedAt ?? job.createdAt)}</span>
            <span>Finished: {formatDate(job.finishedAt)}</span>
            <span>Duration: {formatDuration(job.startedAt ?? job.createdAt, job.finishedAt)}</span>
          </div>
        </div>

        {canCancel && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="inline-flex items-center gap-2 rounded-lg border border-red-700/60 bg-red-900/20 px-3 py-2 text-sm text-red-300 hover:bg-red-900/30 disabled:opacity-50"
          >
            {cancelling ? <Loader2 size={14} className="animate-spin" /> : <Square size={12} />}
            Cancel
          </button>
        )}
      </div>

      {job.status === "failed" && job.errorMessage && (
        <div className="flex items-start gap-3 rounded-xl border border-red-700 bg-red-900/20 p-4 text-sm text-red-300">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">Job failed</p>
            <p className="mt-1 whitespace-pre-wrap">{job.errorMessage}</p>
          </div>
        </div>
      )}

      {cancelError && (
        <div className="rounded-lg border border-red-700 bg-red-900/20 p-3 text-sm text-red-300">
          {cancelError}
        </div>
      )}

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[--muted-foreground]">
            Step Timeline
          </h2>
          <span className="text-xs text-[--muted-foreground]">
            {job.stepResults.filter((step) => step.status === "done").length}/{job.stepResults.length} complete
          </span>
        </div>
        <div className="grid gap-3">
          {job.stepResults.length === 0 && (
            <div className="rounded-lg border border-[--border] bg-[--card] p-4 text-sm text-[--muted-foreground]">
              No step data yet.
            </div>
          )}
          {job.stepResults.map((step) => (
            <div key={step.stepName} className="rounded-xl border border-[--border] bg-[--card] p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-block h-2.5 w-2.5 rounded-full ${step.status === "running" ? "animate-pulse" : ""}`}
                      style={{ background: STEP_STATUS_COLORS[step.status] }}
                    />
                    <p className="font-medium text-[--foreground]">{step.stepName}</p>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[--muted-foreground]">
                    <span>Status: {step.status}</span>
                    <span>Rows: {step.rowCount ?? "—"}</span>
                    <span>Duration: {formatDuration(step.startedAt, step.finishedAt)}</span>
                  </div>
                </div>
                <span
                  className="rounded-full px-2 py-0.5 text-xs font-medium"
                  style={{
                    color: STEP_STATUS_COLORS[step.status],
                    background: `${STEP_STATUS_COLORS[step.status]}22`,
                    border: `1px solid ${STEP_STATUS_COLORS[step.status]}44`,
                  }}
                >
                  {step.status}
                </span>
              </div>
              {step.errorMessage && (
                <div className="mt-3 rounded-lg border border-red-700/60 bg-red-900/20 p-3 text-sm text-red-300">
                  {step.errorMessage}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[--muted-foreground]">
            Logs
          </h2>
          <span className="text-xs text-[--muted-foreground]">{sortedLogs.length} lines</span>
        </div>
        <div
          ref={logContainerRef}
          onScroll={(event) => {
            const node = event.currentTarget;
            const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
            shouldStickToBottomRef.current = distanceFromBottom < 48;
          }}
          className="max-h-[480px] overflow-y-auto rounded-xl border border-[--border] bg-[#0d1117] p-3 font-mono text-xs"
        >
          {sortedLogs.length === 0 && (
            <div className="space-y-2 text-[--muted-foreground]">
              <p>No log lines in Convex yet.</p>
              {(job.status === "queued" || job.status === "running") && (
                <p className="text-[11px] leading-relaxed">
                  Logs are written by the <strong className="text-[--foreground]">FastAPI</strong> process
                  (hydration worker) into this Convex deployment. If this stays empty: confirm{" "}
                  <code className="text-[--foreground]">NEXT_PUBLIC_CONVEX_URL</code> in{" "}
                  <code className="text-[--foreground]">.env.local</code> matches{" "}
                  <code className="text-[--foreground]">CONVEX_URL</code> in the repo{" "}
                  <code className="text-[--foreground]">.env</code>, and check the API terminal for{" "}
                  <code className="text-[--foreground]">rail.hydration</code> lines (especially Convex{" "}
                  <code className="text-[--foreground]">appendLog</code> errors).
                </p>
              )}
              {job.status === "failed" && job.errorMessage && (
                <p className="text-[11px] text-red-300/90">
                  See <strong>Error</strong> above — the worker may have failed before any line was stored.
                </p>
              )}
            </div>
          )}
          <div className="space-y-1">
            {sortedLogs.map((log) => {
              const color =
                log.level === "error" ? "text-red-300" :
                log.level === "warn" ? "text-yellow-300" :
                "text-[--foreground]";

              return (
                <div key={log._id} className={`break-words ${color}`}>
                  <span className="text-[--muted-foreground]">
                    {new Date(log.timestamp).toLocaleTimeString()}{" "}
                  </span>
                  {log.stepName && (
                    <span className="mr-2 rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-[--muted-foreground]">
                      {log.stepName}
                    </span>
                  )}
                  <span>{log.message}</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {job.status === "success" && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[--muted-foreground]">
            Outputs
          </h2>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/explorer"
              className="inline-flex items-center gap-2 rounded-lg border border-[--border] bg-[--card] px-3 py-2 text-sm text-[--foreground] hover:border-[--primary]/40 hover:text-[--primary]"
            >
              Explore Data <ArrowRight size={14} />
            </Link>
            <Link
              href="/sql"
              className="inline-flex items-center gap-2 rounded-lg border border-[--border] bg-[--card] px-3 py-2 text-sm text-[--foreground] hover:border-[--primary]/40 hover:text-[--primary]"
            >
              Open SQL <ArrowRight size={14} />
            </Link>
            <Link
              href="/workspace"
              className="inline-flex items-center gap-2 rounded-lg border border-[--border] bg-[--card] px-3 py-2 text-sm text-[--foreground] hover:border-[--primary]/40 hover:text-[--primary]"
            >
              Open in Workspace <ArrowRight size={14} />
            </Link>
          </div>
          <div className="grid gap-2 text-xs text-[--muted-foreground]">
            <p>DuckDB: {job.outputDbPath ?? "—"}</p>
            <p>OWL: {job.outputOwlPath ?? "—"}</p>
          </div>
        </section>
      )}
    </div>
  );
}
