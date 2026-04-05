"use client";
import { useQuery } from "convex/react";
import { useMemo, useState, Suspense } from "react";

import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Database, Code, Zap, FileText, ChevronRight } from "lucide-react";

const STATUS_COLORS: Record<string, string> = {
  queued: "#8b949e",
  running: "#58a6ff",
  success: "#3fb950",
  failed: "#f85149",
  cancelled: "#8b949e",
};

function timeAgo(ms: number) {
  const s = Math.floor((Date.now() - ms) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(ms).toLocaleDateString();
}

function ResultPreview({ job }: { job: any }) {
  if (job.kind === "hydration") {
    const done = job.stepResults.filter((s: any) => s.status === "done").length;
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-[--muted-foreground]">
        <Zap size={12} className="text-blue-400" />
        <span>{done}/{job.stepResults.length} steps complete</span>
      </div>
    );
  }

  if (job.status === "success" && job.result) {
    if (job.type === "sql") {
      const rowCount = job.result.rowCount;
      return (
        <div className="flex items-center gap-1.5 text-[11px] text-[--muted-foreground]">
          <Database size={12} className="text-purple-400" />
          <span>{rowCount} rows returned</span>
        </div>
      );
    }
    if (job.type === "code") {
      const artifactCount = (job.result.figures?.length || 0) + (Object.keys(job.result.dataframes || {}).length);
      return (
        <div className="flex items-center gap-1.5 text-[11px] text-[--muted-foreground]">
          <Code size={12} className="text-green-400" />
          <span>{artifactCount} visual outputs</span>
        </div>
      );
    }
  }

  if (job.status === "failed") {
    return <span className="text-[11px] text-red-400 truncate max-w-[150px]">{job.errorMessage}</span>;
  }

  return <span className="text-[11px] text-[--muted-foreground]">No result yet</span>;
}

function JobsPageInner({ projectSlug }: { projectSlug: string }) {



  const [filter, setFilter] = useState<string | "all">("all");

  const hydrationJobs = useQuery(
    projectSlug ? api.jobs.listByProject : api.jobs.list,
    projectSlug ? { projectSlug, limit: 100 } : { limit: 100 }
  );
  
  const executionJobs = useQuery(
    projectSlug ? (api as any).executions.listByProject : (api as any).executions.list,
    projectSlug ? { projectSlug, limit: 100 } : { limit: 100 }
  );
  
  const allJobs = useMemo(() => {
    const combined = [
      ...(hydrationJobs ?? []).map((j: any) => ({ ...j, kind: "hydration" as const })),
      ...(executionJobs ?? []).map((j: any) => ({ ...j, kind: "execution" as const }))
    ];
    return combined.sort((a, b) => b.createdAt - a.createdAt);
  }, [hydrationJobs, executionJobs]);

  const filteredJobs = allJobs.filter((j: any) => filter === "all" || j.status === filter);
  const runningCount = allJobs.filter((j: any) => j.status === "running").length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Project Activity</h1>
          <p className="text-sm text-[--muted-foreground] mt-1">
            {projectSlug ? "Isolated view of this project's executions." : "All recent activity across the platform."}
          </p>
        </div>
        
        <div className="flex items-center gap-1 bg-[--muted]/50 p-1 rounded-lg border border-[--border]">
          {["all", "running", "success", "failed"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-3 py-1.5 rounded-md text-[11px] font-medium transition-all capitalize",
                filter === f 
                  ? "bg-[--card] text-[--foreground] shadow-sm border border-[--border]" 
                  : "text-[--muted-foreground] hover:text-[--foreground]"
              )}
            >
              {f} {f === "running" && runningCount > 0 && `(${runningCount})`}
            </button>
          ))}
        </div>
      </div>

      {(hydrationJobs === undefined || executionJobs === undefined) ? (
        <div className="flex flex-col items-center justify-center h-64 border border-[--border] rounded-xl bg-[--card]/50 animate-pulse">
           <p className="text-[--muted-foreground] text-sm italic">Synchronizing job history...</p>
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 border border-dashed border-[--border] rounded-xl bg-[--muted]/10">
          <FileText className="text-[--muted-foreground] mb-3 opacity-20" size={32} />
          <p className="text-[--muted-foreground] text-sm">No {filter === "all" ? "" : filter} activity found.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-[--border] bg-[--card] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[--border] bg-[--muted]/30">
                <th className="text-left px-4 py-3 text-[11px] uppercase tracking-wider text-[--muted-foreground] font-semibold">Activity / Source</th>
                <th className="text-left px-4 py-3 text-[11px] uppercase tracking-wider text-[--muted-foreground] font-semibold">Category</th>
                <th className="text-left px-4 py-3 text-[11px] uppercase tracking-wider text-[--muted-foreground] font-semibold">Status</th>
                <th className="text-left px-4 py-3 text-[11px] uppercase tracking-wider text-[--muted-foreground] font-semibold">Result Insight</th>
                <th className="text-left px-4 py-3 text-[11px] uppercase tracking-wider text-[--muted-foreground] font-semibold">Timing</th>
                <th className="w-10 px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[--border]">
              {filteredJobs.map((job) => (
                <tr key={job._id} className="group hover:bg-white/[0.02] transition-colors">
                  <td className="px-4 py-4">
                    <div className="flex flex-col">
                      <span className="font-mono text-[13px] text-[--foreground] font-medium truncate max-w-[240px]">
                        {job.kind === "hydration" ? job.pipelineSlug : (job as any).input}
                      </span>
                      {!projectSlug && job.projectSlug && (
                        <span className="text-[10px] text-[--primary] mt-1 flex items-center gap-1">
                           <Zap size={10} /> ID: {job.projectSlug.slice(-8)}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-2">
                      {job.kind === "hydration" ? (
                        <Zap className="text-blue-400" size={14} />
                      ) : (job as any).type === "sql" ? (
                        <Database className="text-purple-400" size={14} />
                      ) : (
                        <Code className="text-green-400" size={14} />
                      )}
                      <span className="text-xs uppercase font-semibold text-[--muted-foreground]">
                        {job.kind === "hydration" ? "Hydration" : (job as any).type}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-tight"
                      style={{
                        color: STATUS_COLORS[job.status],
                        background: STATUS_COLORS[job.status] + "15",
                        border: `1px solid ${STATUS_COLORS[job.status]}30`,
                      }}
                    >
                      {job.status}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <ResultPreview job={job} />
                  </td>
                  <td className="px-4 py-4 text-[--muted-foreground] text-[11px]">
                    <div className="flex flex-col">
                      <span>{timeAgo(job.createdAt)}</span>
                      {job.finishedAt && (
                        <span className="text-[10px] opacity-60">Dur: {((job.finishedAt - job.createdAt) / 1000).toFixed(1)}s</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-4 text-right">
                    <Link 
                      href={`/jobs/${job._id}`} 
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg hover:bg-[--muted] transition-colors text-[--muted-foreground] hover:text-[--primary]"
                    >
                      <ChevronRight size={18} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default async function JobsPage({ params }: { params: { project: string } }) {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-[--muted-foreground] animate-pulse">Syncing platform activity...</div>}>
      <JobsPageInner projectSlug={(await params).project} />
    </Suspense>
  );
}
