import { fetchPlannerHome } from "@/lib/api";
import { PlannerWorkbench } from "@/components/planner-workbench";

export default async function PlannerPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const initialHome = await fetchPlannerHome(slug).catch(() => null);
  return <PlannerWorkbench slug={slug} initialHome={initialHome} />;
}
