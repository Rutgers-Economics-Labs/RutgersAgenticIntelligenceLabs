import Link from "next/link";
import { fetchCommandCenter, fetchPlannerHome } from "@/lib/api";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { AgentRunCard, CommandShell, InlineStatus, MetricStrip, TaskBoard } from "@/components/command-center";
import { ApprovalPanel } from "@/components/approval-panel";
import { ReconcileProjectButton } from "@/components/reconcile-actions";
import { CreateOntologyFollowUpTaskButton } from "@/components/ontology-follow-up-actions";
import { getArtifactTrustDisplay, getWorkflowDisplaySections } from "@/lib/integrity-ui";

export default async function ProjectHomePage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [center, home] = await Promise.all([
    fetchCommandCenter(slug),
    fetchPlannerHome(slug),
  ]);
  const tasks = home.planner.tasks ?? [];
  const latestMessage = home.planner.messages.filter((m: any) => String(m.content ?? "").trim()).at(0);
  const workflowSections = center.integritySummary ? getWorkflowDisplaySections(center.integritySummary.agentWorkflow) : [];

  const rightRail = (
    <div>
      <SectionCard eyebrow="Next Action" noPad>
        <div style={{ padding: "12px 14px", fontWeight: 600 }}>{center.nextAction}</div>
      </SectionCard>
      <SectionCard eyebrow="Current Blocker" noPad>
        <div style={{ padding: "12px 14px" }}>
          <div style={{ fontWeight: 600, color: "var(--fg)" }}>{center.currentBlocker ?? "No current blocker detected."}</div>
          {center.auditedTruth?.path ? (
            <div className="mono-muted" style={{ marginTop: 6 }}>
              audited via {center.auditedTruth.path}
            </div>
          ) : null}
        </div>
      </SectionCard>
      <SectionCard eyebrow="Why Blocked" noPad>
        <div style={{ padding: "12px 14px" }}>
          <div style={{ fontWeight: 600, color: "var(--fg)" }}>
            {center.blockerSummary?.headline ?? "No active blocker detected."}
          </div>
          {center.blockerSummary?.reasons?.length ? (
            <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
              {center.blockerSummary.reasons.map((reason) => (
                <div key={reason} className="mono-muted">{reason}</div>
              ))}
            </div>
          ) : (
            <div className="mono-muted" style={{ marginTop: 8 }}>No blocker reasons recorded.</div>
          )}
          {center.blockerSummary?.repairs?.length ? (
            <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
              {center.blockerSummary.repairs.map((repair) => (
                <div key={repair} style={{ color: "var(--fg)" }}>{repair}</div>
              ))}
            </div>
          ) : null}
        </div>
      </SectionCard>
      <SectionCard eyebrow="Audited Truth" noPad>
        <InlineStatus label="session" value={center.auditedTruth?.session?.id ?? "none"} />
        <InlineStatus label="role" value={center.auditedTruth?.session?.role ?? "—"} />
        <InlineStatus label="review" value={center.auditedTruth?.session?.reviewStatus ?? "pending"} />
        <InlineStatus label="integrity" value={center.auditedTruth?.integrity?.blocked ? "blocked" : "clear"} />
        <InlineStatus label="blocked tasks" value={center.auditedTruth?.planner?.taskCounts?.blocked ?? 0} />
        <InlineStatus label="ready tasks" value={center.auditedTruth?.planner?.taskCounts?.ready ?? 0} />
      </SectionCard>
      <SectionCard eyebrow="Audit Timeline" noPad>
        {center.recentAudits?.length ? center.recentAudits.map((audit, index) => (
          <div key={`${audit.session?.id ?? "audit"}-${index}`} className="approval-row">
            <div>
              <div style={{ fontWeight: 600, color: "var(--fg)" }}>
                {audit.session?.id ?? "unknown session"}{audit.session?.role ? ` · ${audit.session.role}` : ""}
              </div>
              <div className="mono-muted">
                {audit.generatedAt ?? "unknown time"}{audit.path ? ` · ${audit.path}` : ""}
              </div>
              <div className="mono-muted">
                {audit.currentBlocker ?? audit.integrity?.reason ?? "No blocker recorded."}
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
              <StatusPill value={audit.session?.status ?? "unknown"} />
              <div className="mono-muted">
                {audit.integrity?.blocked ? "integrity blocked" : "integrity clear"}
              </div>
            </div>
          </div>
        )) : (
          <div className="empty-state">No recent audits yet.</div>
        )}
      </SectionCard>
      <SectionCard eyebrow="Reality Drift" noPad>
        <InlineStatus label="drift" value={center.projectReality?.hasDrift ? "present" : "clear"} />
        <InlineStatus label="task mismatches" value={center.projectReality?.taskSessionMismatchCount ?? 0} />
        <InlineStatus label="stale runtime" value={center.projectReality?.staleRuntimeSessionCount ?? 0} />
        <InlineStatus label="stale audits" value={center.projectReality?.staleAuditSessionCount ?? 0} />
        <InlineStatus label="session status drift" value={center.projectReality?.runningAgentStatusDriftCount ?? 0} />
        <InlineStatus label="session role drift" value={center.projectReality?.runningAgentRoleDriftCount ?? 0} />
        <InlineStatus label="session runner drift" value={center.projectReality?.runningAgentRunnerDriftCount ?? 0} />
        <InlineStatus label="duplicate tasks" value={center.projectReality?.duplicateTaskFileCount ?? 0} />
        <InlineStatus label="ontology drift" value={center.projectReality?.ontologyArtifactDriftCount ?? 0} />
        <InlineStatus label="artifact drift" value={center.projectReality?.artifactRegistryDriftCount ?? 0} />
        <InlineStatus label="secret policy drift" value={center.projectReality?.secretPolicyRoleDriftCount ?? 0} />
        <InlineStatus label="role config drift" value={center.projectReality?.roleConfigAliasDriftCount ?? 0} />
        {center.projectReality?.details?.duplicateTaskFiles?.length ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            {center.projectReality.details.duplicateTaskFiles.slice(0, 5).map((item) => (
              <div key={item} className="mono-muted">{item}</div>
            ))}
          </div>
        ) : null}
        {center.projectReality?.details?.taskSessionMismatchTaskIds?.length ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            {center.projectReality.details.taskSessionMismatchTaskIds.slice(0, 5).map((item) => (
              <div key={item} className="mono-muted">task mismatch: {item}</div>
            ))}
          </div>
        ) : null}
        {center.projectReality?.details?.staleRuntimeSessionIds?.length ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            {center.projectReality.details.staleRuntimeSessionIds.slice(0, 5).map((item) => (
              <div key={item} className="mono-muted">stale runtime: {item}</div>
            ))}
          </div>
        ) : null}
        {center.projectReality?.details?.runningAgentStatusDrift?.hasDrift ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            {center.projectReality.details.runningAgentStatusDrift.sessions.slice(0, 5).map((item) => (
              <div key={`${item.sessionId}-${item.canonicalStatus}`} className="mono-muted">
                session status drift: {item.sessionId} · {item.status} -&gt; {item.canonicalStatus}
              </div>
            ))}
          </div>
        ) : null}
        {center.projectReality?.details?.runningAgentRoleDrift?.hasDrift ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            {center.projectReality.details.runningAgentRoleDrift.sessions.slice(0, 5).map((item) => (
              <div key={`${item.sessionId}-${item.canonicalRole}`} className="mono-muted">
                session role drift: {item.sessionId} · {item.role} -&gt; {item.canonicalRole}
              </div>
            ))}
          </div>
        ) : null}
        {center.projectReality?.details?.runningAgentRunnerDrift?.hasDrift ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            {center.projectReality.details.runningAgentRunnerDrift.sessions.slice(0, 5).map((item) => (
              <div key={`${item.sessionId}-${item.canonicalRunner}`} className="mono-muted">
                session runner drift: {item.sessionId} · {item.runner} -&gt; {item.canonicalRunner}
              </div>
            ))}
          </div>
        ) : null}
        {center.projectReality?.details?.ontologyArtifactDrift?.hasDrift ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            <div className="mono-muted">
              ontology drift: {center.projectReality.details.ontologyArtifactDrift.reason ?? "active ontology pointer drift detected"}
            </div>
            {center.projectReality.details.ontologyArtifactDrift.activeDuckdbPath ? (
              <div className="mono-muted">active: {center.projectReality.details.ontologyArtifactDrift.activeDuckdbPath}</div>
            ) : null}
            {center.projectReality.details.ontologyArtifactDrift.expectedDuckdbPath ? (
              <div className="mono-muted">expected: {center.projectReality.details.ontologyArtifactDrift.expectedDuckdbPath}</div>
            ) : null}
          </div>
        ) : null}
        {center.projectReality?.details?.artifactRegistryDrift?.hasDrift ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            {center.projectReality.details.artifactRegistryDrift.untrackedArtifactPaths.slice(0, 5).map((item) => (
              <div key={`untracked-${item}`} className="mono-muted">untracked artifact: {item}</div>
            ))}
            {center.projectReality.details.artifactRegistryDrift.missingArtifactPaths.slice(0, 5).map((item) => (
              <div key={`missing-${item}`} className="mono-muted">missing artifact file: {item}</div>
            ))}
          </div>
        ) : null}
        {center.projectReality?.details?.secretPolicyRoleDrift?.hasDrift ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            {center.projectReality.details.secretPolicyRoleDrift.policies.slice(0, 5).map((item) => (
              <div key={item.policyId || `${item.agentRole}-${item.canonicalRole}`} className="mono-muted">
                secret policy role drift: {item.agentRole} -&gt; {item.canonicalRole}
              </div>
            ))}
          </div>
        ) : null}
        {center.projectReality?.details?.roleConfigAliasDrift?.hasDrift ? (
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 6 }}>
            {center.projectReality.details.roleConfigAliasDrift.configs.slice(0, 5).map((item) => (
              <div key={`${item.configPath}-${item.canonicalRole}`} className="mono-muted">
                role config drift: {item.configPath} · {item.role} -&gt; {item.canonicalRole}
              </div>
            ))}
          </div>
        ) : null}
      </SectionCard>
      <SectionCard eyebrow="Approvals" noPad>
        <ApprovalPanel approvals={center.pendingApprovals} slug={slug} />
      </SectionCard>
      <SectionCard eyebrow="Repair Actions">
        <ReconcileProjectButton slug={slug} />
      </SectionCard>
      <SectionCard eyebrow="Recommended Repair" noPad>
        {center.recommendedRepairTask ? (
          <div className="approval-row">
            <div>
              <div style={{ fontWeight: 600, color: "var(--fg)" }}>{center.recommendedRepairTask.title}</div>
              <div className="mono-muted">
                {center.recommendedRepairTask.reason ?? "Next repair task currently ready on the board"}
              </div>
              <div className="mono-muted">
                {center.recommendedRepairTask.agentRole || "unassigned role"}
                {center.recommendedRepairTask.auditor ? ` · ${center.recommendedRepairTask.auditor} auditor` : ""}
              </div>
            </div>
            <StatusPill value={center.recommendedRepairTask.status} />
          </div>
        ) : (
          <div className="empty-state">No repair recommendation yet.</div>
        )}
      </SectionCard>
      <SectionCard eyebrow="Repair Queue" noPad>
        <InlineStatus label="repair tasks" value={center.repairQueue?.count ?? 0} />
        <InlineStatus label="ready" value={center.repairQueue?.readyCount ?? 0} />
        <InlineStatus label="running" value={center.repairQueue?.runningCount ?? 0} />
        {center.repairQueue?.tasks?.length ? center.repairQueue.tasks.map((task) => (
          <div key={task.id || task.title} className="approval-row">
            <div>
              <div style={{ fontWeight: 600, color: "var(--fg)" }}>{task.title}</div>
              <div className="mono-muted">{task.agentRole || "unassigned role"}</div>
            </div>
            <StatusPill value={task.status} />
          </div>
        )) : (
          <div className="empty-state">No repair tasks on the board.</div>
        )}
      </SectionCard>
      <SectionCard eyebrow="Source Health" noPad>
        <InlineStatus label="sources" value={center.sourceSummary.count} />
        {Object.entries(center.sourceSummary.statusCounts ?? {}).map(([key, value]) => (
          <InlineStatus key={key} label={key.replaceAll("_", " ")} value={value} />
        ))}
        {Object.entries(center.integritySummary?.sourceFreshnessCounts ?? {}).map(([key, value]) => (
          <InlineStatus key={`freshness-${key}`} label={key.replaceAll("_", " ")} value={value} />
        ))}
        {Object.entries(center.integritySummary?.sourceAdmissibilityCounts ?? {}).map(([key, value]) => (
          <InlineStatus key={`admissibility-${key}`} label={`${key.replaceAll("_", " ")} admissibility`} value={value} />
        ))}
      </SectionCard>
      <SectionCard eyebrow="Workflow Gates" noPad>
        {workflowSections.length ? workflowSections.map((section) => (
          <div key={section.key} className="approval-row">
            <div>
              <div style={{ fontWeight: 600, color: "var(--fg)" }}>{section.label}</div>
              <div className="mono-muted">{section.blockerCount ? `${section.blockerCount} blockers` : "ready"}</div>
            </div>
            <StatusPill value={section.status} />
          </div>
        )) : (
          <div className="empty-state">No integrity workflow summary yet.</div>
        )}
      </SectionCard>
      <SectionCard eyebrow="Ontology Coverage" noPad>
        {Object.entries(center.ontologyFollowUps?.classificationCounts ?? {}).map(([key, value]) => (
          <InlineStatus key={key} label={key.replaceAll("_", " ")} value={value} />
        ))}
        {center.ontologyFollowUps?.questions?.length ? (
          center.ontologyFollowUps.questions.slice(0, 5).map((question) => (
            <div key={question.title} className="approval-row">
              <div>
                <div style={{ fontWeight: 600, color: "var(--fg)" }}>{question.title}</div>
                <div className="mono-muted">
                  {question.notes?.[0] ?? "No ontology coverage note recorded."}
                </div>
                {question.expectedTaskTitle ? (
                  <div className="mono-muted">
                    {question.taskPresent ? `task: ${question.expectedTaskTitle}` : `missing task: ${question.expectedTaskTitle}`}
                  </div>
                ) : null}
                {question.expectedTaskTitle && !question.taskPresent ? (
                  <div style={{ marginTop: 8 }}>
                    <CreateOntologyFollowUpTaskButton
                      slug={slug}
                      title={question.title}
                      classification={question.classification ?? ""}
                    />
                  </div>
                ) : null}
              </div>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                <StatusPill value={question.classification ?? "unknown"} />
                {question.expectedTaskTitle ? (
                  <StatusPill value={question.taskStatus ?? (question.taskPresent ? "linked" : "missing_task")} />
                ) : null}
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state">No ontology follow-up classifications yet.</div>
        )}
      </SectionCard>
      <SectionCard eyebrow="Auditors" noPad>
        {Object.entries(center.auditors ?? {}).length ? Object.entries(center.auditors ?? {}).map(([key, value]) => (
          <div key={key} className="approval-row">
            <div>
              <div style={{ fontWeight: 600, color: "var(--fg)", textTransform: "capitalize" }}>{key}</div>
              <div className="mono-muted">
                {value.blockers?.length ? value.blockers[0] : value.state ? `state: ${value.state}` : "ready"}
              </div>
            </div>
            <StatusPill value={value.status} />
          </div>
        )) : (
          <div className="empty-state">No auditor summary yet.</div>
        )}
      </SectionCard>
      <SectionCard eyebrow="Repo Health" noPad>
        <InlineStatus label="local repo" value={center.repoHealth.hasLocalRepo ? "yes" : "no"} />
        <InlineStatus label="rail.yaml" value={center.repoHealth.hasRailYaml ? "present" : "missing"} />
        <InlineStatus label="research plan" value={center.repoHealth.hasResearchPlan ? "present" : "missing"} />
      </SectionCard>
    </div>
  );

  return (
    <ProjectShell slug={slug} title="Mission Control" section="overview" rightRail={rightRail}>
      <MetricStrip
        metrics={[
          { label: "Tasks", value: center.taskCounts.total, sub: `${center.taskCounts.byStatus.running ?? 0} running` },
          { label: "Approvals", value: center.pendingApprovals.length, sub: center.pendingApprovals.length ? "action required" : "clear" },
          { label: "Active Runs", value: center.activeSessions.length, sub: center.activeSessions.length ? "agents live" : "idle" },
          { label: "Sources", value: center.sourceSummary.count, sub: "inventory rows" },
          { label: "Skills", value: center.skillSummary.count, sub: "repo playbooks" },
        ]}
      />
      <CommandShell>
        <div style={{ borderRight: "1px solid var(--border)" }}>
          <SectionCard eyebrow="Current Objective" title={center.project.name}>
            {center.currentPlan.content ? (
              <MarkdownRenderer content={center.currentPlan.content} />
            ) : (
              <p className="mono-muted">No current plan file found.</p>
            )}
          </SectionCard>

          <SectionCard eyebrow="Task Board" noPad>
            <TaskBoard tasks={tasks} slug={slug} />
          </SectionCard>

          <SectionCard eyebrow="Latest Planner Message">
            {latestMessage ? (
              <MarkdownRenderer content={String(latestMessage.content ?? "")} />
            ) : (
              <p className="mono-muted">No planner messages yet.</p>
            )}
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

          <SectionCard eyebrow="Recent Artifacts" noPad>
            {center.recentArtifacts.length ? (
              center.recentArtifacts.map((artifact) => (
                <Link href={`/projects/${slug}/artifacts`} key={artifact.path} className="agent-run-card">
                  <div>
                    <div style={{ fontWeight: 600 }}>{artifact.name}</div>
                    <div className="mono-muted">{artifact.path}</div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                    <StatusPill value={artifact.type} />
                    <StatusPill value={getArtifactTrustDisplay(artifact).label} />
                  </div>
                </Link>
              ))
            ) : (
              <div className="empty-state">No artifacts yet.</div>
            )}
          </SectionCard>
        </div>
      </CommandShell>
    </ProjectShell>
  );
}
