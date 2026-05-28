import { ProjectShell } from "@/components/project-shell";
import { FetchDataHydrateButton } from "@/components/fetch-data-hydrate-button";
import {
  fetchHydrationStatus,
  fetchOntologyClasses,
  fetchOntologyClassGraph,
  fetchOntologyDatabaseGraph,
  fetchOntologyGraph,
  fetchPlannerHome,
} from "@/lib/api";
import { OntologyExplorer } from "@/components/ontology-explorer";
import { CoverageExplorer } from "@/components/coverage-explorer";
import { PageIntro } from "@/components/page-intro";
import type { CommandCenter, PlannerHome } from "@/lib/types";

function OntologyRightRail({
  slug,
  home,
  hydration,
}: {
  slug: string;
  home: PlannerHome;
  hydration: { state?: string; pipelineSlug?: string } | null;
}) {
  const rows = [
    { label: "status", value: home.project?.status ?? "unknown" },
    { label: "hydration", value: hydration?.state ?? "unknown" },
    { label: "pipeline", value: hydration?.pipelineSlug ?? "—" },
    { label: "snapshot", value: home.controlPlane?.snapshot?.loaded ? "repo-backed" : "live" },
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
  const [home, hydrationResult] = await Promise.allSettled([
    fetchPlannerHome(slug),
    fetchHydrationStatus(slug),
  ]);
  if (home.status !== "fulfilled") {
    const messages = [home]
      .filter((result): result is PromiseRejectedResult => result.status === "rejected")
      .map((result) => {
        const reason = result.reason;
        if (reason instanceof Error && reason.message) {
          return reason.message;
        }
        return String(reason ?? "Unknown API error");
      });

    return (
      <ProjectShell
        slug={slug}
        title="Ontology"
        section="ontology"
      >
        <div style={{ padding: 20, display: "grid", gap: 18 }}>
          <PageIntro
            title="Explore the project's classes, graph coverage, and hydrated data."
            detail="Ontology is the data model view. Use it when you want to inspect classes, entity graphs, and hydration status rather than steer the task board."
            actions={[
              { label: "Open Dashboard", href: `/projects/${slug}/dashboard` },
              { label: "Back to Overview", href: `/projects/${slug}` },
            ]}
          />
          <div
            style={{
              padding: 16,
              border: "1px solid rgba(239, 68, 68, 0.35)",
              background: "rgba(239, 68, 68, 0.08)",
            }}
          >
            <div style={{ fontWeight: 700, marginBottom: 8 }}>The ontology control-plane is unavailable.</div>
            <div className="mono-muted" style={{ lineHeight: 1.6 }}>
              This page needs the repo-backed planner home endpoint before it can render ontology state.
            </div>
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            {messages.map((message, index) => (
              <pre
                key={`${message}-${index}`}
                style={{
                  margin: 0,
                  padding: 12,
                  overflowX: "auto",
                  background: "var(--panel)",
                  border: "1px solid var(--border)",
                  fontSize: 12,
                  whiteSpace: "pre-wrap",
                }}
              >
                {message}
              </pre>
            ))}
          </div>
        </div>
      </ProjectShell>
    );
  }

  const homeValue = home.value;
  const hydration = hydrationResult.status === "fulfilled" ? hydrationResult.value : null;
  const center = buildOntologyFallbackCommandCenter(homeValue);
  const projectId = homeValue.project?.id;
  const ontologyStateClassification = center.auditors?.ontology?.stateClassification;
  const ontologyUnavailable =
    !projectId ||
    hydration?.state === "not_hydrated" ||
    ontologyStateClassification === "not_applicable";

  const classes = !ontologyUnavailable && projectId
    ? await fetchOntologyClasses(projectId)
    : { classes: [] as Array<{ name: string; count: number }> };
  const classList = Array.isArray((classes as { classes?: unknown[] }).classes)
    ? ((classes as { classes: { name: string; count: number }[] }).classes ?? [])
    : [];
  const classError = (classes as { error?: string }).error;

  const [classGraph, instanceGraph, databaseGraph] = !ontologyUnavailable && projectId
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
      rightRail={<OntologyRightRail slug={slug} home={homeValue} hydration={hydration} />}
    >
      <div style={{ padding: 20 }}>
        <PageIntro
          title="Explore the project's classes, graph coverage, and hydrated data."
          detail="Ontology is the data model view. Use it to inspect classes and entity graphs after hydration, then jump back to Dashboard if you want charts built on top of those tables."
          actions={[
            { label: "Open Dashboard", href: `/projects/${slug}/dashboard` },
            { label: "Back to Overview", href: `/projects/${slug}` },
          ]}
        />
        {center ? (
          <div style={{ marginBottom: 24 }}>
            <CoverageExplorer slug={slug} center={center} classes={classList} />
          </div>
        ) : null}
        {ontologyUnavailable ? (
          <div
            style={{
              padding: 14,
              border: "1px solid var(--border)",
              background: "var(--panel)",
              display: "grid",
              gap: 10,
            }}
          >
            <div style={{ fontWeight: 700, color: "var(--fg)" }}>No active ontology for this project.</div>
            <div className="mono-muted" style={{ lineHeight: 1.6 }}>
              This project is document-heavy and currently has no hydrated ontology artifact on this device.
              Use <span style={{ color: "var(--fg)" }}>Fetch data &amp; hydrate</span> if you expect a DuckDB-backed ontology,
              or use the repo/artifact views for the literature workflow.
            </div>
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
        ) : !ontologyUnavailable && projectId ? (
          <OntologyExplorer
            slug={slug}
            projectId={projectId}
            classes={classList}
            classGraph={classGraph}
            instanceGraph={instanceGraph}
            databaseGraph={databaseGraph}
            hydrationState={hydration?.state ?? null}
            pipelineSlug={hydration?.pipelineSlug ?? null}
          />
        ) : !ontologyUnavailable ? (
          <p style={{ fontSize: 12, color: "var(--muted)" }}>Project not loaded.</p>
        ) : null}
      </div>
    </ProjectShell>
  );
}

