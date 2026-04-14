export default async function ArtifactsPage({ params }: { params: Promise<{ project: string, slug: string[] }> }) {
  const { project, slug } = await params;
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">Artifact Explorer</h1>
      <p className="text-muted-foreground">Browsing artifact: {slug?.join('/') || 'root'} in project: {project}</p>
      {/* TODO: Implement artifact viewer plane */}
    </div>
  );
}
