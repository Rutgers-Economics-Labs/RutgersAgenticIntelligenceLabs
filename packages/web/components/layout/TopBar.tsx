"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { usePathname } from "next/navigation";
import { useMemo, Suspense } from "react";

export function TopBar() {
  const pathname = usePathname();

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

  return (
    <div className="h-12 w-full bg-[--card] border-b border-[--border] flex items-center justify-between px-4 shrink-0 sticky top-0 z-50">
      {/* Left */}
      <div className="flex items-center w-[200px]">
        <Link href="/projects" className="flex items-center hover:opacity-80 transition-opacity">
          <span className="text-sm font-bold text-[--primary] tracking-wide uppercase">RAIL</span>
        </Link>
      </div>

      {/* Center */}
      <div className="flex-1 flex justify-center">
        {isProjectScopedRoute && (
          <Suspense fallback={<div className="h-9 w-[250px] bg-muted animate-pulse rounded-md" />}>
            <ProjectSwitcher />
          </Suspense>
        )}
      </div>

      {/* Right */}
      <div className="flex items-center w-[200px] justify-end">
        <Button variant="outline" size="sm" asChild className="h-8">
          <Link href="/projects?new=1">
            <Plus className="h-4 w-4 mr-1" />
            New Project
          </Link>
        </Button>
      </div>
    </div>
  );
}
