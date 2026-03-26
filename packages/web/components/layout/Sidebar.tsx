"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Network, Database, GitBranch, BarChart2,
  Activity, Settings, Layers, FolderOpen, Sun, Moon,
  BotMessageSquare, Table2, Library,
} from "lucide-react";
import { useTheme } from "@/components/ThemeProvider";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { useEffect, useMemo, useState } from "react";

const NAV = [
  { href: "/workspace", label: "AI Workspace",  icon: BotMessageSquare },
  { href: "/",          label: "Dashboard",     icon: Activity },
  { href: "/projects",  label: "Projects",      icon: FolderOpen },
  { href: "/explorer",  label: "Explorer",      icon: Layers },
  { href: "/graph",     label: "Graph",         icon: Network },
  { href: "/sql",       label: "SQL",           icon: Table2 },
  { href: "/analysis",  label: "Analysis",      icon: BarChart2 },
  { href: "/configs",   label: "Data Sources",  icon: Database },
  { href: "/registry",  label: "Registry",      icon: Library },
  { href: "/pipelines", label: "Pipelines",     icon: GitBranch },
  { href: "/jobs",      label: "Jobs",          icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { theme, toggle } = useTheme();
  
  // Real-time counter of active jobs (running or queued)
  const activeJobs = useQuery(api.jobs.list, { status: "running", limit: 10 });
  const runningCount = activeJobs?.length ?? 0;

  const projects = useQuery(api.projects.list, {});

  // Do not read localStorage in useState initializer: server renders "" but client would
  // read a saved id → hydration mismatch on <Link href> and <select value>.
  const urlProjectId = searchParams.get("projectId");

  // Select follows optimistic state so it does not snap back while navigation completes.
  const [storedProjectId, setStoredProjectId] = useState("");

  // URL is source of truth when the param is present (refresh, deep link, back/forward).
  useEffect(() => {
    if (urlProjectId === null) return;
    setStoredProjectId(urlProjectId);
    try {
      if (urlProjectId) localStorage.setItem("rail_projectId", urlProjectId);
      else localStorage.removeItem("rail_projectId");
    } catch {
      /* ignore */
    }
  }, [urlProjectId]);

  // When the URL omits projectId, restore from localStorage after mount (client-only).
  useEffect(() => {
    if (urlProjectId !== null) return;
    try {
      const s = localStorage.getItem("rail_projectId") || "";
      setStoredProjectId(s);
    } catch {
      /* ignore */
    }
  }, [urlProjectId]);

  const projectId = storedProjectId;
  const projectLabel = useMemo(() => {
    if (!projectId || !projects) return "";
    const p = projects.find((x) => x._id === projectId);
    return p ? p.name : "";
  }, [projectId, projects]);

  const isProjectScopedRoute = useMemo(() => {
    return (
      pathname.startsWith("/explorer") ||
      pathname.startsWith("/graph") ||
      pathname.startsWith("/sql") ||
      pathname.startsWith("/workspace") ||
      pathname.startsWith("/analysis")
    );
  }, [pathname]);

  useEffect(() => {
    // Sticky behavior: if user has a saved project and is on a project-scoped route,
    // ensure the URL includes projectId so refresh/copy-paste preserves scope.
    if (!isProjectScopedRoute) return;
    if (urlProjectId) return;
    if (!storedProjectId) return;
    const sp = new URLSearchParams(searchParams.toString());
    sp.set("projectId", storedProjectId);
    router.replace(`${pathname}?${sp.toString()}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isProjectScopedRoute, urlProjectId, storedProjectId, pathname]);

  // Only use the URL for link hrefs so SSR and the first client pass match. Sticky
  // projectId is applied via router.replace; after that, searchParams include it here too.
  function linkHref(href: string) {
    const id = searchParams.get("projectId");
    if (!id) return href;
    if (href === "/projects" || href === "/configs" || href === "/registry" || href === "/pipelines" || href === "/jobs") {
      return href;
    }
    const sp = new URLSearchParams();
    sp.set("projectId", id);
    return `${href}?${sp.toString()}`;
  }

  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-[--border] bg-[--card] h-screen sticky top-0">
      <div className="px-4 py-5 border-b border-[--border]">
        <span className="text-sm font-bold text-[--primary] tracking-wide uppercase">RAIL</span>
        <p className="text-[10px] text-[--muted-foreground] mt-0.5">Agentic Intelligence Labs</p>

        {/* Project switcher */}
        <div className="mt-3">
          <p className="text-[10px] text-[--muted-foreground] uppercase tracking-wide font-medium mb-1">
            Project
          </p>
          <select
            value={projectId}
            onChange={(e) => {
              const next = e.target.value;
              try { localStorage.setItem("rail_projectId", next); } catch {}
              setStoredProjectId(next);
              // If we're already on a scoped route, update the current URL. Otherwise just persist.
              if (isProjectScopedRoute) {
                const sp = new URLSearchParams(searchParams.toString());
                if (next) sp.set("projectId", next);
                else sp.delete("projectId");
                router.push(`${pathname}?${sp.toString()}`);
              }
            }}
            className="w-full px-2 py-1.5 rounded border border-[--border] bg-[--muted] text-xs text-[--foreground] outline-none focus:border-[--primary]"
          >
            <option value="">All / Global</option>
            {projects?.map((p) => (
              <option key={p._id} value={p._id}>
                {p.name}
              </option>
            ))}
          </select>
          {projectId && projectLabel && (
            <p className="mt-1 text-[10px] text-[--muted-foreground] truncate" title={projectLabel}>
              {projectLabel}
            </p>
          )}
        </div>
      </div>
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          const isJobs = href === "/jobs";
          
          return (
            <Link
              key={href}
              href={linkHref(href)}
              className={cn(
                "flex items-center justify-between px-4 py-2.5 text-sm transition-colors group",
                active
                  ? "bg-[--accent]/20 text-[--primary] font-medium"
                  : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-white/5"
              )}
            >
              <div className="flex items-center gap-3">
                <Icon size={15} />
                {label}
              </div>
              
              {isJobs && runningCount > 0 && (
                <span className="flex items-center justify-center min-w-[18px] h-[18px] px-1 bg-[--primary] text-white text-[10px] font-bold rounded-full animate-pulse shadow-[0_0_8px_rgba(var(--primary-rgb),0.5)]">
                  {runningCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="px-4 py-3 border-t border-[--border] flex items-center justify-between">
        <p className="text-[10px] text-[--muted-foreground]">Rutgers Agentic Intelligence Labs</p>
        <button
          onClick={toggle}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          className="p-1.5 rounded text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted] transition-colors"
        >
          {theme === "dark" ? <Sun size={13} /> : <Moon size={13} />}
        </button>
      </div>
    </aside>
  );
}
