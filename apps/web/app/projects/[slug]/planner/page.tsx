import { PlannerWorkbench } from "@/components/planner-workbench";

export default async function PlannerPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <PlannerWorkbench slug={slug} />;
}
