"use client";

import { use, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "convex/react";
import { Id } from "@/convex/_generated/dataModel";
import { api } from "@/convex/_generated/api";
import { AlertCircle, ArrowRight, Link2, Loader2, Square } from "lucide-react";
import { toast } from "sonner";
import { ToolResult } from "@/components/jobs/ToolResult";
import { countPipelineStepsFromSpec, hydrationStepProgress } from "@/lib/pipeline-steps";
import { projects } from "@/lib/api";

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
  params: Promise<{ project: string; id: string }>;
}) {
  const { project, id } = use(params);
  const job = useQuery(api.jobs.get, { jobId: id as Id<"hydrationJobs"> });
  const execution = useQuery((api as any).executions.get, { jobId: id as any });
  const pipelineConfig = useQuery(
    api.configs.getPipeline,
    job && !execution && job.pipelineSlug ? { slug: job.pipelineSlug } : "skip",
  );

  /** Both queries must settle — execution is often `null` for hydration IDs, which is not "missing job". */
  const queriesPending = job === undefined || execution === undefined;
  const activeJob = job || execution;
  const isExecution = !!execution;
  
  const jobId = id;
  const logs = useQuery(api.jobs.getLogs, { jobId, limit: 1000 });

  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState("");
  const [linkingArtifacts, setLinkingArtifacts] = useState(false);
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

  const hydrationSteps = useMemo(() => {
    if (!job || execution) return null;
    const specTotal = countPipelineStepsFromSpec(pipelineConfig?.parsedSpec);
    return hydrationStepProgress(job.stepResults, specTotal);
  }, [job, execution, pipelineConfig]);

  async function handleLinkArtifactsToProject() {
    if (!job?.outputDbPath) {
      toast.error("This job has no stored database path yet.");
      return;
    }
    setLinkingArtifacts(true);
    try {
      await projects.registerArtifacts(project, jobId, {
        output_db_path: job.outputDbPath,
        ...(job.outputOwlPath ? { output_owl_path: job.outputOwlPath } : {}),
      });
      toast.success("Artifacts linked to this project. Graph and SQL should load without 428.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not link artifacts");
    } finally {
      setLinkingArtifacts(false);
    }
  }

  async function handleCancel() {
    setCancelling(true);
    setCancelError("");
    try {
      const endpoint = isExecution ? `${API_BASE}/jobs/executions/${jobId}/interrupt` : `${API_BASE}/jobs/${jobId}`;
      const res = await fetch(endpoint, { method: "DELETE" });
      if (!res.ok) {
        throw new Error(await res.text());
      }
    } catch (error) {
      setCancelError(error instanceof Error ? error.message : "Failed to cancel job");
    } finally {
      setCancelling(false);
    }
  }

  if (queriesPending) {
    return (
      <div className="space-y-4 p-6">
        <div className="h-4 w-48 animate-pulse rounded bg-[--muted]" />
        <div className="h-32 animate-pulse rounded-xl border border-[--border] bg-[--muted]/30" />
      </div>
    );
  }

  if (!activeJob) {
    return (
      <div className="space-y-4">
        <Link href={`/${project}/jobs`} className="text-sm text-[--primary] hover:underline">
          ← Back to Jobs
        </Link>
        <div className="rounded-lg border border-red-700 bg-red-900/20 p-4 text-sm text-red-300">
          Job not found.
        </div>
      </div>
    );
  }

  const jobData = activeJob;
  const canCancel = jobData.status === "queued" || jobData.status === "running";

  return (
    <div className="flex flex-col gap-8 max-w-6xl mx-auto w-full p-10 pb-20">
      <div className="flex flex-col gap-4">
        <Link 
          href={`/${project}/jobs`} 
          className="group inline-flex items-center gap-2 text-xs font-medium text-[--muted-foreground] hover:text-[--primary] transition-colors"
        >
          <div className="flex h-5 w-5 items-center justify-center rounded-md bg-[--muted]/50 group-hover:bg-[--primary]/10 transition-colors">
            <ArrowRight className="rotate-180" size={12} />
          </div>
          Back to Project Activity
        </Link>
        
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-[--foreground]">
                {isExecution ? `Execution: ${(execution as any).type.toUpperCase()}` : (job as any)?.pipelineSlug}
              </h1>
              <div
                className="px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider"
                style={{
                  color: STATUS_COLORS[jobData.status],
                  background: `${STATUS_COLORS[jobData.status]}15`,
                  border: `1px solid ${STATUS_COLORS[jobData.status]}30`,
                }}
              >
                {jobData.status}
              </div>
            </div>
            <div className="flex items-center gap-4 text-xs text-[--muted-foreground]">
              <span className="flex items-center gap-1.5">
                <span className="h-1 w-1 rounded-full bg-[--muted-foreground]/40" />
                Started {formatDate(jobData.startedAt ?? jobData.createdAt)}
              </span>
              {jobData.finishedAt && (
                <span className="flex items-center gap-1.5">
                  <span className="h-1 w-1 rounded-full bg-[--muted-foreground]/40" />
                  Finished {formatDate(jobData.finishedAt)}
                </span>
              )}
              <span className="flex items-center gap-1.5">
                <span className="h-1 w-1 rounded-full bg-[--muted-foreground]/40" />
                Duration: {formatDuration(jobData.startedAt ?? jobData.createdAt, jobData.finishedAt)}
              </span>
            </div>
          </div>

          {canCancel && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="inline-flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-xs font-semibold text-red-400 hover:bg-red-500/20 transition-all disabled:opacity-50"
            >
              {cancelling ? <Loader2 size={14} className="animate-spin" /> : <Square size={12} />}
              Stop Execution
            </button>
          )}
        </div>
      </div>

      {jobData.status === "failed" && jobData.errorMessage && (
        <div className="flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/5 p-5 text-sm text-red-400 backdrop-blur-md">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div className="space-y-1">
            <p className="font-bold uppercase text-[10px] tracking-widest opacity-70">Fatal Error</p>
            <p className="font-medium whitespace-pre-wrap leading-relaxed">{jobData.errorMessage}</p>
          </div>
        </div>
      )}

      {cancelError && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-400 animate-in fade-in slide-in-from-top-1">
          {cancelError}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          {!isExecution && job && (
            <section className="space-y-4">
              <div className="flex items-center justify-between px-1">
                <div className="space-y-0.5">
                   <h2 className="text-xs font-bold uppercase tracking-widest text-[--muted-foreground]">
                    Pipeline Execution Timeline
                  </h2>
                </div>
                <span className="text-[11px] font-medium text-[--muted-foreground] bg-[--muted]/50 px-2 py-0.5 rounded-full">
                  {hydrationSteps
                    ? `${hydrationSteps.done}/${hydrationSteps.total} Steps`
                    : `${job.stepResults.filter((step) => step.status === "done").length}/${job.stepResults.length} Steps`}
                </span>
              </div>
              <div className="grid gap-3">
                {job.stepResults.length === 0 && (
                  <div className="rounded-xl border border-[--border] bg-[--card]/40 backdrop-blur-xl p-8 text-center">
                    <Loader2 className="mx-auto mb-3 animate-spin text-[--muted-foreground]" size={20} />
                    <p className="text-sm text-[--muted-foreground] italic">Initializing processing engine...</p>
                  </div>
                )}
                {job.stepResults.map((step) => (
                  <div key={step.stepName} className="group relative overflow-hidden rounded-xl border border-[--border] bg-[--card]/40 backdrop-blur-xl p-4 hover:border-[--primary]/30 transition-all transition-colors">
                    <div className="flex items-start justify-between gap-4 relative z-10">
                      <div className="space-y-2">
                        <div className="flex items-center gap-3">
                          <div 
                            className="flex h-2.5 w-2.5 rounded-full shadow-[0_0_8px_rgba(var(--primary-rgb),0.4)]"
                            style={{ 
                              background: STEP_STATUS_COLORS[step.status],
                              boxShadow: step.status === "running" ? `0 0 12px ${STEP_STATUS_COLORS[step.status]}88` : "none"
                            }}
                          />
                          <p className="font-semibold text-sm text-[--foreground] tracking-tight">{step.stepName}</p>
                        </div>
                        <div className="flex items-center gap-4 text-[11px] font-medium text-[--muted-foreground]">
                          <span className="flex items-center gap-1 capitalize opacity-80">{step.status}</span>
                          {step.rowCount !== undefined && (
                             <span className="flex items-center gap-1.5">
                               <span className="h-1 w-1 rounded-full bg-[--muted-foreground]/30" />
                               {step.rowCount.toLocaleString()} entities
                             </span>
                          )}
                          <span className="flex items-center gap-1.5">
                            <span className="h-1 w-1 rounded-full bg-[--muted-foreground]/30" />
                            {formatDuration(step.startedAt, step.finishedAt)}
                          </span>
                        </div>
                      </div>
                      <div
                        className="rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                        style={{
                          color: STEP_STATUS_COLORS[step.status],
                          background: `${STEP_STATUS_COLORS[step.status]}10`,
                          border: `1px solid ${STEP_STATUS_COLORS[step.status]}20`,
                        }}
                      >
                        {step.status}
                      </div>
                    </div>
                    {step.errorMessage && (
                      <div className="mt-3 rounded-lg border border-red-500/10 bg-red-500/5 p-3 text-[11px] text-red-400 leading-relaxed font-mono">
                        {step.errorMessage}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {isExecution && execution && (
            <section className="space-y-4">
               <h2 className="text-xs font-bold uppercase tracking-widest text-[--muted-foreground] px-1">
                Instruction Payload
              </h2>
              <div className="rounded-xl border border-[--border] bg-black/40 p-4 font-mono text-[13px] leading-relaxed text-[--foreground] backdrop-blur-xl">
                <pre className="whitespace-pre-wrap">{execution.input}</pre>
              </div>
            </section>
          )}

          <section className="space-y-4">
            <div className="flex items-center justify-between px-1">
               <h2 className="text-xs font-bold uppercase tracking-widest text-[--muted-foreground]">
                Live Runtime Stream
              </h2>
              <span className="text-[10px] font-mono font-bold text-[--muted-foreground] opacity-60 uppercase">
                {sortedLogs.length} Lines Buffered
              </span>
            </div>
            <div
              ref={logContainerRef}
              onScroll={(event) => {
                const node = event.currentTarget;
                const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
                shouldStickToBottomRef.current = distanceFromBottom < 48;
              }}
              className="h-[500px] overflow-y-auto rounded-xl border border-[--border] bg-[--background]/60 backdrop-blur-xl p-4 font-mono text-[11px] leading-6 scrollbar-thin scrollbar-thumb-[--border]"
            >
              {sortedLogs.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full space-y-3 text-[--muted-foreground] opacity-40">
                  <Loader2 className="animate-spin" size={24} />
                  <p className="text-sm italic tracking-tight">Awaiting stream from worker node...</p>
                </div>
              )}
              <div className="space-y-0.5">
                {sortedLogs.map((log) => {
                  const color =
                    log.level === "error" || log.level === "stderr" ? "text-red-400" :
                    log.level === "warn" ? "text-amber-400" :
                    log.level === "stdout" ? "text-blue-400" :
                    "text-[--foreground]/80";

                  return (
                    <div key={log._id} className="group flex gap-4 hover:bg-white/[0.02] transition-colors -mx-2 px-2 rounded">
                      <span className="shrink-0 text-[--muted-foreground]/40 tabular-nums">
                        {new Date(log.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                      <div className="flex flex-col gap-0.5 min-w-0">
                        <div className={`break-all ${color}`}>
                          {log.stepName && (
                            <span className="mr-3 rounded-md bg-[--muted]/40 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[--muted-foreground] border border-[--border]">
                              {log.stepName}
                            </span>
                          )}
                          <span className="selection:bg-[--primary]/30">{log.message}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
        </div>

        <aside className="space-y-8">
          {!isExecution && job && job.status === "success" && (
            <section className="space-y-6 rounded-2xl border border-[--border] bg-[--card]/40 backdrop-blur-xl p-6">
              <h2 className="text-xs font-bold uppercase tracking-widest text-[--muted-foreground] border-b border-[--border] pb-4">
                Hydration Artifacts
              </h2>
              
              <div className="space-y-3">
                <button
                  type="button"
                  onClick={handleLinkArtifactsToProject}
                  disabled={linkingArtifacts || !job.outputDbPath}
                  className="group flex w-full items-center justify-between rounded-xl border border-[--primary]/30 bg-[--primary]/10 px-4 py-3 text-xs font-semibold text-[--primary] transition-all hover:bg-[--primary]/15 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="flex items-center gap-2">
                    {linkingArtifacts ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Link2 size={14} />
                    )}
                    Link artifacts to this project
                  </span>
                  <ArrowRight size={14} className="opacity-60 group-hover:translate-x-0.5 transition-transform" />
                </button>
                <Link
                  href={`/${project}/graph`}
                  className="group flex items-center justify-between w-full rounded-xl border border-[--border] bg-[--muted]/50 px-4 py-3 text-xs font-semibold text-[--foreground] hover:border-[--primary]/40 hover:bg-[--primary]/5 transition-all"
                >
                  Explore Knowledge Graph
                  <ArrowRight size={14} className="opacity-40 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                </Link>
                <Link
                  href={`/${project}/sql`}
                  className="group flex items-center justify-between w-full rounded-xl border border-[--border] bg-[--muted]/50 px-4 py-3 text-xs font-semibold text-[--foreground] hover:border-[--primary]/40 hover:bg-[--primary]/5 transition-all"
                >
                  Execution SQL Explorer
                  <ArrowRight size={14} className="opacity-40 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                </Link>
                <Link
                  href={`/${project}/agent`}
                  className="group flex items-center justify-between w-full rounded-xl border border-[--border] bg-[--muted]/50 px-4 py-3 text-xs font-semibold text-[--foreground] hover:border-[--primary]/40 hover:bg-[--primary]/5 transition-all"
                >
                  Research Workspace
                  <ArrowRight size={14} className="opacity-40 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                </Link>
              </div>

              <div className="space-y-4 pt-4">
                 <div className="space-y-1">
                    <p className="text-[10px] font-bold uppercase text-[--muted-foreground] opacity-60">Database Target</p>
                    <p className="text-[11px] font-mono break-all bg-[--muted]/30 px-2 py-1.5 rounded border border-[--border]">{job.outputDbPath ?? "—"}</p>
                 </div>
                 <div className="space-y-1">
                    <p className="text-[10px] font-bold uppercase text-[--muted-foreground] opacity-60">Ontology Schema (OWL)</p>
                    <p className="text-[11px] font-mono break-all bg-[--muted]/30 px-2 py-1.5 rounded border border-[--border]">{job.outputOwlPath ?? "—"}</p>
                 </div>
              </div>
            </section>
          )}

          {isExecution && execution && execution.status === "success" && execution.result && (
            <section className="space-y-4">
              <h2 className="text-xs font-bold uppercase tracking-widest text-[--muted-foreground] px-1">
                Terminal Output
              </h2>
              <div className="rounded-xl border border-[--border] bg-[--card]/60 p-4 backdrop-blur-xl">
                 <ToolResult name={execution.type === "code" ? "execute_python" : "sql"} result={execution.result} />
              </div>
            </section>
          )}

          <section className="rounded-2xl border border-[--border] bg-[--card]/40 backdrop-blur-xl p-6 space-y-4">
             <h2 className="text-xs font-bold uppercase tracking-widest text-[--muted-foreground] border-b border-[--border] pb-4">
                Node Properties
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                   <p className="text-[10px] font-bold uppercase text-[--muted-foreground] opacity-50">Machine</p>
                   <p className="text-xs font-mono">{activeJob.machine || "local-node"}</p>
                </div>
                <div className="space-y-1">
                   <p className="text-[10px] font-bold uppercase text-[--muted-foreground] opacity-50">Environment</p>
                   <p className="text-xs font-mono">production</p>
                </div>
                <div className="space-y-1">
                   <p className="text-[10px] font-bold uppercase text-[--muted-foreground] opacity-50">Worker ID</p>
                   <p className="text-xs font-mono">{id.slice(0, 8)}</p>
                </div>
                <div className="space-y-1">
                   <p className="text-[10px] font-bold uppercase text-[--muted-foreground] opacity-50">Source</p>
                   <p className="text-xs font-mono uppercase">Convex</p>
                </div>
              </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
