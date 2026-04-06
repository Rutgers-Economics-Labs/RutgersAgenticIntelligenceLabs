"use client";
import { Suspense, use } from "react";

import { AnalysisWorkspace } from "@/components/analysis/AnalysisWorkspace";
import { Id } from "@/convex/_generated/dataModel";
import { AlertCircle, PlusCircle } from "lucide-react";
import Link from "next/link";

function AnalysisPageInner({ projectSlug }: { projectSlug: string }) {



  if (!projectSlug) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] text-center max-w-md mx-auto space-y-6">
        <div className="w-16 h-16 rounded-full bg-[--primary]/10 flex items-center justify-center text-[--primary]">
           <AlertCircle size={32} />
        </div>
        <div>
          <h2 className="text-2xl font-bold tracking-tight">No Project Selected</h2>
          <p className="text-[--muted-foreground] mt-2">
            Analysis requires an active project context to access its artifacts and data schema.
          </p>
        </div>
        <Link 
          href="/projects" 
          className="inline-flex items-center gap-2 px-6 py-2.5 bg-[--primary] text-white rounded-lg font-bold hover:bg-[--primary]/90 transition-all shadow-lg shadow-[--primary]/20"
        >
          <PlusCircle size={18} />
          Select a Project
        </Link>
      </div>
    );
  }

  return <AnalysisWorkspace projectSlug={projectSlug} />;
}

export default function AnalysisPage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = use(params);
  return (
    <Suspense fallback={<div className="p-8 text-sm text-[--muted-foreground] animate-pulse">Initializing Analysis Workspace...</div>}>
      <AnalysisPageInner projectSlug={project} />
    </Suspense>
  );
}
