"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";
import { Activity, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

export function RunningJobsIndicator() {
  const [dismissed, setDismissed] = useState(false);
  const runningJobs = useQuery(api.jobs.list, { status: "running" });
  const firstProjectId = runningJobs?.[0]?.projectId as Id<"projects"> | undefined;
  const project = useQuery(api.projects.getById, firstProjectId ? { projectId: firstProjectId } : "skip");

  if (!runningJobs || runningJobs.length === 0 || dismissed) return null;

  const count = runningJobs.length;
  const jobsHref = project ? `/${project.slug}/jobs` : "/projects";

  return (
    <div className="mb-6 flex items-center justify-between px-4 py-2 bg-[--primary]/10 border border-[--primary]/30 rounded-lg animate-in slide-in-from-top duration-500">
      <div className="flex items-center gap-3 text-sm text-[--primary]">
        <div className="flex items-center justify-center w-6 h-6 rounded-full bg-[--primary]/20 animate-pulse">
          <Activity size={14} />
        </div>
        <p className="font-medium">
          {count === 1 
            ? `Hydration running: ${runningJobs[0].pipelineSlug}`
            : `${count} active hydration jobs running...`
          }
        </p>
      </div>
      
      <div className="flex items-center gap-4">
        <Link 
          href={jobsHref} 
          className="text-xs font-semibold text-[--primary] hover:underline transition-all"
        >
          View Progress →
        </Link>
        <button 
          onClick={() => setDismissed(true)}
          className="text-[--muted-foreground] hover:text-[--foreground] transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