function buildOntologyFallbackCommandCenter(home: PlannerHome): CommandCenter {
  const summary = home.controlPlane ?? {};

  return {
    project: {
      id: home.project?.id ?? "",
      name: home.project?.name ?? "Project",
      slug: home.project?.slug ?? "",
      status: home.project?.status ?? null,
      localRepoPath: home.project?.localRepoPath ?? null,
      defaultBranch: null,
    },
    currentPlan: {
      path: home.planner.files?.currentPlan ?? null,
      summary: summary.nextAction ?? "Open Planner to inspect ontology tasks and hydration state.",
      content: undefined,
    },
    missionBrief: summary.missionBrief
      ? {
          current: summary.missionBrief.current ?? "Planner summary unavailable.",
          next: summary.missionBrief.next ?? "Open Planner to continue.",
          sourceSessionId: summary.missionBrief.sourceSessionId ?? null,
          sourceRole: summary.missionBrief.sourceRole ?? null,
          sourceStatus: summary.missionBrief.sourceStatus ?? null,
          sourceUpdatedAt: summary.missionBrief.sourceUpdatedAt ?? null,
        }
      : null,
    nextAction: summary.nextAction ?? "Open Planner to inspect ontology tasks and hydration state.",
    goal: null,
    taskCounts: {
      total: home.planner.tasks?.length ?? 0,
      byStatus: {},
    },
    activeSessions: home.planner.sessions ?? [],
    pendingApprovals: home.planner.approvals ?? [],
    recentArtifacts: [],
    sourceSummary: {
      count: 0,
      statusCounts: {},
      freshnessCounts: {},
      admissibilityCounts: {},
    },
    skillSummary: {
      count: 0,
      agentRolesWithSkillAccess: [],
    },
    integritySummary: {
      staleArtifactCount: 0,
      sourceFreshnessCounts: {},
      sourceAdmissibilityCounts: {},
      agentWorkflow: emptyAgentWorkflowSummary(),
    },
    ontologyFollowUps: summary.ontologyFollowUps ?? {
      path: null,
      questions: [],
      classificationCounts: {},
    },
    auditedTruth: null,
    recentAudits: [],
    currentBlocker: summary.currentBlocker ?? null,
    blockerSummary: undefined,
    repairQueue: {
      count: 0,
      readyCount: 0,
      runningCount: 0,
      byStatus: {},
      tasks: [],
    },
    recommendedRepairTask: null,
    projectReality: undefined,
    auditors: normalizeAuditors(summary.auditors),
    repoHealth: {
      hasLocalRepo: Boolean(home.project?.localRepoPath),
      hasRailYaml: true,
      hasResearchPlan: true,
    },
    snapshot: summary.snapshot ?? {
      loaded: false,
      path: "research_plan/state/control_plane_snapshot.json",
      generatedAt: null,
      version: 1,
    },
    closeoutCertificate: undefined,
  };
}

function emptyAgentWorkflowSummary(): NonNullable<CommandCenter["integritySummary"]>["agentWorkflow"] {
  return {
    research: { status: "unknown", requirements: [] },
    data: { status: "unknown", requirements: [] },
    coding: { status: "unknown", requirements: [] },
    artifact: { status: "unknown", requirements: [] },
    health: { status: "unknown", requirements: [] },
  };
}

function normalizeAuditors(value: Record<string, unknown> | null | undefined): CommandCenter["auditors"] {
  if (!value) return {};
  const entries = Object.entries(value).flatMap(([key, item]) => {
    if (!item || typeof item !== "object") return [];
    const candidate = item as {
      status?: unknown;
      blockers?: unknown;
      state?: unknown;
      stateClassification?: unknown;
    };
    return [[
      key,
      {
        status: typeof candidate.status === "string" ? candidate.status : "unknown",
        blockers: Array.isArray(candidate.blockers)
          ? candidate.blockers.filter((entry): entry is string => typeof entry === "string")
          : undefined,
        state: typeof candidate.state === "string" ? candidate.state : null,
        stateClassification:
          typeof candidate.stateClassification === "string" ? candidate.stateClassification : null,
      },
    ]];
  });
  return Object.fromEntries(entries);
}
