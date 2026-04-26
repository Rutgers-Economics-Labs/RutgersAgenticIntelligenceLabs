import Link from "next/link";
import { fetchCommandCenter, fetchPlannerHome } from "@/lib/api";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { AgentRunCard, CommandShell, InlineStatus, MetricStrip, TaskBoard } from "@/components/command-center";
import { ApprovalPanel } from "@/components/approval-panel";

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

  const rightRail = (
    <div>
      <SectionCard eyebrow="Next Action" noPad>
        <div style={{ padding: "12px 14px", fontWeight: 600 }}>{center.nextAction}</div>
      </SectionCard>
      <SectionCard eyebrow="Approvals" noPad>
        <ApprovalPanel approvals={center.pendingApprovals} slug={slug} />
      </SectionCard>
      <SectionCard eyebrow="Source Health" noPad>
        <InlineStatus label="sources" value={center.sourceSummary.count} />
        {Object.entries(center.sourceSummary.statusCounts ?? {}).map(([key, value]) => (
          <InlineStatus key={key} label={key.replaceAll("_", " ")} value={value} />
        ))}
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
            <TaskBoard tasks={tasks} />
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
                  <StatusPill value={artifact.type} />
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
