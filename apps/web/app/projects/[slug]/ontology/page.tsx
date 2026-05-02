import { ProjectShell } from "@/components/project-shell";
import { StatusPill } from "@/components/status-pill";
import { HydrationRerunButton } from "@/components/hydration-actions";
import { fetchHydrationStatus, fetchOntologyClasses, fetchPlannerHome, fetchProjectContext, fetchOntologyGraph } from "@/lib/api";
import { EntityExplorer } from "@/components/entity-explorer";
import { GraphVisualizer } from "@/components/graph-visualizer";
import { MetadataExplorer } from "@/components/metadata-explorer";

function OntologyRightRail({ slug, context, home, hydration }: { slug: string; context: any; home: any; hydration: any }) {
  const rows = [
    { label: "status",        value: context.project?.status ?? "unknown" },
    { label: "hydration",     value: hydration?.state ?? "unknown" },
    { label: "device",        value: hydration?.deviceId ? String(hydration.deviceId).slice(0, 10) : "unknown" },
    { label: "pipeline",      value: hydration?.pipelineSlug ?? "unknown" },
    { label: "last hydrated", value: context.project?.last_hydrated
        ? new Date(context.project.last_hydrated).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })
        : "never" },
    { label: "data sources",  value: String(context.data_sources?.length ?? 0) },
    { label: "pipelines",     value: String(context.pipelines?.length ?? 0) },
    { label: "current plan",  value: home.planner.files?.currentPlan ? "present" : "missing" },
  ];
  return (
    <div>
      <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)" }}>
        <span className="rail-label">Project State</span>
      </div>
      {rows.map(({ label, value }) => (
        <div key={label} style={{
          padding: "8px 14px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)" }}>{label}</span>
          {["present", "missing"].includes(value) ? (
            <StatusPill value={value} />
          ) : (
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--fg)" }}>{value}</span>
          )}
        </div>
      ))}
      <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)" }}>
        <HydrationRerunButton slug={slug} pipelineSlug={hydration?.pipelineSlug} compact />
      </div>
      {hydration && (
        <>
          <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)", borderTop: "1px solid var(--border)" }}>
            <span className="rail-label">Artifacts By Node</span>
          </div>
          <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)" }}>this node</span>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--fg)" }}>{hydration.currentDeviceArtifacts?.length ?? 0}</span>
          </div>
          <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)" }}>other nodes</span>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--fg)" }}>{hydration.otherDeviceArtifacts?.length ?? 0}</span>
          </div>
        </>
      )}
    </div>
  );
}

export default async function OntologyPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [home, context, hydrationResult] = await Promise.allSettled([
    fetchPlannerHome(slug),
    fetchProjectContext(slug),
    fetchHydrationStatus(slug),
  ]);
  if (home.status !== "fulfilled") throw home.reason;
  if (context.status !== "fulfilled") throw context.reason;
  const homeValue = home.value;
  const contextValue = context.value;
  const hydration = hydrationResult.status === "fulfilled" ? hydrationResult.value : null;
  const classes = homeValue.project?.id
    ? await fetchOntologyClasses(homeValue.project.id)
    : { error: "Project id unavailable." };
  const classList = Array.isArray((classes as any).classes) ? (classes as any).classes : [];
  const classError = (classes as any).error as string | undefined;

  const graphData = homeValue.project?.id 
    ? await fetchOntologyGraph(homeValue.project.id, { limit: 100 })
    : { nodes: [], links: [] };

  return (
    <ProjectShell
      slug={slug}
      title="Ontology"
      section="ontology"
      rightRail={<OntologyRightRail slug={slug} context={contextValue} home={homeValue} hydration={hydration} />}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "24px", padding: "20px" }}>
        
        {/* Metadata Explorer */}
        <section>
          <div style={{ marginBottom: "12px", borderBottom: "1px solid var(--border)", paddingBottom: "6px" }}>
            <span className="rail-label">Metadata Explorer</span>
          </div>
          <MetadataExplorer slug={slug} />
        </section>

        {/* Graph Visualizer */}
        <section>
          <div style={{ marginBottom: "12px", borderBottom: "1px solid var(--border)", paddingBottom: "6px" }}>
            <span className="rail-label">Knowledge Graph</span>
          </div>
          <GraphVisualizer nodes={graphData.nodes || []} links={graphData.links || []} />
        </section>

        {/* Entity Explorer */}
        <section>
          <div style={{ marginBottom: "12px", borderBottom: "1px solid var(--border)", paddingBottom: "6px" }}>
            <span className="rail-label">Entity Explorer</span>
          </div>
          {!classError && homeValue.project?.id && (
             <EntityExplorer projectId={homeValue.project.id} classes={classList} />
          )}
        </section>

        {/* Original Class Grid (Summary) */}
        <section>
          <div style={{ marginBottom: "12px", borderBottom: "1px solid var(--border)", paddingBottom: "6px" }}>
            <span className="rail-label">Class Summary</span>
          </div>
          {classError ? (
            <div style={{ padding: "14px", fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--s-awaiting)", borderLeft: "2px solid var(--s-awaiting)" }}>
              {classError}
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "8px" }}>
              {classList.map((item: any, i: number) => (
                <div key={i} style={{ padding: "10px", background: "var(--panel)", border: "1px solid var(--border)", borderRadius: "4px" }}>
                  <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--fg)" }}>{item.name}</div>
                  <div style={{ fontSize: "10px", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>{item.count} instances</div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </ProjectShell>
  );
}
