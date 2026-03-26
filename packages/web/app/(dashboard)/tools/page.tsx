"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";

export default function ToolsPage() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("projectId") || "";
  const projects = useQuery(api.projects.list, {});
  const current = projectId && projects ? projects.find((p) => p._id === projectId) : null;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-lg font-semibold">Tools</h1>
        <p className="text-xs text-[--muted-foreground] mt-1">
          Optional assistants and utilities. Kept here to reduce clutter elsewhere.
        </p>
      </div>

      <div className="rounded-xl border border-[--border] p-5 bg-[--muted]">
        <p className="text-[10px] text-[--muted-foreground] uppercase tracking-wide font-medium">
          Context
        </p>
        <p className="text-sm mt-1">
          {current ? (
            <>
              Current project: <span className="font-semibold">{current.name}</span>
            </>
          ) : (
            <>
              Current project: <span className="font-semibold">None</span>{" "}
              <span className="text-[--muted-foreground]">(select one in the sidebar)</span>
            </>
          )}
        </p>
      </div>

      <div className="rounded-xl border border-[--border] p-5">
        <h2 className="text-sm font-semibold mb-3">AI</h2>
        <div className="space-y-2">
          <Link
            href={projectId ? `/workspace?projectId=${projectId}` : "/workspace"}
            className="block rounded-lg border border-[--border] px-3 py-2 hover:border-[--primary]/60 hover:bg-[--muted] transition-colors"
          >
            <p className="text-sm font-medium">AI Workspace</p>
            <p className="text-xs text-[--muted-foreground] mt-0.5">
              Chat-driven workflow for the selected project.
            </p>
          </Link>

          <Link
            href={current ? `/projects/${current.slug}` : "/projects"}
            className="block rounded-lg border border-[--border] px-3 py-2 hover:border-[--primary]/60 hover:bg-[--muted] transition-colors"
          >
            <p className="text-sm font-medium">Project Assistant</p>
            <p className="text-xs text-[--muted-foreground] mt-0.5">
              Available from a project page (kept out of the global UI).
            </p>
          </Link>
        </div>
      </div>
    </div>
  );
}

