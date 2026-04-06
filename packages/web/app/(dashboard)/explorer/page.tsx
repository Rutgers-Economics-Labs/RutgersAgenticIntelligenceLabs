"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import OntologyExplorerContent from "@/components/ontology/OntologyExplorerContent";

function ExplorerWithProject() {
  const sp = useSearchParams();
  const projectSlug =
    sp.get("projectSlug")?.trim() ||
    sp.get("projectId")?.trim() ||
    "";

  if (!projectSlug) {
    return (
      <div className="p-10 max-w-xl">
        <h1 className="text-2xl font-semibold mb-2">Entity Explorer</h1>
        <p className="text-sm text-[--muted-foreground] mb-4">
          Choose a project context. Add{" "}
          <code className="rounded bg-[--muted] px-1.5 py-0.5 text-[--primary]">?projectSlug=your-project</code>{" "}
          to the URL, or open the explorer from a project’s Ontology page.
        </p>
        <Link href="/projects" className="text-sm text-[--primary] hover:underline">
          ← Projects
        </Link>
      </div>
    );
  }

  return <OntologyExplorerContent projectSlug={projectSlug} />;
}

export default function ExplorerPage() {
  return (
    <Suspense fallback={<div className="p-8 text-[--muted-foreground]">Loading explorer...</div>}>
      <ExplorerWithProject />
    </Suspense>
  );
}
