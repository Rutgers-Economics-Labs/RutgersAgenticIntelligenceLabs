"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Network, Database, GitBranch, BarChart2,
  Activity, Settings, Layers, FolderOpen, Sun, Moon,
  BotMessageSquare, Table2, Library, MessageCircleQuestion, BookOpen, ShieldCheck,
} from "lucide-react";
import { useTheme } from "@/components/ThemeProvider";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { useEffect, useMemo, useState } from "react";

type NavItem = { href: string; label: string; icon: React.ElementType };

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Research",
    items: [
      { href: "/questions", label: "Questions", icon: MessageCircleQuestion },
      { href: "/analysis",  label: "Analysis",  icon: BarChart2 },
      { href: "/context",   label: "Knowledge Base", icon: BookOpen },
    ],
  },
  {
    title: "Explore",
    items: [
      { href: "/explorer", label: "Explorer", icon: Layers },
      { href: "/graph",    label: "Graph",    icon: Network },
      { href: "/sql",      label: "SQL",      icon: Table2 },
      { href: "/quality",  label: "Quality",  icon: ShieldCheck },
    ],
  },
  {
    title: "Ops",
    items: [
      { href: "/jobs", label: "Jobs", icon: Settings },
      { href: "/pipelines", label: "Pipelines", icon: GitBranch },
    ],
  },
  {
    title: "Data",
    items: [
      { href: "/configs", label: "Configs", icon: Database },
      { href: "/registry", label: "Registry", icon: Library },
    ],
  },
  {
    title: "Tools",
    items: [
      { href: "/tools", label: "Tools", icon: BotMessageSquare },
    ],
  },
];

import { Suspense } from "react";

function SidebarContent() {
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
      pathname.startsWith("/analysis") ||
      pathname.startsWith("/questions") ||
      pathname.startsWith("/context") ||
      pathname.startsWith("/quality")
    );
  }, [pathname]);

  // Ensure the selected project is always a real project (no "All/Global" state).
  useEffect(() => {
    if (!projects || projects.length === 0) return;

    const hasStored = !!storedProjectId;
    const storedIsValid = hasStored && projects.some((p) => p._id === storedProjectId);
    if (storedIsValid) return;

    const fallbackId = projects[0]._id;
    setStoredProjectId(fallbackId);
    try {
      localStorage.setItem("rail_projectId", fallbackId);
    } catch {
      /* ignore */
    }

    // If the URL already has projectId (or we're on a scoped route), keep it consistent.
    const sp = new URLSearchParams(searchParams.toString());
    const urlId = sp.get("projectId");
    const shouldSyncUrl = isProjectScopedRoute || urlId !== null;
    if (shouldSyncUrl && urlId !== fallbackId) {
      sp.set("projectId", fallbackId);
      router.replace(`${pathname}?${sp.toString()}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects, storedProjectId, isProjectScopedRoute, pathname]);

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
    const id = storedProjectId;
    if (!id) return href;
    if (href === "/projects" || href === "/configs" || href === "/registry" || href === "/pipelines" || href === "/jobs") {
      return href;
    }
    const sp = new URLSearchParams();
    sp.set("projectId", id);
    return `${href}?${sp.toString()}`;
  }

  // Only render project-scoped links if we are inside a project scoped route
  const visibleNavGroups = NAV_GROUPS.filter((group) => {
    if (!isProjectScopedRoute && (group.title === "Research" || group.title === "Explore")) {
      return false;
    }
    return true;
  });

  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-[--border] bg-[--card] h-[calc(100vh-3rem)] sticky top-12">
      <nav className="flex-1 py-3 overflow-y-auto">
        <div className="mb-3">
          <Link
            href={linkHref("/")}
            className={cn(
              "flex items-center justify-between px-4 py-2.5 text-sm transition-colors group",
              pathname === "/"
                ? "bg-[--accent]/20 text-[--primary] font-medium"
                : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-white/5"
            )}
          >
            <div className="flex items-center gap-3">
              <Activity size={15} />
              Dashboard
            </div>
          </Link>
          <Link
            href="/projects"
            className={cn(
              "flex items-center justify-between px-4 py-2.5 text-sm transition-colors group",
              pathname.startsWith("/projects")
                ? "bg-[--accent]/20 text-[--primary] font-medium"
                : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-white/5"
            )}
          >
            <div className="flex items-center gap-3">
              <FolderOpen size={15} />
              Projects
            </div>
          </Link>
        </div>

        {visibleNavGroups.map((group) => (
          <div key={group.title} className="mb-3 last:mb-0">
            <p className="px-4 py-1 text-[10px] text-[--muted-foreground] uppercase tracking-wide font-medium">
              {group.title}
            </p>
            <div className="mt-1">
              {group.items.map(({ href, label, icon: Icon }) => {
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
            </div>
          </div>
        ))}
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

export function Sidebar() {
  return (
    <Suspense fallback={<aside className="w-56 shrink-0 flex flex-col border-r border-[--border] bg-[--card] h-[calc(100vh-3rem)] sticky top-12" />}>
      <SidebarContent />
    </Suspense>
  );
}
