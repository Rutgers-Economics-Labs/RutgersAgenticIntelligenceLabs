"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";

export default function Root() {
  const searchParams = useSearchParams();
  const urlProjectId = searchParams.get("projectId") || "";

  const projects = useQuery(api.projects.list, {});
  const runningJobs = useQuery(api.jobs.list, { status: "running", limit: 10 });

  const currentProject = useMemo(() => {
    if (!urlProjectId || !projects) return null;
    return projects.find((p) => p._id === urlProjectId) ?? null;
  }, [projects, urlProjectId]);

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold">Dashboard</h1>
          <p className="text-xs text-[--muted-foreground] mt-1">
            Projects, activity, and quick access to your tools.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Link
            href="/projects"
            className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground] hover:border-[--primary]/50 transition-colors"
          >
            View projects
          </Link>
          <Link
            href="/configs"
            className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground] hover:border-[--primary]/50 transition-colors"
          >
            Manage configs
          </Link>
        </div>
      </div>

      {currentProject && (
        <div className="rounded-xl border border-[--border] bg-[--muted] p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[10px] text-[--muted-foreground] uppercase tracking-wide font-medium">
                Current project
              </p>
              <p className="text-sm font-semibold truncate mt-1">{currentProject.name}</p>
              {currentProject.description && (
                <p className="text-xs text-[--muted-foreground] mt-1 truncate">
                  {currentProject.description}
                </p>
              )}
            </div>
            <Link
              href={`/projects/${currentProject.slug}`}
              className="text-xs px-3 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90 transition-opacity"
            >
              Open
            </Link>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-4">
            {[
              { label: "Explorer", href: `/explorer?projectId=${currentProject._id}` },
              { label: "Graph", href: `/graph?projectId=${currentProject._id}` },
              { label: "SQL", href: `/sql?projectId=${currentProject._id}` },
              { label: "Analysis", href: `/analysis?projectId=${currentProject._id}` },
            ].map((x) => (
              <Link
                key={x.href}
                href={x.href}
                className="text-xs px-3 py-2 rounded-lg border border-[--border] hover:border-[--primary]/60 hover:bg-white/5 transition-colors"
              >
                {x.label}
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-[--border] p-5">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="text-sm font-semibold">Projects</h2>
            <Link href="/projects" className="text-xs text-[--primary] hover:underline">
              Open all →
            </Link>
          </div>

          {projects === undefined && <p className="text-xs text-[--muted-foreground]">Loading…</p>}
          {projects?.length === 0 && (
            <p className="text-xs text-[--muted-foreground]">No projects yet.</p>
          )}
          {projects && projects.length > 0 && (
            <div className="space-y-2">
              {projects.slice(0, 6).map((p) => (
                <Link
                  key={p._id}
                  href={`/projects/${p.slug}`}
                  className={cn(
                    "block rounded-lg border border-[--border] px-3 py-2 hover:border-[--primary]/60 hover:bg-[--muted] transition-colors",
                    urlProjectId === p._id && "border-[--primary]/60 bg-[--primary]/5"
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium truncate">{p.name}</p>
                    <span className="text-[10px] px-2 py-0.5 rounded border border-[--border] text-[--muted-foreground] shrink-0">
                      {p.status}
                    </span>
                  </div>
                  {p.ontologyConfigSlug && (
                    <p className="text-[10px] text-[--muted-foreground] font-mono mt-1 truncate">
                      onto: {p.ontologyConfigSlug}
                    </p>
                  )}
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-[--border] p-5">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="text-sm font-semibold">Activity</h2>
            <Link href="/jobs" className="text-xs text-[--primary] hover:underline">
              View jobs →
            </Link>
          </div>

          <div className="rounded-lg border border-[--border] bg-[--muted] p-3">
            <p className="text-xs text-[--muted-foreground]">
              Running jobs:{" "}
              <span className="text-[--foreground] font-semibold">
                {(runningJobs?.length ?? 0).toLocaleString()}
              </span>
            </p>
            <p className="text-[10px] text-[--muted-foreground] mt-1">
              For full job history and logs, open Jobs.
            </p>
          </div>

          <div className="mt-4 space-y-2">
            {[
              { title: "Explore data", desc: "Browse entities and relationships.", href: "/explorer" },
              { title: "Query with SQL", desc: "Run SQL or translate questions.", href: "/sql" },
              { title: "Run analysis", desc: "Execute analysis plugins.", href: "/analysis" },
              { title: "Tools", desc: "Assistants and utilities.", href: "/tools" },
            ].map((x) => (
              <Link
                key={x.href}
                href={x.href}
                className="block rounded-lg border border-[--border] px-3 py-2 hover:border-[--primary]/60 hover:bg-[--muted] transition-colors"
              >
                <p className="text-sm font-medium">{x.title}</p>
                <p className="text-xs text-[--muted-foreground] mt-0.5">{x.desc}</p>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
