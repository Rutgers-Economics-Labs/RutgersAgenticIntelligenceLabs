import { ProjectShell } from "@/components/project-shell";
import { FetchDataHydrateButton } from "@/components/fetch-data-hydrate-button";
import {
  fetchCommandCenter,
  fetchHydrationStatus,
  fetchOntologyClasses,
  fetchOntologyClassGraph,
  fetchOntologyDatabaseGraph,
  fetchOntologyGraph,
  fetchPlannerHome,
  fetchProjectContext,
} from "@/lib/api";
import { OntologyExplorer } from "@/components/ontology-explorer";
import { CoverageExplorer } from "@/components/coverage-explorer";

function OntologyRightRail({
  slug,
  context,
  hydration,
}: {
  slug: string;
  context: Awaited<ReturnType<typeof fetchProjectContext>>;
  hydration: { state?: string; pipelineSlug?: string } | null;
}) {
  const rows = [
    { label: "status", value: context.project?.status ?? "unknown" },
    { label: "hydration", value: hydration?.state ?? "unknown" },
    {
      label: "last hydrated",
      value: context.project?.last_hydrated
        ? new Date(context.project.last_hydrated).toLocaleString("en-US", {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          })
        : "never",
    },
    { label: "pipeline", value: hydration?.pipelineSlug ?? "—" },
  ];

  return (
    <div>
      <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)" }}>
        <span className="rail-label">Ontology</span>
      </div>
      {rows.map(({ label, value }) => (
        <div
          key={label}
          style={{
            padding: "8px 14px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)" }}>
            {label}
          </span>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--fg)" }}>{value}</span>
        </div>
      ))}
      <div style={{ padding: "10px 14px" }}>
        <FetchDataHydrateButton slug={slug} pipelineSlug={hydration?.pipelineSlug} variant="compact" />
      </div>
    </div>
  );
}

export default async function OntologyPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const [home, context, hydrationResult, centerResult] = await Promise.allSettled([
    fetchPlannerHome(slug),
    fetchProjectContext(slug),
    fetchHydrationStatus(slug),
    fetchCommandCenter(slug),
  ]);
  if (home.status !== "fulfilled") throw home.reason;
  if (context.status !== "fulfilled") throw context.reason;

  const homeValue = home.value;
  const contextValue = context.value;
  const hydration = hydrationResult.status === "fulfilled" ? hydrationResult.value : null;
  const center = centerResult.status === "fulfilled" ? centerResult.value : null;
  const projectId = homeValue.project?.id;

  const classes = projectId
    ? await fetchOntologyClasses(projectId)
    : { error: "Project id unavailable." };
  const classList = Array.isArray((classes as { classes?: unknown[] }).classes)
    ? ((classes as { classes: { name: string; count: number }[] }).classes ?? [])
    : [];
  const classError = (classes as { error?: string }).error;

  const [classGraph, instanceGraph, databaseGraph] = projectId
    ? await Promise.all([
        fetchOntologyClassGraph(projectId),
        fetchOntologyGraph(projectId, { limit: 200 }),
        fetchOntologyDatabaseGraph(projectId),
      ])
    : [
        { nodes: [], links: [] },
        { nodes: [], links: [] },
        { nodes: [], links: [] },
      ];

  return (
    <ProjectShell
      slug={slug}
      title="Ontology"
      section="ontology"
      rightRail={<OntologyRightRail slug={slug} context={contextValue} hydration={hydration} />}
    >
      <div style={{ padding: 20 }}>
        {center ? (
          <div style={{ marginBottom: 24 }}>
            <CoverageExplorer slug={slug} center={center} classes={classList} />
          </div>
        ) : null}
        {classError ? (
          <div
            style={{
              padding: 14,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              color: "var(--s-awaiting)",
              borderLeft: "2px solid var(--s-awaiting)",
            }}
          >
            {classError}
          </div>
        ) : projectId ? (
          <OntologyExplorer
            projectId={projectId}
            classes={classList}
            classGraph={classGraph}
            instanceGraph={instanceGraph}
            databaseGraph={databaseGraph}
          />
        ) : (
          <p style={{ fontSize: 12, color: "var(--muted)" }}>Project not loaded.</p>
        )}
      </div>
    </ProjectShell>
  );
}
