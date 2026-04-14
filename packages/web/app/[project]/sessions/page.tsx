export default async function SessionsPage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = await params;
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">Agent Sessions</h1>
      <p className="text-muted-foreground">Session history and operational timeline for project: {project}</p>
      {/* TODO: Implement run timeline and session events */}
    </div>
  );
}
