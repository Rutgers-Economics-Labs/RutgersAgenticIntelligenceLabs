import { RepoBrowser } from "@/components/project/repo/RepoBrowser";

export default async function PlanPage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = await params;
  return <RepoBrowser projectSlug={project} rootDir="research_plan" title="Research Plan" />;
}
