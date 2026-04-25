import { MarkdownRenderer } from "@/components/markdown-renderer";
import { ProjectShell } from "@/components/project-shell";
import { StatusPill } from "@/components/status-pill";
import { fetchPlannerBoard, fetchPlannerThread } from "@/lib/api";

function TaskCard({ task }: { task: any }) {
  return (
    <div style={{
      borderBottom: "1px solid var(--border)",
      padding: "12px 14px",
      background: "var(--panel)",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 500, color: "var(--fg)", lineHeight: 1.3 }}>{task.title}</span>
        <StatusPill value={task.status} />
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>{task.agentRole}</span>
        {task.runner && <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>· {task.runner}</span>}
      </div>
      {task.description && (
        <MarkdownRenderer content={String(task.description)} />
      )}
      {task.repoPaths && task.repoPaths.length > 0 && (
        <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 4 }}>
          {task.repoPaths.map((p: string) => (
            <span key={p} style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              padding: "2px 6px",
              border: "1px solid var(--border)",
              color: "var(--muted)",
              background: "var(--panel-alt)",
            }}>
              {p}
            </span>
          ))}
        </div>
      )}
      {task.acceptanceCriteria && task.acceptanceCriteria.length > 0 && (
        <ul style={{ marginTop: 8, paddingLeft: 14, fontSize: 12, color: "var(--muted)" }}>
          {task.acceptanceCriteria.map((c: string, i: number) => (
            <li key={i} style={{ marginBottom: 2 }}>{c}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ApprovalRow({ approval }: { approval: any }) {
  return (
    <div style={{
      borderBottom: "1px solid var(--border)",
      padding: "10px 14px",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 8,
    }}>
      <div>
        <div style={{ fontSize: 12, fontWeight: 500, color: "var(--fg)" }}>
          {String(approval.approvalType ?? "approval")}
        </div>
        <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
          {String(approval.requestedByRole ?? "planner")}
          {approval.taskId ? ` · task ${String(approval.taskId).slice(-6)}` : ""}
        </div>
      </div>
      <StatusPill value={String(approval.status ?? "pending")} />
    </div>
  );
}

// ── Right rail: tasks + approvals ─────────────────────────────────────

function PlannerRightRail({ board }: { board: any }) {
  const byStatus: Record<string, any[]> = {};
  for (const task of board.tasks ?? []) {
    const s = task.status ?? "backlog";
    (byStatus[s] ??= []).push(task);
  }

  const ORDER = ["running", "awaiting_approval", "awaiting_input", "ready", "review", "blocked", "backlog", "done", "cancelled"];
  const grouped = ORDER.flatMap((s) => (byStatus[s] ?? []).map((t) => ({ ...t, _status: s })));
  const remaining = (board.tasks ?? []).filter((t: any) => !ORDER.includes(t.status ?? "backlog"));

  return (
    <div>
      {/* Approvals */}
      {board.approvals && board.approvals.length > 0 && (
        <div style={{ borderBottom: "1px solid var(--border)" }}>
          <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)" }}>
            <span className="rail-label">Approvals</span>
          </div>
          {board.approvals.map((a: any, i: number) => (
            <ApprovalRow key={i} approval={a} />
          ))}
        </div>
      )}

      {/* Task board */}
      <div>
        <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="rail-label">Tasks</span>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
            {(board.tasks ?? []).length}
          </span>
        </div>
        {[...grouped, ...remaining].length === 0 ? (
          <div style={{ padding: "24px 14px", textAlign: "center", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
            No tasks yet.
          </div>
        ) : (
          [...grouped, ...remaining].map((task) => (
            <TaskCard key={task._id} task={task} />
          ))
        )}
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────

export default async function PlannerPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [thread, board] = await Promise.all([
    fetchPlannerThread(slug),
    fetchPlannerBoard(slug),
  ]);
  const messages = (thread.messages as any[]).filter((m) => String(m.content ?? "").trim());

  return (
    <ProjectShell
      slug={slug}
      title="Planner"
      section="planner"
      rightRail={<PlannerRightRail board={board} />}
    >
      {/* Thread */}
      <div>
        {messages.length === 0 ? (
          <div style={{ padding: "40px 16px", textAlign: "center", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 12 }}>
            Planner thread is empty.
          </div>
        ) : (
          messages.map((msg: any, i: number) => {
            const role = String(msg.role ?? "assistant");
            const isUser = role === "user";
            const isSystem = role === "system";
            if (isSystem) return null;
            return (
              <div
                key={i}
                style={{
                  borderBottom: "1px solid var(--border)",
                  padding: "14px 16px",
                  background: isUser ? "var(--panel-alt)" : "var(--panel)",
                }}
              >
                <div style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10,
                  letterSpacing: "0.14em",
                  textTransform: "uppercase",
                  color: isUser ? "var(--fg)" : "var(--muted)",
                  marginBottom: 8,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}>
                  {role}
                  {msg.messageType && msg.messageType !== "chat" && (
                    <span style={{ opacity: 0.6 }}>· {msg.messageType}</span>
                  )}
                  {msg.createdAt && (
                    <span style={{ opacity: 0.5, marginLeft: "auto" }}>
                      {new Date(msg.createdAt).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false })}
                    </span>
                  )}
                </div>
                <MarkdownRenderer content={String(msg.content ?? "")} />
              </div>
            );
          })
        )}
      </div>
    </ProjectShell>
  );
}
