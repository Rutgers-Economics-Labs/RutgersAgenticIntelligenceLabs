import { Suspense } from "react";
import { fetchPlannerHome, fetchRunnerSessions } from "@/lib/api";
import type { PlannerHome, RunnerSession } from "@/lib/types";
import { RunsClient } from "./client";

type RunsPageProps = {
  params: Promise<{ slug: string }>;
};

export default async function RunsPage({ params }: RunsPageProps) {
  const { slug } = await params;
  let initialSessions: RunnerSession[] = [];
  let initialHome: PlannerHome | null = null;

  const [sessionsResult, homeResult] = await Promise.allSettled([
    fetchRunnerSessions(slug),
    fetchPlannerHome(slug),
  ]);

  if (sessionsResult.status === "fulfilled") {
    initialSessions = sessionsResult.value.sessions;
  }
  if (homeResult.status === "fulfilled") {
    initialHome = homeResult.value;
  }

  return (
    <Suspense>
      <RunsClient slug={slug} initialSessions={initialSessions} initialHome={initialHome} />
    </Suspense>
  );
}
