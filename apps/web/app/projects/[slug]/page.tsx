import Link from "next/link";
import { fetchHydrationStatus, fetchOntologyClasses, fetchPlannerHome } from "@/lib/api";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { CommandShell, EmptyState, InlineStatus } from "@/components/command-center";
import { ApprovalPanel } from "@/components/approval-panel";
import { ReconcileProjectButton } from "@/components/reconcile-actions";
import { OperatorOverviewStrip } from "@/components/operator-overview-strip";
import { getArtifactTrustDisplay } from "@/lib/integrity-ui";
import type { AgentWorkflowSummary, CommandCenter, PlannerHome } from "@/lib/types";

export default async function ProjectHomePage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [homeResult, hydration] = await Promise.all([
    fetchPlannerHome(slug).then((value) => ({ ok: true as const, value })).catch((error) => ({ ok: false as const, error })),
    fetchHydrationStatus(slug).catch(() => null),
  ]);

  const home = homeResult.ok ? homeResult.value : null;
  const center = home ? buildFallbackCommandCenter(home) : null;

  if (!home || !center) {
    const messages = [homeResult]
      .filter((result): result is { ok: false; error: unknown } => !result.ok)
      .map((result) => {
        if (result.error instanceof Error && result.error.message) {
          return result.error.message;
        }
        return "Unknown API error";
      });

    return (
      <div
        style={{
          minHeight: "100vh",
          background: "var(--bg)",
          color: "var(--fg)",
          padding: "48px 24px",
        }}
      >
        <div
          style={{
            maxWidth: 920,
            margin: "0 auto",
            border: "1px solid var(--border)",
            background: "var(--panel)",
          }}
        >
          <div style={{ padding: "18px 20px", borderBottom: "1px solid var(--border)" }}>
            <div className="mono-muted" style={{ fontSize: 10, letterSpacing: "0.16em", textTransform: "uppercase" }}>
              Project Unavailable
            </div>
            <h1 style={{ margin: "8px 0 0", fontSize: 24 }}>{slug}</h1>
          </div>

          <div style={{ padding: 20, display: "grid", gap: 18 }}>
            <div
              style={{
                padding: 16,
                border: "1px solid rgba(239, 68, 68, 0.35)",
                background: "rgba(239, 68, 68, 0.08)",
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: 8 }}>The control-plane API is unavailable.</div>
              <div className="mono-muted" style={{ lineHeight: 1.6 }}>
                This page needs the planner home endpoint before it can render the mission-control UI.
                Right now that server-side request is failing, so the route is showing a safe fallback instead of a 500.
              </div>
            </div>

            <div>
              <div className="mono-muted" style={{ marginBottom: 8, fontSize: 10, letterSpacing: "0.16em", textTransform: "uppercase" }}>
                Errors
              </div>
              <div style={{ display: "grid", gap: 8 }}>
                {messages.map((message, index) => (
                  <pre
                    key={`${message}-${index}`}
                    style={{
                      margin: 0,
                      padding: 12,
                      overflowX: "auto",
                      background: "var(--bg)",
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

            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <Link href="/" style={{ color: "var(--fg)", textDecoration: "underline" }}>
                Back to catalog
              </Link>
              <Link href={`/projects/${slug}/repo`} style={{ color: "var(--fg)", textDecoration: "underline" }}>
                Open repo mirror
              </Link>
              <Link href={`/projects/${slug}/settings`} style={{ color: "var(--fg)", textDecoration: "underline" }}>
                Project settings
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const tasks = home.planner.tasks ?? [];
  const ontologyClasses = home.project?.id
    ? await fetchOntologyClasses(home.project.id).catch(() => ({ classes: [] as Array<{ name: string; count: number }> }))
    : { classes: [] as Array<{ name: string; count: number }> };
  const classPreview = (ontologyClasses.classes ?? [])
    .filter((row): row is { name: string; count: number } => {
      const item = row as { name?: unknown; count?: unknown };
      return typeof item.name === "string" && typeof item.count === "number";
    });
  const meaningfulArtifacts = center.recentArtifacts.filter((artifact) => isMeaningfulArtifact(artifact.path, artifact.name));
  const openTasks = tasks.filter((task: any) => !["done", "backlog", "cancelled"].includes(String(task.status ?? "")));
  const priorityTasks = openTasks
    .filter((task: any) => ["awaiting_approval", "running", "review", "blocked", "ready"].includes(String(task.status ?? "")))
    .slice(0, 6);
  const primaryActionLinks = buildPrimaryActions({
    slug,
    center,
    hydrationState: center.auditors?.ontology?.state ?? null,
  });
  const planSummary = buildPlanSummary(center);
  const queueCounts = {
    running: center.taskCounts.byStatus.running ?? 0,
    review: center.taskCounts.byStatus.review ?? 0,
    waiting: center.taskCounts.byStatus.awaiting_approval ?? 0,
    ready: center.taskCounts.byStatus.ready ?? 0,
  };
  const healthLinks = [
    { label: "Planner", detail: "full queue and dispatch decisions", href: `/projects/${slug}/planner` },
    { label: "Review", detail: "approvals and repair tasks", href: `/projects/${slug}/review` },
    { label: "Ontology", detail: "class coverage and hydration state", href: `/projects/${slug}/ontology` },
    { label: "Integrity", detail: "drift, evidence, and verification", href: `/projects/${slug}/integrity` },
  ];

  const overviewStrip = (
    <OperatorOverviewStrip
      slug={slug}
      center={center}
      pipelineSlug={hydration?.pipelineSlug}
      ontologyClassPreview={classPreview}
    />
  );


  const rightRail = (
    <div className="overview-rail-stack">
      <SectionCard eyebrow="Action Queue" noPad>
        <div style={{ padding: "12px 14px" }}>
          <div className="overview-meta-grid" style={{ marginBottom: 12 }}>
            <div className="overview-meta-card">
              <div className="rail-label">Approvals</div>
              <div className="overview-meta-value">{center.pendingApprovals.length}</div>
            </div>
            <div className="overview-meta-card">
              <div className="rail-label">Ready Tasks</div>
              <div className="overview-meta-value">{queueCounts.ready}</div>
            </div>
          </div>
          {center.pendingApprovals.length ? (
            <ApprovalPanel approvals={center.pendingApprovals.slice(0, 2)} slug={slug} />
          ) : (
            <EmptyState title="Queue is clear" detail="No approvals are blocking dispatch right now." />
          )}
        </div>
      </SectionCard>

      <SectionCard eyebrow="System Health" noPad>
        <div style={{ padding: "12px 14px" }}>
          <InlineStatus label="drift" value={center.projectReality?.hasDrift ? "present" : "clear"} />
          <InlineStatus label="stale sessions" value={center.projectReality?.staleRuntimeSessionCount ?? 0} />
          <InlineStatus label="integrity" value={center.auditedTruth?.integrity?.blocked ? "blocked" : "clear"} />
          <InlineStatus label="goal mode" value={center.goal?.objective ? "configured" : "unset"} />
          <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
            <ReconcileProjectButton slug={slug} />
          </div>
        </div>
      </SectionCard>

      <SectionCard eyebrow="Deep Dives" noPad>
        <div className="overview-deep-links">
          {healthLinks.map((item) => (
            <Link key={item.label} href={item.href as any} className="overview-deep-link">
              <div>
                <div style={{ fontWeight: 700 }}>{item.label}</div>
                <div className="mono-muted">{item.detail}</div>
              </div>
              <span className="overview-inline-link">Open</span>
            </Link>
          ))}
        </div>
      </SectionCard>
    </div>
  );

  return (
    <ProjectShell slug={slug} title="Mission Control" section="overview" rightRail={rightRail}>
      {overviewStrip}
      <div className="overview-main-grid">
        <div className="overview-stack">
          <SectionCard eyebrow="Do This Next" title={center.project.name}>
            <div className="overview-action-grid">
              {primaryActionLinks.map((item, index) => (
                <div key={`${item.title}-${index}`} className={`overview-action-card${index === 0 ? " primary" : ""}`}>
                  <div className="overview-kicker">{item.label}</div>
                  <div className="overview-headline">{item.title}</div>
                  <div className="overview-copy">{item.detail}</div>
                  <div className="overview-link-row">
                    <Link href={item.href as any} className="overview-inline-link">
                      Open {item.destination} →
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard eyebrow="Current Queue" title={`${priorityTasks.length} items need attention`} noPad>
            {priorityTasks.length ? (
              <>
                {priorityTasks.map((task: any) => (
                  <div key={task._id} className="overview-queue-row">
                    <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 700, color: "var(--fg)", lineHeight: 1.35 }}>{task.title}</div>
                        <div className="mono-muted" style={{ marginTop: 4 }}>
                        {truncateTaskDetail(
                          task.latestRunSummary && task.latestRunSummary !== "Not started"
                            ? task.latestRunSummary
                            : task.description,
                        )}
                      </div>
                    </div>
                    <StatusPill value={task.status ?? "unknown"} />
                  </div>
                ))}
                <div style={{ padding: "12px 16px" }}>
                  <Link href={`/projects/${slug}/planner` as any} className="overview-inline-link">
                    Open full planner board →
                  </Link>
                </div>
              </>
            ) : (
              <EmptyState title="No urgent queue items" detail="Open Planner to review backlog and completed work." />
            )}
          </SectionCard>
        </div>

        <div className="overview-stack">
          <SectionCard eyebrow="Project Snapshot" title="What this project is doing">
            <div className="overview-copy" style={{ marginTop: 0 }}>{planSummary}</div>
            <div className="overview-meta-grid" style={{ marginTop: 16 }}>
              <div className="overview-meta-card">
                <div className="rail-label">Running</div>
                <div className="overview-meta-value">{queueCounts.running}</div>
              </div>
              <div className="overview-meta-card">
                <div className="rail-label">In review</div>
                <div className="overview-meta-value">{queueCounts.review}</div>
              </div>
              <div className="overview-meta-card">
                <div className="rail-label">Artifacts</div>
                <div className="overview-meta-value">{meaningfulArtifacts.length}</div>
              </div>
              <div className="overview-meta-card">
                <div className="rail-label">Sources</div>
                <div className="overview-meta-value">{center.sourceSummary.count}</div>
              </div>
            </div>
          </SectionCard>

          <SectionCard eyebrow="Recent Output" title="Latest evidence" noPad>
            {meaningfulArtifacts.length ? (
              meaningfulArtifacts.slice(0, 4).map((artifact) => (
                <Link href={`/projects/${slug}/artifacts` as any} key={artifact.path} className="overview-queue-row">
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700 }}>{artifact.name}</div>
                    <div className="mono-muted">{artifact.path}</div>
                  </div>
                  <StatusPill value={getArtifactTrustDisplay(artifact).label} />
                </Link>
              ))
            ) : (
              <EmptyState title="No output yet" detail="Artifacts will appear here once research or repair runs publish results." />
            )}
          </SectionCard>
        </div>
      </div>
    </ProjectShell>
  );
}

function buildPrimaryActions({
  slug,
  center,
  hydrationState,
}: {
  slug: string;
  center: CommandCenter;
  hydrationState?: string | null;
}) {
  const items: Array<{ label: string; title: string; detail: string; href: string; destination: string }> = [];

  if (center.pendingApprovals.length) {
    items.push({
      label: "First move",
      title: `Review ${center.pendingApprovals.length} pending approval${center.pendingApprovals.length === 1 ? "" : "s"}`,
      detail: "The planner is paused on approval-gated work. Clearing this queue is the fastest way to unblock progress.",
      href: `/projects/${slug}/review`,
      destination: "review",
    });
  }

  if (center.blockerSummary?.blocked) {
    items.push({
      label: "Primary blocker",
      title: center.blockerSummary.headline || "Clear the active blocker",
      detail: center.blockerSummary.reasons?.[0] || "Open the recommended fix surface and resolve the gating issue.",
      href: center.blockerSummary.fixHref || `/projects/${slug}/integrity`,
      destination: center.blockerSummary.fixSection || "integrity",
    });
  }

  if (hydrationState === "stale_on_this_device" || hydrationState === "not_hydrated") {
    items.push({
      label: "Data readiness",
      title: "Hydrate ontology data on this device",
      detail: "The ontology isn’t locally ready yet, so graph and class views will stay incomplete until hydration finishes.",
      href: `/projects/${slug}/ontology`,
      destination: "ontology",
    });
  }

  if ((center.taskCounts.byStatus.ready ?? 0) > 0) {
    items.push({
      label: "Ready work",
      title: `${center.taskCounts.byStatus.ready} task${center.taskCounts.byStatus.ready === 1 ? "" : "s"} are ready to run`,
      detail: "Open Planner to launch or sequence the next batch instead of scanning the full board here.",
      href: `/projects/${slug}/planner`,
      destination: "planner",
    });
  }

  if (!items.length) {
    items.push({
      label: "Next move",
      title: center.nextAction || "Review the planner queue",
      detail: "The project is relatively clear right now. Open Planner to inspect backlog, active work, and completion state.",
      href: `/projects/${slug}/planner`,
      destination: "planner",
    });
  }

  return items.slice(0, 3);
}

function truncateTaskDetail(value: string | null | undefined): string {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "No recent execution summary recorded yet.";
  return text.length > 140 ? `${text.slice(0, 137)}...` : text;
}

function buildPlanSummary(center: CommandCenter): string {
  const summary = String(center.currentPlan.summary ?? "").trim();
  if (summary && !summary.toLowerCase().startsWith("phase:")) return summary;
  if (center.blockerSummary?.headline) return center.blockerSummary.headline;
  if (center.nextAction) return center.nextAction;
  return "Open Planner to inspect the live queue and durable repo state.";
}

function isMeaningfulArtifact(path: string | null | undefined, name: string | null | undefined): boolean {
  const value = `${path ?? ""} ${name ?? ""}`.toLowerCase();
  return !value.includes(".ds_store") && !value.includes("__pycache__") && !value.endsWith(".pyc");
}

function buildFallbackCommandCenter(home: PlannerHome): CommandCenter {
  const tasks = home.planner.tasks ?? [];
  const approvals = home.planner.approvals ?? [];
  const sessions = home.planner.sessions ?? [];
  const byStatus = tasks.reduce<Record<string, number>>((counts, task) => {
    const status = String(task.status ?? "unknown");
    counts[status] = (counts[status] ?? 0) + 1;
    return counts;
  }, {});
  const summary = home.controlPlane ?? {};
  const headline = String(summary.currentBlocker ?? "").trim();
  const closeoutCertificate = normalizeCloseoutCertificate(summary.closeoutCertificate);
  const auditors = normalizeAuditors(summary.auditors);

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
      summary: summary.nextAction ?? "Open Planner to inspect the live queue and durable repo state.",
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
    nextAction: summary.nextAction ?? "Open Planner to inspect the live queue and durable repo state.",
    goal: summary.goal ?? null,
    taskCounts: {
      total: summary.taskCounts?.total ?? tasks.length,
      byStatus: summary.taskCounts?.byStatus ?? byStatus,
    },
    activeSessions: sessions,
    pendingApprovals: approvals,
    recentArtifacts: summary.recentArtifacts ?? [],
    sourceSummary: summary.sourceSummary ?? {
      count: 0,
      statusCounts: {},
      freshnessCounts: {},
      admissibilityCounts: {},
    },
    skillSummary: summary.skillSummary ?? {
      count: 0,
      agentRolesWithSkillAccess: [],
    },
    integritySummary: summary.integritySummary ?? {
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
    blockerSummary: summary.blockerSummary ?? {
      blocked: Boolean(headline),
      headline: headline || "No active blocker.",
      reasons: headline ? [headline] : [],
      repairs: [],
      category: headline ? "closeout_pending" : "clear",
      categoryLabel: headline ? "Needs attention" : "Clear",
      severity: headline ? "warning" : "ok",
      fixSection: headline ? "planner" : null,
      fixHref: headline ? `/projects/${home.project?.slug ?? ""}/planner` : null,
    },
    repairQueue: summary.repairQueue ?? {
      count: 0,
      readyCount: 0,
      runningCount: 0,
      byStatus: {},
      tasks: [],
    },
    recommendedRepairTask: summary.recommendedRepairTask ?? null,
    projectReality: normalizeProjectReality(summary.projectReality, sessions.length),
    auditors,
    closeoutCertificate,
    repoHealth: normalizeRepoHealth(home.repoHealth, home.project?.localRepoPath),
    snapshot: summary.snapshot ?? {
      loaded: false,
      path: "research_plan/state/control_plane_snapshot.json",
      generatedAt: null,
      version: 1,
    },
  };
}

function normalizeProjectReality(
  value: Record<string, unknown> | null | undefined,
  activeRuntimeSessionCount: number,
): CommandCenter["projectReality"] {
  type ProjectReality = NonNullable<CommandCenter["projectReality"]>;
  if (!value || typeof value !== "object") {
    return {
      hasDrift: false,
      duplicateTaskFileCount: 0,
      taskSessionMismatchCount: 0,
      staleRuntimeSessionCount: 0,
      staleAuditSessionCount: 0,
      terminalSessionCount: 0,
      activeRuntimeSessionCount,
      details: {
        duplicateTaskFiles: [],
        taskSessionMismatchTaskIds: [],
        staleRuntimeSessionIds: [],
        staleAuditSessionIds: [],
        terminalSessionIds: [],
        activeRuntimeSessionIds: [],
      },
    };
  }
  return {
    hasDrift: Boolean(value.hasDrift),
    duplicateTaskFileCount: Number(value.duplicateTaskFileCount ?? 0),
    taskSessionMismatchCount: Number(value.taskSessionMismatchCount ?? 0),
    staleRuntimeSessionCount: Number(value.staleRuntimeSessionCount ?? 0),
    staleAuditSessionCount: Number(value.staleAuditSessionCount ?? 0),
    terminalSessionCount: Number(value.terminalSessionCount ?? 0),
    activeRuntimeSessionCount: Number(value.activeRuntimeSessionCount ?? activeRuntimeSessionCount),
    runningAgentStatusDriftCount: typeof value.runningAgentStatusDriftCount === "number" ? value.runningAgentStatusDriftCount : undefined,
    runningAgentRoleDriftCount: typeof value.runningAgentRoleDriftCount === "number" ? value.runningAgentRoleDriftCount : undefined,
    runningAgentRunnerDriftCount: typeof value.runningAgentRunnerDriftCount === "number" ? value.runningAgentRunnerDriftCount : undefined,
    ontologyArtifactDriftCount: typeof value.ontologyArtifactDriftCount === "number" ? value.ontologyArtifactDriftCount : undefined,
    artifactRegistryDriftCount: typeof value.artifactRegistryDriftCount === "number" ? value.artifactRegistryDriftCount : undefined,
    secretPolicyRoleDriftCount: typeof value.secretPolicyRoleDriftCount === "number" ? value.secretPolicyRoleDriftCount : undefined,
    roleConfigAliasDriftCount: typeof value.roleConfigAliasDriftCount === "number" ? value.roleConfigAliasDriftCount : undefined,
    details: typeof value.details === "object" && value.details ? (value.details as ProjectReality["details"]) : undefined,
  };
}

function normalizeRepoHealth(
  value: PlannerHome["repoHealth"] | null | undefined,
  localRepoPath?: string | null,
): CommandCenter["repoHealth"] {
  return {
    hasLocalRepo: Boolean(value?.hasLocalRepo ?? localRepoPath),
    hasRailYaml: Boolean(value?.hasRailYaml ?? localRepoPath),
    hasResearchPlan: Boolean(value?.hasResearchPlan ?? localRepoPath),
  };
}

function emptyAgentWorkflowSummary(): AgentWorkflowSummary {
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
    const candidate = item as { status?: unknown; blockers?: unknown; state?: unknown };
    return [[
      key,
      {
        status: typeof candidate.status === "string" ? candidate.status : "unknown",
        blockers: Array.isArray(candidate.blockers) ? candidate.blockers.filter((entry): entry is string => typeof entry === "string") : undefined,
        state: typeof candidate.state === "string" ? candidate.state : null,
      },
    ]];
  });
  return Object.fromEntries(entries);
}

function normalizeCloseoutCertificate(
  value: Record<string, unknown> | null | undefined,
): CommandCenter["closeoutCertificate"] | undefined {
  if (!value || typeof value !== "object") return undefined;
  const candidate = value as { status?: unknown; phase?: unknown; headline?: unknown; blockers?: unknown };
  const status = candidate.status;
  if (status !== "issued" && status !== "pending" && status !== "would_issue_if") return undefined;
  return {
    status,
    phase: typeof candidate.phase === "string" ? candidate.phase : "unknown",
    headline: typeof candidate.headline === "string" ? candidate.headline : "Closeout state unavailable.",
    blockers: Array.isArray(candidate.blockers) ? candidate.blockers.filter((entry): entry is string => typeof entry === "string") : [],
  };
}
