"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { ontology, projects } from "@/lib/api";

type OntologyClassRow = { name: string; instanceCount: number };

/**
 * Link Convex project → latest successful job artifact paths (POST /projects/:slug/register-artifacts),
 * then reload ontology classes. Clears API 428 "Sync Required" when files exist locally.
 */
export function useArtifactLink(projectSlug: string) {
  const [linking, setLinking] = useState(false);

  const linkArtifacts = useCallback(
    async (onClassesLoaded?: (classes: OntologyClassRow[]) => void) => {
      setLinking(true);
      try {
        await projects.registerArtifacts(projectSlug);
        toast.success("Ontology artifacts linked to this project");
        const cls = await ontology.classes(projectSlug);
        onClassesLoaded?.(cls);
        return cls;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Could not link artifacts";
        toast.error(msg);
        throw e;
      } finally {
        setLinking(false);
      }
    },
    [projectSlug],
  );

  return { linking, linkArtifacts };
}
