import re

with open("packages/web/components/layout/ProjectSwitcher.tsx", "r") as f:
    content = f.read()

# Let's replace the whole file since it needs significant changes for the new routing model.
new_content = """"use client";

import * as React from "react";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Check, ChevronsUpDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import Link from "next/link";

import { Suspense } from "react";

function ProjectSwitcherContent({ projectSlug }: { projectSlug?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [open, setOpen] = React.useState(false);

  const projects = useQuery(api.projects.list, {}) || [];

  const urlProjectId = searchParams.get("projectId");
  const [storedProjectId, setStoredProjectId] = React.useState("");

  React.useEffect(() => {
    if (urlProjectId !== null) {
      setStoredProjectId(urlProjectId);
      try {
        localStorage.setItem("rail_projectId", urlProjectId);
      } catch {}
    } else {
      try {
        const s = localStorage.getItem("rail_projectId") || "";
        setStoredProjectId(s);
      } catch {}
    }
  }, [urlProjectId]);

  const projectId = storedProjectId;

  const currentProject = projectSlug
    ? projects.find((p) => p.slug === projectSlug)
    : projects.find((p) => p._id === projectId);

  const isProjectScopedRoute = React.useMemo(() => {
    return (
      projectSlug !== undefined ||
      pathname.startsWith("/explorer") ||
      pathname.startsWith("/graph") ||
      pathname.startsWith("/sql") ||
      pathname.startsWith("/workspace") ||
      pathname.startsWith("/analysis") ||
      pathname.startsWith("/questions") ||
      pathname.startsWith("/context") ||
      pathname.startsWith("/quality")
    );
  }, [pathname, projectSlug]);

  const onProjectSelect = (project: any) => {
    setOpen(false);
    setStoredProjectId(project._id);
    try {
      localStorage.setItem("rail_projectId", project._id);
    } catch {}

    if (projectSlug) {
      // Replace the current slug in the URL with the new project's slug
      const newPathname = pathname.replace(`/${projectSlug}`, `/${project.slug}`);
      router.push(newPathname);
    } else {
      const sp = new URLSearchParams(searchParams.toString());
      sp.set("projectId", project._id);

      if (isProjectScopedRoute) {
        router.push(`${pathname}?${sp.toString()}`);
      } else {
        // Fallback for old routing
        router.push(`/explorer?${sp.toString()}`);
      }
    }
  };

  const getStatusColor = (status?: string) => {
    switch (status) {
      case "hydrated":
        return "bg-green-500";
      case "ready":
        return "bg-yellow-500";
      default:
        return "bg-gray-500"; // draft or unknown
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-[250px] justify-between h-9 bg-background border-border text-foreground"
        >
          {currentProject ? (
            <div className="flex items-center gap-2 truncate">
              <div
                className={cn(
                  "w-2 h-2 rounded-full shrink-0",
                  getStatusColor(currentProject.status)
                )}
              />
              <span className="truncate">{currentProject.name}</span>
            </div>
          ) : (
            <span className="text-muted-foreground truncate">Select Project...</span>
          )}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[250px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Search project..." />
          <CommandList>
            <CommandEmpty>No project found.</CommandEmpty>
            <CommandGroup heading="Projects">
              {projects.map((project) => (
                <CommandItem
                  key={project._id}
                  value={project.name}
                  onSelect={() => onProjectSelect(project)}
                  className="flex items-center justify-between"
                >
                  <div className="flex items-center gap-2 truncate">
                    <div
                      className={cn(
                        "w-2 h-2 rounded-full shrink-0",
                        getStatusColor(project.status)
                      )}
                    />
                    <span className="truncate">{project.name}</span>
                  </div>
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4 shrink-0",
                      currentProject && currentProject._id === project._id ? "opacity-100" : "opacity-0"
                    )}
                  />
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup>
              <CommandItem onSelect={() => {
                setOpen(false);
                router.push('/projects');
              }} className="cursor-pointer">
                All Projects
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export function ProjectSwitcher({ projectSlug }: { projectSlug?: string }) {
  return (
    <Suspense fallback={<div className="h-9 w-[250px] bg-muted animate-pulse rounded-md" />}>
      <ProjectSwitcherContent projectSlug={projectSlug} />
    </Suspense>
  );
}
"""

with open("packages/web/components/layout/ProjectSwitcher.tsx", "w") as f:
    f.write(new_content)
