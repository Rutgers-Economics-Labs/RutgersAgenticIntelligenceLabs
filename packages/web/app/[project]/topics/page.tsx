import { RepoBrowser } from "@/components/project/repo/RepoBrowser";

export default async function TopicsRootPage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = await params;
  return <RepoBrowser projectSlug={project} rootDir="topics" title="Topic Workspace" />;
}
