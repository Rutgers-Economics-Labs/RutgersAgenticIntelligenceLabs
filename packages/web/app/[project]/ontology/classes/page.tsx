"use client";
import { Suspense, use } from "react";
import OntologyExplorerContent from "@/components/ontology/OntologyExplorerContent";

export default function ExplorerPage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = use(params);
  return (
    <Suspense fallback={<div className="p-8 text-[--muted-foreground]">Loading explorer...</div>}>
      <OntologyExplorerContent projectSlug={project} />
    </Suspense>
  );
}
