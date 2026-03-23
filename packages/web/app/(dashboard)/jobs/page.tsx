"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@/lib/utils";

const STATUS_COLORS: Record<string, string> = {
  queued: "#8b949e", running: "#58a6ff", success: "#3fb950",
  failed: "#f85149", cancelled: "#8b949e",
};

function timeAgo(ms: number) {
  const s = Math.floor((Date.now() - ms) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

export default function JobsPage() {
  const [filter, setFilter] = useState<string | "all">("all");
  const jobs = useQuery(api.jobs.list, { limit: 100 });
  
  const filteredJobs = jobs?.filter(j => filter === "all" || j.status === filter);
  const runningCount = jobs?.filter(j => j.status === "running").length ?? 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Hydration Jobs</h1>
        <div className="flex items-center gap-1 bg-[--muted] p-1 rounded-md border border-[--border]">
          {["all", "running", "success", "failed"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-3 py-1 rounded text-xs font-medium transition-all capitalize",
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

      {jobs === undefined && (
        <p className="text-[--muted-foreground] text-sm">Loading…</p>
      )}
      {filteredJobs?.length === 0 && (
        <div className="flex items-center justify-center h-48 border border-dashed border-[--border] rounded-lg text-[--muted-foreground] text-sm">
          No {filter === "all" ? "" : filter} jobs found.
        </div>
      )}
      {filteredJobs && filteredJobs.length > 0 && (
        <div className="rounded-lg border border-[--border] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[--border] bg-[--muted]">
                <th className="text-left px-4 py-2.5 text-[--muted-foreground] font-medium">Pipeline</th>
                <th className="text-left px-4 py-2.5 text-[--muted-foreground] font-medium">Status</th>
                <th className="text-left px-4 py-2.5 text-[--muted-foreground] font-medium">Steps</th>
                <th className="text-left px-4 py-2.5 text-[--muted-foreground] font-medium">Started</th>
                <th className="w-20 px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {filteredJobs.map((job) => (
                <tr key={job._id} className="border-b border-[--border] hover:bg-white/[0.03]">
                  <td className="px-4 py-3 font-mono text-xs text-[--muted-foreground]">{job.pipelineSlug}</td>
                  <td className="px-4 py-3">
                    <span
                      className="px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{
                        color: STATUS_COLORS[job.status],
                        background: STATUS_COLORS[job.status] + "22",
                        border: `1px solid ${STATUS_COLORS[job.status]}44`,
                      }}
                    >
                      {job.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[--muted-foreground] text-xs">
                    {job.stepResults.filter((s) => s.status === "done").length}
                    /{job.stepResults.length} done
                  </td>
                  <td className="px-4 py-3 text-[--muted-foreground] text-xs">{timeAgo(job.createdAt)}</td>
                  <td className="px-4 py-3">
                    <Link href={`/jobs/${job._id}`} className="text-xs text-[--primary] hover:underline">
                      View →
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
