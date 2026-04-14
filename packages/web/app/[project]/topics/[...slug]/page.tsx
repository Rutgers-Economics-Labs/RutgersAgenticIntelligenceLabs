import { RepoBrowser } from "@/components/project/repo/RepoBrowser";

export default async function TopicsDeepLinkPage({ params }: { params: Promise<{ project: string, slug: string[] }> }) {
  const { project, slug } = await params;
  const path = slug.join("/");
  return <RepoBrowser projectSlug={project} rootDir="topics" title="Topic Workspace" defaultSelectedPath={`topics/${path}`} />;
}
