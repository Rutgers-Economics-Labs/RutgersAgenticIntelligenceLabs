"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Network, Database, GitBranch, BarChart2,
  Activity, Settings, Layers, FolderOpen, Sun, Moon,
  BotMessageSquare, Table2, Library,
} from "lucide-react";
import { useTheme } from "@/components/ThemeProvider";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";

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
  const { theme, toggle } = useTheme();
  
  // Real-time counter of active jobs (running or queued)
  const activeJobs = useQuery(api.jobs.list, { status: "running", limit: 10 });
  const runningCount = activeJobs?.length ?? 0;

  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-[--border] bg-[--card] h-screen sticky top-0">
      <div className="px-4 py-5 border-b border-[--border]">
        <span className="text-sm font-bold text-[--primary] tracking-wide uppercase">RAIL</span>
        <p className="text-[10px] text-[--muted-foreground] mt-0.5">Agentic Intelligence Labs</p>
      </div>
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          const isJobs = href === "/jobs";
          
          return (
            <Link
              key={href}
              href={href}
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
