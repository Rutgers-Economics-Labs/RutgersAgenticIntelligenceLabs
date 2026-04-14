"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { 
  FileText, ListTodo, Layers, Notebook, 
  Archive, History, Settings 
} from "lucide-react";

export function ProjectNav({ projectSlug }: { projectSlug: string }) {
  const pathname = usePathname();

  const navItems = [
    { label: "Specs", href: `/${projectSlug}/specs`, icon: FileText },
    { label: "Plan", href: `/${projectSlug}/plan`, icon: ListTodo },
    { label: "Ontology", href: `/${projectSlug}/ontology`, icon: Layers },
    { label: "Topics", href: `/${projectSlug}/topics`, icon: Notebook },
    { label: "Artifacts", href: `/${projectSlug}/artifacts`, icon: Archive },
    { label: "Sessions", href: `/${projectSlug}/sessions`, icon: History },
    { label: "Settings", href: `/${projectSlug}/settings`, icon: Settings },
  ];

  return (
    <nav className="flex items-center gap-1 p-1 bg-white/5 rounded-lg border border-white/10 mx-auto w-fit">
      {navItems.map((item) => {
        const Icon = item.icon;
        const isActive = pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md transition-all",
              isActive 
                ? "bg-[--primary] text-[--primary-foreground] shadow-sm" 
                : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-white/5"
            )}
          >
            <Icon size={14} />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
