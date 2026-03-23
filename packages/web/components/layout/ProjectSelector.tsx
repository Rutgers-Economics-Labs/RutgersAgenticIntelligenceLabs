"use client";

import { Suspense, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { ChevronDown, FolderOpen, X } from "lucide-react";

const STORAGE_KEY = "rail_selected_project_id";

function ProjectSelectorInner() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const projects = useQuery(api.projects.list);

  const [open, setOpen] = useState(false);

  // Active project: URL param takes precedence, then localStorage
  const urlProjectId = searchParams.get("projectId");
  const [activeProjectId, setActiveProjectId] = useState<string | null>(
    urlProjectId ?? (typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null)
  );

  // Sync when URL changes (e.g. user navigates directly)
  useEffect(() => {
    if (urlProjectId !== null) {
      setActiveProjectId(urlProjectId);
      localStorage.setItem(STORAGE_KEY, urlProjectId);
    }
  }, [urlProjectId]);

  const activeProject = projects?.find((p: any) => p._id === activeProjectId);

  function select(projectId: string) {
    setActiveProjectId(projectId);
    localStorage.setItem(STORAGE_KEY, projectId);
    setOpen(false);
    const params = new URLSearchParams(searchParams.toString());
    params.set("projectId", projectId);
    router.push(`${pathname}?${params.toString()}`);
  }

  function clear() {
    setActiveProjectId(null);
    localStorage.removeItem(STORAGE_KEY);
    setOpen(false);
    const params = new URLSearchParams(searchParams.toString());
    params.delete("projectId");
    const qs = params.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  if (!projects || projects.length === 0) return null;

  return (
    <div className="relative px-3 py-2 border-b border-[--border]">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md text-xs bg-[--muted] hover:bg-[--accent]/20 transition-colors"
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <FolderOpen size={12} className="text-[--primary] shrink-0" />
          <span className="truncate text-[--foreground]">
            {activeProject ? activeProject.name : "All projects"}
          </span>
        </div>
        <ChevronDown size={11} className={`text-[--muted-foreground] shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-3 right-3 top-full mt-1 z-50 rounded-lg border border-[--border] bg-[--card] shadow-xl overflow-hidden">
          <button
            onClick={clear}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-[--muted-foreground] hover:bg-[--muted] transition-colors"
          >
            <X size={11} /> All projects
          </button>
          <div className="border-t border-[--border]" />
          {projects.map((p: any) => (
            <button
              key={p._id}
              onClick={() => select(p._id)}
              className={`w-full text-left flex items-center gap-2 px-3 py-2 text-xs transition-colors ${
                p._id === activeProjectId
                  ? "bg-[--primary]/10 text-[--primary]"
                  : "text-[--foreground] hover:bg-[--muted]"
              }`}
            >
              <span className="truncate">{p.name}</span>
              {p._id === activeProjectId && (
                <span className="ml-auto text-[10px] text-[--primary]">active</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ProjectSelector() {
  return (
    <Suspense fallback={null}>
      <ProjectSelectorInner />
    </Suspense>
  );
}
