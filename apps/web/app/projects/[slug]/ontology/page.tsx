import { ProjectShell } from "@/components/project-shell";
import { StatusPill } from "@/components/status-pill";
import { HydrationRerunButton } from "@/components/hydration-actions";
import { fetchHydrationStatus, fetchOntologyClasses, fetchPlannerHome, fetchProjectContext } from "@/lib/api";

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

  return (
    <ProjectShell
      slug={slug}
      title="Ontology"
      section="ontology"
      rightRail={<OntologyRightRail slug={slug} context={contextValue} home={homeValue} hydration={hydration} />}
    >
      {/* Ontology classes */}
      <div style={{ borderBottom: "1px solid var(--border)" }}>
        <div style={{
          padding: "8px 14px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}>
          <span className="rail-label">Classes</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <HydrationRerunButton slug={slug} pipelineSlug={hydration?.pipelineSlug} />
            {!classError && (
              <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
                {classList.length}
              </span>
            )}
          </div>
        </div>

        {classError ? (
          <div style={{
            padding: "14px",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11,
            color: "var(--s-awaiting)",
            borderLeft: "2px solid var(--s-awaiting)",
            margin: "8px 14px",
          }}>
            {classError}
          </div>
        ) : classList.length === 0 ? (
          <div style={{ padding: "24px 14px", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
            No ontology classes returned yet.
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          }}>
            {classList.slice(0, 48).map((item: any, i: number) => (
              <div key={i} style={{
                padding: "10px 14px",
                borderBottom: "1px solid var(--border)",
                borderRight: "1px solid var(--border)",
              }}>
                <div style={{ fontSize: 12, fontWeight: 500, color: "var(--fg)", marginBottom: 2 }}>
                  {String(item.name ?? item.class_name ?? item.label ?? "class")}
                </div>
                {item.count != null && (
                  <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
                    {item.count} instances
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Data sources + pipelines */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr" }}>
        <div style={{ borderRight: "1px solid var(--border)" }}>
          <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)" }}>
            <span className="rail-label">Data Sources</span>
          </div>
          {(contextValue.data_sources ?? []).length === 0 ? (
            <div style={{ padding: "24px 14px", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
              None discovered.
            </div>
          ) : (
            (contextValue.data_sources ?? []).map((source: any, i: number) => (
              <div key={i} style={{
                padding: "8px 14px",
                borderBottom: "1px solid var(--border)",
                fontSize: 12,
                color: "var(--fg)",
              }}>
                {String(source.name ?? source.slug ?? "source")}
              </div>
            ))
          )}
        </div>

        <div>
          <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)" }}>
            <span className="rail-label">Pipelines</span>
          </div>
          {(contextValue.pipelines ?? []).length === 0 ? (
            <div style={{ padding: "24px 14px", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
              None linked.
            </div>
          ) : (
            (contextValue.pipelines ?? []).map((pipeline: any, i: number) => (
              <div key={i} style={{
                padding: "8px 14px",
                borderBottom: "1px solid var(--border)",
                fontSize: 12,
                color: "var(--fg)",
              }}>
                {String(pipeline.name ?? pipeline.slug ?? "pipeline")}
              </div>
            ))
          )}
        </div>
      </div>
    </ProjectShell>
  );
}
