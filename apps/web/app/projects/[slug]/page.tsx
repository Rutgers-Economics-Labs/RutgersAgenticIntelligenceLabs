import Link from "next/link";
import { fetchCommandCenter, fetchHydrationStatus, fetchOntologyClasses, fetchPlannerHome } from "@/lib/api";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { AgentRunCard, CommandShell, InlineStatus, MetricStrip, TaskBoard } from "@/components/command-center";
import { ApprovalPanel } from "@/components/approval-panel";
import { ReconcileProjectButton } from "@/components/reconcile-actions";
import { OperatorOverviewStrip } from "@/components/operator-overview-strip";
import { getArtifactTrustDisplay } from "@/lib/integrity-ui";

export default async function ProjectHomePage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [center, home, hydration] = await Promise.all([
    fetchCommandCenter(slug),
    fetchPlannerHome(slug),
    fetchHydrationStatus(slug).catch(() => null),
  ]);
  const tasks = home.planner.tasks ?? [];
  const ontologyClasses = home.project?.id
    ? await fetchOntologyClasses(home.project.id).catch(() => ({ classes: [] as Array<{ name: string; count: number }> }))
    : { classes: [] as Array<{ name: string; count: number }> };
  const classPreview = (ontologyClasses.classes ?? [])
    .filter((row): row is { name: string; count: number } => {
      const item = row as { name?: unknown; count?: unknown };
      return typeof item.name === "string" && typeof item.count === "number";
    });

  const overviewStrip = (
    <OperatorOverviewStrip
      slug={slug}
      center={center}
      pipelineSlug={hydration?.pipelineSlug}
      ontologyClassPreview={classPreview}
    />
  );


  const rightRail = (
    <div>
      <SectionCard eyebrow="Execution Truth" noPad>
        <div style={{ padding: "12px 14px" }}>
          <div className="mono-muted" style={{ marginBottom: 12, fontSize: 10 }}>[DB AUTHORITATIVE]</div>
          <InlineStatus label="drift" value={center.projectReality?.hasDrift ? "present" : "clear"} />
          <InlineStatus label="stale sessions" value={center.projectReality?.staleRuntimeSessionCount ?? 0} />
          <InlineStatus label="integrity" value={center.auditedTruth?.integrity?.blocked ? "blocked" : "clear"} />
          <InlineStatus label="ready tasks" value={center.auditedTruth?.planner?.taskCounts?.ready ?? 0} />
        </div>
      </SectionCard>

      <SectionCard eyebrow="Repair Center" noPad>
        <div style={{ padding: "12px 14px" }}>
          {tasks.filter((t: any) => t.blockerCategory === "publish_failure").length > 0 ? (
            <div style={{ marginBottom: 16, padding: "12px", background: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--error)", borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: "var(--error)", display: "flex", alignItems: "center", gap: 8 }}>
                ⚠️ Branch Merge Conflict
              </div>
              <div className="mono-muted" style={{ marginTop: 6, fontSize: 12, color: "var(--error)" }}>
                A verified session workspace failed to merge into the default branch. 
                Please pull the branch locally, resolve the conflict, and merge manually.
              </div>
            </div>
          ) : null}

          {center.recommendedRepairTask ? (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, color: "var(--fg)" }}>{center.recommendedRepairTask.title}</div>
              <div className="mono-muted" style={{ marginTop: 4 }}>{center.recommendedRepairTask.reason}</div>
            </div>
          ) : null}
          <div style={{ display: "grid", gap: 8 }}>
            <ReconcileProjectButton slug={slug} />
          </div>
        </div>
      </SectionCard>

      <SectionCard eyebrow="Approvals" noPad>
        <ApprovalPanel approvals={center.pendingApprovals} slug={slug} />
      </SectionCard>

      <SectionCard eyebrow="Recent Audits" noPad>
        {center.recentAudits?.slice(0, 3).map((audit, index) => (
          <div key={`${audit.session?.id ?? "audit"}-${index}`} className="approval-row">
            <div>
              <div style={{ fontWeight: 600, color: "var(--fg)" }}>{audit.session?.id?.slice(-8)}</div>
              <div className="mono-muted">{audit.currentBlocker || "clear"}</div>
            </div>
            <StatusPill value={audit.session?.status ?? "unknown"} />
          </div>
        ))}
      </SectionCard>
    </div>
  );

  return (
    <ProjectShell slug={slug} title="Mission Control" section="overview" rightRail={rightRail}>
      {overviewStrip}
      
      <MetricStrip
        metrics={[
          { label: "Tasks", value: center.taskCounts.total, sub: `${center.taskCounts.byStatus.running ?? 0} running` },
          { label: "Approvals", value: center.pendingApprovals.length, sub: center.pendingApprovals.length ? "action required" : "clear" },
          { label: "Evidence", value: center.sourceSummary.count + (center.recentArtifacts?.length ?? 0), sub: "artifacts + sources" },
        ]}
      />
      
      <CommandShell>
        <div style={{ borderRight: "1px solid var(--border)" }}>
          <SectionCard eyebrow="Current Objective" title={center.project.name}>
            <div className="mono-muted" style={{ marginBottom: 8, fontSize: 10 }}>[REPO MIRROR: research_plan/current_plan.md]</div>
            {center.currentPlan.content ? (
              <MarkdownRenderer content={center.currentPlan.content} />
            ) : (
              <p className="mono-muted">No current plan file found.</p>
            )}
          </SectionCard>

          <SectionCard eyebrow="Task Board" noPad>
            <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)", fontSize: 10 }} className="mono-muted">
              [DB AUTHORITATIVE]
            </div>
            <TaskBoard tasks={tasks} slug={slug} />
          </SectionCard>
        </div>

        <div>
          <SectionCard eyebrow="Active Agents" noPad>
            {center.activeSessions.length ? (
              center.activeSessions.map((session: any, i: number) => (
                <AgentRunCard key={session._id ?? i} slug={slug} session={session} />
              ))
            ) : (
              <div className="empty-state">No active agent sessions.</div>
            )}
          </SectionCard>

          <SectionCard eyebrow="Evidence" noPad>
            <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)", fontSize: 10 }} className="mono-muted">
              [REPO MIRROR: artifacts/]
            </div>
            {center.recentArtifacts.length ? (
              center.recentArtifacts.slice(0, 10).map((artifact) => (
                <Link href={`/projects/${slug}/artifacts`} key={artifact.path} className="agent-run-card">
                  <div>
                    <div style={{ fontWeight: 600 }}>{artifact.name}</div>
                    <div className="mono-muted">{artifact.path}</div>
                  </div>
                  <StatusPill value={getArtifactTrustDisplay(artifact).label} />
                </Link>
              ))
            ) : (
              <div className="empty-state">No evidence produced yet.</div>
            )}
          </SectionCard>
        </div>
      </CommandShell>
    </ProjectShell>
  );
}
