export default async function ProjectHomePage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = await params;
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">Project: {project}</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div className="p-6 rounded-xl border border-[--border] bg-[--card]">
          <h2 className="text-sm font-semibold mb-2">Planner</h2>
          <p className="text-xs text-[--muted-foreground]">Long-lived planner thread and active task board summary.</p>
        </div>
        <div className="p-6 rounded-xl border border-[--border] bg-[--card]">
          <h2 className="text-sm font-semibold mb-2">Repository</h2>
          <p className="text-xs text-[--muted-foreground]">Current spec and research plan context from Git.</p>
        </div>
        <div className="p-6 rounded-xl border border-[--border] bg-[--card]">
          <h2 className="text-sm font-semibold mb-2">Artifacts</h2>
          <p className="text-xs text-[--muted-foreground]">Recent reports, datasets, and verification status.</p>
        </div>
      </div>
    </div>
  );
}
