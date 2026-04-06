"use client";

import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { use, useState, useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import useSWR from "swr";
import Editor from "@monaco-editor/react";

const fetcher = (url: string) => fetch(url).then((res) => res.json());

function SchemaContent({ projectSlug }: { projectSlug: string }) {
  const project = useQuery(api.projects.get, { slug: projectSlug });

  const ontologyConfigSlug = project?.ontologyConfigSlug;
  const ontologyConfig = useQuery(api.configs.getOntology, ontologyConfigSlug ? { slug: ontologyConfigSlug } : "skip");

  // Fetch the engine kernel YAML
  const { data: kernelData } = useSWR("/api/v1/ontology-kernel", fetcher);

  // We could also fetch a dynamically merged YAML if there's an endpoint for it,
  // or simulate the merged view by concatenating them or showing what the backend compiles.
  // The spec says: "Merged" tab shows what the engine actually sees — kernel + project merged.
  // Assuming `/api/v1/ontology/schema?project=slug` returns the full compiled schema.
  // If not, we'll construct it in frontend. For now, try fetching it or just falling back to concatenation.
  const { data: mergedData } = useSWR(`/api/v1/ontology/schema?project=${projectSlug}`, fetcher);

  const kernelYaml = kernelData?.yaml || kernelData?.content || "# Kernel YAML not found or loading...";
  const projectYaml = ontologyConfig?.content || "# Project ontology not configured yet.";

  // If no dedicated merged endpoint exists, we append them for display purposes.
  // Ideally, the backend `get_compiled_ontology` output is best.
  const mergedYaml = mergedData?.yaml || mergedData?.content || `${kernelYaml}\n\n# --- Project Extension ---\n\n${projectYaml}`;

  if (!project) {
    return <div className="flex h-full items-center justify-center"><div className="animate-pulse">Loading schema...</div></div>;
  }

  return (
    <div className="flex flex-col h-full w-full max-w-6xl mx-auto p-10 pb-20">
      <div className="flex justify-between items-center mb-6 shrink-0">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Ontology Schema</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Read-only view of the merged ontology configuration driving this project.
          </p>
        </div>
      </div>

      <div className="flex-1 min-h-0 border border-border rounded-md overflow-hidden flex flex-col bg-card">
        <Tabs defaultValue="merged" className="flex flex-col h-full">
          <div className="px-4 py-2 border-b border-border bg-muted/20 flex items-center justify-between">
            <TabsList className="h-8">
              <TabsTrigger value="merged" className="text-xs">Merged</TabsTrigger>
              <TabsTrigger value="project" className="text-xs">Project Extension</TabsTrigger>
              <TabsTrigger value="kernel" className="text-xs">Kernel</TabsTrigger>
            </TabsList>
          </div>

          <div className="flex-1 relative">
            <TabsContent value="merged" className="absolute inset-0 m-0 border-0">
              <Editor
                language="yaml"
                theme="vs-dark"
                value={mergedYaml}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  fontSize: 13,
                  fontFamily: "var(--font-mono)",
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                }}
              />
            </TabsContent>

            <TabsContent value="project" className="absolute inset-0 m-0 border-0">
              <Editor
                language="yaml"
                theme="vs-dark"
                value={projectYaml}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  fontSize: 13,
                  fontFamily: "var(--font-mono)",
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                }}
              />
            </TabsContent>

            <TabsContent value="kernel" className="absolute inset-0 m-0 border-0">
              <Editor
                language="yaml"
                theme="vs-dark"
                value={kernelYaml}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  fontSize: 13,
                  fontFamily: "var(--font-mono)",
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                }}
              />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
}

import { Suspense } from "react";

export default function OntologySchemaPage({ params }: { params: Promise<{ project: string }> }) {
  const { project: projectSlug } = use(params);

  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center"><div className="animate-pulse">Loading schema...</div></div>}>
      <SchemaContent projectSlug={projectSlug} />
    </Suspense>
  );
}
