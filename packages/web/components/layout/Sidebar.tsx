"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Network, Database, GitBranch, BarChart2,
  Activity, Settings, Layers, FolderOpen, Sun, Moon,
  BotMessageSquare, Table2,
} from "lucide-react";
import { useTheme } from "@/components/ThemeProvider";

const NAV = [
  { href: "/workspace", label: "AI Workspace",  icon: BotMessageSquare },
  { href: "/",          label: "Dashboard",     icon: Activity },
  { href: "/projects",  label: "Projects",      icon: FolderOpen },
  { href: "/explorer",  label: "Explorer",      icon: Layers },
  { href: "/graph",     label: "Graph",         icon: Network },
  { href: "/sql",       label: "SQL",           icon: Table2 },
  { href: "/analysis",  label: "Analysis",      icon: BarChart2 },
  { href: "/configs",   label: "Data Sources",  icon: Database },
  { href: "/pipelines", label: "Pipelines",     icon: GitBranch },
  { href: "/jobs",      label: "Jobs",          icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();
  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-[--border] bg-[--card] h-screen sticky top-0">
      <div className="px-4 py-5 border-b border-[--border]">
        <span className="text-sm font-bold text-[--primary] tracking-wide uppercase">RAIL</span>
        <p className="text-[10px] text-[--muted-foreground] mt-0.5">Agentic Intelligence Labs</p>
      </div>
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-4 py-2.5 text-sm transition-colors",
                active
                  ? "bg-[--accent]/20 text-[--primary] font-medium"
                  : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-white/5"
              )}
            >
              <Icon size={15} />
              {label}
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
