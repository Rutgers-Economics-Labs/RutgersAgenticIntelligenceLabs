import { RepoBrowser } from "@/components/project/repo/RepoBrowser";

export default async function SpecsPage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = await params;
  return <RepoBrowser projectSlug={project} rootDir="specs" title="Specifications" />;
}
