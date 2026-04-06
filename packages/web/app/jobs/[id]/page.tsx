"use client";

/**
 * Legacy URLs used `/jobs/:id` but job UI lives under `/[project]/jobs/:id`.
 * Resolve the project from the job document and redirect.
 */
import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";

export default function LegacyJobDeepLink({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const job = useQuery(api.jobs.get, { jobId: id as Id<"hydrationJobs"> });
  const execution = useQuery((api as any).executions.get, { jobId: id as any });

  const queriesPending = job === undefined || execution === undefined;
  const active = job || execution;

  const projectId =
    active && "projectId" in active && active.projectId
      ? (active.projectId as Id<"projects">)
      : undefined;

  const projectDoc = useQuery(api.projects.getById, projectId ? { projectId } : "skip");

  useEffect(() => {
    if (queriesPending) return;
    if (!active) {
      router.replace("/projects");
      return;
    }
    if (!projectId) {
      router.replace("/projects");
      return;
    }
    if (projectDoc === undefined) return;
    if (!projectDoc) {
      router.replace("/projects");
      return;
    }
    router.replace(`/${projectDoc.slug}/jobs/${id}`);
  }, [queriesPending, active, projectId, projectDoc, id, router]);

  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-2 p-8 text-sm text-[--muted-foreground]">
      <p>Redirecting to job…</p>
    </div>
  );
}
