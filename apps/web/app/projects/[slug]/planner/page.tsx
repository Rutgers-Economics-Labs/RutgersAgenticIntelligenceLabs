import { MarkdownRenderer } from "@/components/markdown-renderer";
import { ProjectShell } from "@/components/project-shell";
import { TaskBoard } from "@/components/task-board";
import { fetchPlannerBoard, fetchPlannerThread } from "@/lib/api";

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
      rightRail={<TaskBoard board={board} slug={slug} />}
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
