import { fetchDashboard, fetchPlannerHome } from "@/lib/api";
import type { DashboardResponse, PlannerHome } from "@/lib/types";
import DashboardClient from "./client";

type DashboardPageProps = {
  params: Promise<{ slug: string }>;
};

export default async function DashboardPage({ params }: DashboardPageProps) {
  const { slug } = await params;

  const [plannerHomeResult, dashboardResult] = await Promise.allSettled([
    fetchPlannerHome(slug),
    fetchDashboard(slug),
  ]);

  const initialPlannerHome: PlannerHome | null =
    plannerHomeResult.status === "fulfilled" ? plannerHomeResult.value : null;
  const initialDashboard: DashboardResponse | null =
    dashboardResult.status === "fulfilled" ? dashboardResult.value : null;

  const errors: string[] = [];
  if (plannerHomeResult.status === "rejected") {
    errors.push(
      plannerHomeResult.reason instanceof Error && plannerHomeResult.reason.message
        ? plannerHomeResult.reason.message
        : String(plannerHomeResult.reason),
    );
  }
  if (dashboardResult.status === "rejected") {
    errors.push(
      dashboardResult.reason instanceof Error && dashboardResult.reason.message
        ? dashboardResult.reason.message
        : String(dashboardResult.reason),
    );
  }

  return (
    <DashboardClient
      slug={slug}
      initialPlannerHome={initialPlannerHome}
      initialDashboard={initialDashboard}
      initialErrors={errors}
    />
  );
}
