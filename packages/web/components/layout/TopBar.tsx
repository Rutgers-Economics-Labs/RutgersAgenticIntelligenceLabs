"use client";

import Link from "next/link";
import { Plus, Github, Settings, LayoutGrid } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { usePathname } from "next/navigation";
import { useMemo, Suspense } from "react";
import { cn } from "@/lib/utils";

export function TopBar({ projectSlug }: { projectSlug?: string }) {
  const pathname = usePathname();

  const isProjectMode = useMemo(() => {
    return !!projectSlug || 
      pathname.startsWith("/explorer") ||
      pathname.startsWith("/graph") ||
      pathname.startsWith("/sql") ||
      pathname.startsWith("/workspace") ||
      pathname.startsWith("/analysis") ||
      pathname.startsWith("/questions") ||
      pathname.startsWith("/context") ||
      pathname.startsWith("/quality");
  }, [pathname, projectSlug]);

  return (
    <div className="h-12 w-full bg-[--card]/80 backdrop-blur-md border-b border-[--border] flex items-center justify-between px-6 shrink-0 sticky top-0 z-50">
      {/* Left */}
      <div className="flex items-center w-auto gap-4">
        <Link href="/projects" className="flex items-center gap-3 hover:opacity-80 transition-all active:scale-95 group">
          <img src="/rel-logo.jpg" className="w-8 h-8 rounded-lg shadow-sm" alt="REL Logo" />
          <div className="flex flex-col">
            <span className="text-[10px] font-black tracking-[0.1em] uppercase opacity-80 group-hover:opacity-100 leading-none">
              Rutgers Agentic
            </span>
            <span className="text-[10px] font-black tracking-[0.1em] uppercase opacity-80 group-hover:opacity-100 leading-none mt-0.5">
              Intelligence Lab
            </span>
          </div>
        </Link>
      </div>

      {/* Center */}
      <div className="flex-1 flex justify-center">
        {isProjectMode && (
          <Suspense fallback={<div className="h-8 w-[240px] bg-white/5 animate-pulse rounded-lg" />}>
            <ProjectSwitcher projectSlug={projectSlug} />
          </Suspense>
        )}
      </div>

      {/* Right */}
      <div className="flex items-center w-[250px] justify-end gap-2">
        {projectSlug ? (
          <>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground" asChild>
              <Link href={`/${projectSlug}/github`} title="GitHub Sync">
                <Github size={16} />
              </Link>
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground" asChild>
              <Link href={`/${projectSlug}/settings`} title="Settings">
                <Settings size={16} />
              </Link>
            </Button>
          </>
        ) : (
          <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground" asChild>
             <Link href="/registry" title="Config Registry">
                <LayoutGrid size={16} />
             </Link>
          </Button>
        )}
        <div className="h-4 w-[1px] bg-[--border] mx-1" />
        <Button variant="outline" size="sm" asChild className="h-8 text-[10px] uppercase font-bold tracking-wider border-[--border] bg-transparent hover:bg-white/5">
          <Link href="/projects">
            All Projects
          </Link>
        </Button>
      </div>
    </div>
  );
}
