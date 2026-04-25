import Link from "next/link";
import { ReactNode } from "react";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { StatusPill } from "@/components/status-pill";
import { ProjectArtifact, ProjectSkill, ProjectSource, RunnerSession } from "@/lib/types";

export function CommandShell({ children }: { children: ReactNode }) {
  return <div className="command-grid">{children}</div>;
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="empty-state">
      <div style={{ fontWeight: 600, color: "var(--fg)", marginBottom: 4 }}>{title}</div>
      {detail && <div style={{ color: "var(--muted)" }}>{detail}</div>}
    </div>
  );
}

export function InlineStatus({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="inline-status">
      <span>{label}</span>
      <strong>{value ?? "—"}</strong>
    </div>
  );
}

export function MetricStrip({ metrics }: { metrics: Array<{ label: string; value: string | number; sub?: string }> }) {
  return (
    <div className="metric-strip">
      {metrics.map((item) => (
        <div className="metric-cell" key={item.label}>
          <div className="rail-label">{item.label}</div>
          <div className="metric-value">{item.value}</div>
          {item.sub && <div className="metric-sub">{item.sub}</div>}
        </div>
      ))}
    </div>
  );
}

export function AgentRunCard({ slug, session }: { slug: string; session: RunnerSession }) {
  const id = session._id ?? session.id;
  const href = id ? `/projects/${slug}/runs/${id}` : `/projects/${slug}/runs`;
  return (
    <Link href={href as any} className="agent-run-card">
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg)" }}>{session.title ?? session.role ?? "Agent run"}</div>
        <div className="mono-muted">
          {session.role ?? "agent"}{session.runner ? ` · ${session.runner}` : ""}
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
        <StatusPill value={session.status} />
        {session.review?.reviewStatus && <StatusPill value={session.review.reviewStatus} />}
      </div>
    </Link>
  );
}

export function ApprovalPanel({ approvals }: { approvals: Array<Record<string, unknown>> }) {
  if (!approvals.length) return <EmptyState title="No approvals pending" detail="Write-capable agent work will appear here before execution." />;
  return (
    <div>
      {approvals.map((approval, index) => (
        <div className="approval-row" key={String(approval._id ?? index)}>
          <div>
            <div style={{ fontWeight: 600, color: "var(--fg)" }}>{String(approval.approvalType ?? "approval")}</div>
            <div className="mono-muted">
              {String(approval.requestedByRole ?? "planner")}
              {approval.taskId ? ` · task ${String(approval.taskId).slice(-8)}` : ""}
            </div>
          </div>
          <StatusPill value={String(approval.status ?? "pending")} />
        </div>
      ))}
    </div>
  );
}

export function TaskBoard({ tasks }: { tasks: Array<any> }) {
  const statuses = ["running", "awaiting_approval", "ready", "review", "blocked", "backlog", "done"];
  if (!tasks.length) return <EmptyState title="No tasks yet" detail="Launch a research workflow to seed the first execution plan." />;
  return (
    <div className="task-board">
      {statuses.map((status) => {
        const rows = tasks.filter((task) => (task.status ?? "backlog") === status);
        return (
          <div className="task-column" key={status}>
            <div className="task-column-header">
              <span>{status.replaceAll("_", " ")}</span>
              <strong>{rows.length}</strong>
            </div>
            {rows.length === 0 ? (
              <div className="task-empty">Empty</div>
            ) : rows.map((task) => (
              <div className="task-mini-card" key={task._id}>
                <div style={{ fontWeight: 600, color: "var(--fg)" }}>{task.title}</div>
                <div className="mono-muted">{task.agentRole ?? "planner"}{task.runner ? ` · ${task.runner}` : ""}</div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

export function SkillList({ skills }: { skills: ProjectSkill[] }) {
  if (!skills.length) return <EmptyState title="No skills found" detail="Repo-local skill files under skills/ will appear here." />;
  return (
    <div className="split-list">
      {skills.map((skill) => (
        <div className="split-row" key={skill.path}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--fg)" }}>{skill.name}</div>
            <div className="mono-muted">{skill.path}</div>
            {skill.summary && <p style={{ margin: "8px 0 0", color: "var(--muted)" }}>{skill.summary}</p>}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
              {skill.usedBy.map((role) => <StatusPill key={role} value={role} />)}
            </div>
          </div>
          <pre className="content-preview">{skill.content}</pre>
        </div>
      ))}
    </div>
  );
}

export function SourceInventoryTable({ sources }: { sources: ProjectSource[] }) {
  if (!sources.length) return <EmptyState title="No source inventory" detail="Source candidates and ontology source configs will appear here." />;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="data-table">
        <thead>
          <tr>
            {["Name", "Status", "Publisher", "Access", "Coverage", "Fields", "Files"].map((h) => <th key={h}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.id}>
              <td>
                <strong>{source.name}</strong>
                {source.qualityNotes && <div className="mono-muted">{source.qualityNotes.slice(0, 120)}</div>}
              </td>
              <td><StatusPill value={source.status} /></td>
              <td>{source.publisher}</td>
              <td>{source.accessMethod}</td>
              <td>{[source.geography, source.timeCoverage, source.updateFrequency].filter(Boolean).join(" · ") || "—"}</td>
              <td className="mono-muted">{Array.isArray(source.keyFields) ? source.keyFields.slice(0, 4).join(", ") : String(source.keyFields ?? "—")}</td>
              <td className="mono-muted">{source.linkedFiles.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ArtifactPreview({ artifact }: { artifact: ProjectArtifact }) {
  const preview = artifact.preview;
  return (
    <div className="artifact-card">
      <div className="artifact-header">
        <div>
          <div style={{ fontWeight: 700, color: "var(--fg)" }}>{artifact.name}</div>
          <div className="mono-muted">{artifact.path}</div>
        </div>
        <StatusPill value={artifact.type} />
      </div>
      {preview?.kind === "markdown" && preview.content ? (
        <div className="artifact-preview"><MarkdownRenderer content={preview.content} /></div>
      ) : preview?.kind === "table" && preview.rows ? (
        <div className="table-preview">
          <table className="data-table">
            <tbody>
              {preview.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}
            </tbody>
          </table>
        </div>
      ) : preview?.kind === "structured" || preview?.kind === "html" ? (
        <pre className="content-preview">{preview.content}</pre>
      ) : preview?.kind === "image" && preview.imagePath ? (
        <img src={preview.imagePath} alt={artifact.name} className="artifact-image" />
      ) : (
        <div className="mono-muted">Metadata preview only · {(artifact.sizeBytes / 1024).toFixed(1)} KB</div>
      )}
    </div>
  );
}
