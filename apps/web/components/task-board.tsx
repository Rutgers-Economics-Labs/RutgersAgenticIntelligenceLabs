"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { launchTask } from "@/lib/api";
import { StatusPill } from "@/components/status-pill";
import { ApprovalPanel } from "@/components/approval-panel";

// ── Runner options ─────────────────────────────────────────────────────

const RUNNERS = [
  {
    id: "gemini_cli",
    label: "RAIL Gemini",
    sub: "Gemini 3 Flash · web search · file I/O",
    icon: "G",
    color: "#4285f4",
  },
  {
    id: "claude_code",
    label: "Claude Code",
    sub: "Sonnet 4.6 · local CLI · full repo access",
    icon: "C",
    color: "#d97706",
  },
  {
    id: "cursor_cli",
    label: "Cursor Agent",
    sub: "Cursor CLI · local agent mode",
    icon: "A",
    color: "#0ea5e9",
  },
  {
    id: "jules",
    label: "Jules",
    sub: "Google Jules · cloud · GitHub integration",
    icon: "J",
    color: "#16a34a",
  },
  {
    id: "codex_cli",
    label: "Codex CLI",
    sub: "OpenAI Codex · local CLI",
    icon: "X",
    color: "#8b5cf6",
  },
  {
    id: "copilot_cli",
    label: "Copilot CLI",
    sub: "GitHub Copilot · local CLI",
    icon: "GH",
    color: "#111827",
  },
];

// ── Task launch modal ──────────────────────────────────────────────────

export function TaskModalExport({
  slug, task, onClose,
}: { slug: string; task: any; onClose: () => void }) {
  return <TaskModal slug={slug} task={task} onClose={onClose} />;
}

function TaskModal({
  slug,
  task,
  onClose,
}: {
  slug: string;
  task: any;
  onClose: () => void;
}) {
  const router = useRouter();
  const [runner, setRunner] = useState("gemini_cli");
  const [additionalInstructions, setAdditionalInstructions] = useState("");
  const [verifyAfter, setVerifyAfter] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setLaunching(true);
    setError(null);
    try {
      const verifyNote = verifyAfter
        ? "\n\nAfter completing the main work, run a self-verification pass: check for hardcoded values that should be config-driven, verify all pipeline connections reference real sources and transforms (not placeholder names), and confirm each acceptance criterion is met with evidence."
        : "";
      const instructions = additionalInstructions.trim()
        ? `\n\nAdditional instructions:\n${additionalInstructions.trim()}`
        : "";
      const taskWithExtras = { ...task, description: (task.description ?? task.title) + instructions + verifyNote };
      const result = await launchTask(slug, taskWithExtras, runner);
      const sessionId = result.convex_session_id ?? result.session_id;
      onClose();
      if (sessionId) {
        router.push(`/projects/${slug}/runs/${encodeURIComponent(sessionId)}`);
      } else {
        router.push(`/projects/${slug}/runs`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to launch");
      setLaunching(false);
    }
  }

  const criteria: string[] = (task.acceptanceCriteria ?? []).map((c: unknown) =>
    typeof c === "string" ? c : JSON.stringify(c)
  );

  return (
    /* Backdrop */
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 100,
        background: "rgba(0,0,0,0.45)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      {/* Panel */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 480, maxWidth: "95vw", maxHeight: "90vh",
          background: "var(--panel)",
          border: "1px solid var(--border-strong)",
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div style={{
          padding: "14px 16px 12px",
          borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10,
        }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)", lineHeight: 1.3, marginBottom: 4 }}>
              {task.title}
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <StatusPill value={task.status} />
              {task.agentRole && (
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
                  {task.agentRole}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 18, lineHeight: 1, flexShrink: 0, padding: 2 }}
          >×</button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "14px 16px" }}>

          {/* Description */}
          {task.description && (
            <p style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6, marginBottom: 12, marginTop: 0 }}>
              {task.description}
            </p>
          )}

          {/* Acceptance criteria */}
          {criteria.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 6 }}>
                Acceptance criteria
              </div>
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: "var(--fg)", lineHeight: 1.7 }}>
                {criteria.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          )}

          {/* Additional instructions */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 6 }}>
              Additional instructions
            </div>
            <textarea
              value={additionalInstructions}
              onChange={(e) => setAdditionalInstructions(e.target.value)}
              placeholder="Extra context or constraints for the agent…"
              rows={3}
              style={{
                width: "100%", boxSizing: "border-box",
                background: "var(--bg)", border: "1px solid var(--border)",
                color: "var(--fg)", fontFamily: "JetBrains Mono, monospace", fontSize: 11,
                padding: "8px 10px", resize: "vertical", outline: "none",
                lineHeight: 1.6,
              }}
            />
          </div>

          {/* Verification checkbox */}
          <div style={{ marginBottom: 16 }}>
            <label style={{
              display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer",
              padding: "10px 12px",
              border: `1px solid ${verifyAfter ? "var(--s-review)" : "var(--border)"}`,
              background: verifyAfter ? "var(--s-review)11" : "var(--bg)",
              transition: "border-color 100ms, background 100ms",
            }}>
              <input
                type="checkbox"
                checked={verifyAfter}
                onChange={(e) => setVerifyAfter(e.target.checked)}
                style={{ marginTop: 2, accentColor: "var(--s-review)", flexShrink: 0 }}
              />
              <div>
                <div style={{ fontSize: 13, fontWeight: verifyAfter ? 600 : 400, color: "var(--fg)" }}>
                  Self-verify after completion
                </div>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                  Agent checks for hardcoded values, bad pipeline connections, and unmet criteria
                </div>
              </div>
            </label>
          </div>

          {/* Runner picker */}
          <div style={{ marginBottom: 6 }}>
            <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 8 }}>
              Execution agent
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {RUNNERS.map((r) => {
                const selected = runner === r.id;
                return (
                  <button
                    key={r.id}
                    onClick={() => setRunner(r.id)}
                    style={{
                      display: "flex", alignItems: "center", gap: 12,
                      padding: "10px 12px",
                      border: `1px solid ${selected ? r.color : "var(--border)"}`,
                      background: selected ? `${r.color}14` : "var(--bg)",
                      cursor: "pointer",
                      textAlign: "left", width: "100%",
                      transition: "border-color 100ms, background 100ms",
                    }}
                  >
                    <span style={{
                      width: 28, height: 28, borderRadius: 4, flexShrink: 0,
                      background: selected ? r.color : "var(--border)",
                      color: selected ? "#fff" : "var(--muted)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontFamily: "JetBrains Mono, monospace", fontSize: 12, fontWeight: 700,
                      transition: "background 100ms, color 100ms",
                    }}>{r.icon}</span>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: selected ? 600 : 400, color: "var(--fg)" }}>
                        {r.label}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>
                        {r.sub}
                      </div>
                    </div>
                    {selected && (
                      <span style={{ marginLeft: "auto", width: 8, height: 8, borderRadius: "50%", background: r.color, flexShrink: 0 }} />
                    )}
                  </button>
                );
              })}
            </div>

            {/* Custom runner */}
            <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", flexShrink: 0 }}>
                or custom:
              </span>
              <input
                value={RUNNERS.some(r => r.id === runner) ? "" : runner}
                onChange={(e) => setRunner(e.target.value.trim().toLowerCase().replace(/\s+/g, "_") || "gemini_cli")}
                placeholder="e.g. open_code_cli"
                style={{
                  flex: 1, background: "var(--bg)", border: "1px solid var(--border)",
                  color: "var(--fg)", fontFamily: "JetBrains Mono, monospace", fontSize: 11,
                  padding: "5px 8px", outline: "none",
                }}
              />
            </div>
            {!RUNNERS.some(r => r.id === runner) && runner && (
              <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", marginTop: 4 }}>
                Using custom runner: <strong style={{ color: "var(--fg)" }}>{runner}</strong>
              </div>
            )}
          </div>
          {error && (
            <div style={{ marginTop: 10, padding: "8px 10px", background: "var(--s-failed)22", border: "1px solid var(--s-failed)", fontSize: 12, color: "var(--s-failed)", fontFamily: "JetBrains Mono, monospace" }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          borderTop: "1px solid var(--border)",
          padding: "12px 16px",
          display: "flex", justifyContent: "flex-end", gap: 8,
        }}>
          <button
            onClick={onClose}
            disabled={launching}
            style={{
              padding: "7px 14px",
              background: "none", border: "1px solid var(--border)",
              fontFamily: "JetBrains Mono, monospace", fontSize: 11,
              letterSpacing: "0.08em", textTransform: "uppercase",
              color: "var(--muted)", cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleRun}
            disabled={launching}
            style={{
              padding: "7px 18px",
              background: launching ? "var(--panel-alt)" : "var(--fg)",
              color: launching ? "var(--muted)" : "var(--bg)",
              border: "1px solid var(--border-strong)",
              fontFamily: "JetBrains Mono, monospace", fontSize: 11,
              letterSpacing: "0.08em", textTransform: "uppercase",
              cursor: launching ? "not-allowed" : "pointer",
            }}
          >
            {launching ? "Launching…" : "Run task"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Clickable task card ────────────────────────────────────────────────

function TaskCard({ task, onClick }: { task: any; onClick: () => void }) {
  const canRun = ["ready", "backlog", "blocked"].includes(task.status ?? "");

  return (
    <div
      onClick={onClick}
      style={{
        borderBottom: "1px solid var(--border)",
        padding: "12px 14px",
        background: "var(--panel)",
        cursor: "pointer",
        transition: "background 100ms",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-alt)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "var(--panel)")}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 13, fontWeight: 500, color: "var(--fg)", lineHeight: 1.3 }}>{task.title}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          {canRun && (
            <span style={{
              fontFamily: "JetBrains Mono, monospace", fontSize: 9,
              letterSpacing: "0.1em", textTransform: "uppercase",
              padding: "1px 5px", border: "1px solid var(--border)",
              color: "var(--muted)",
            }}>run</span>
          )}
          <StatusPill value={task.status} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
          {task.agentRole ?? "—"}
        </span>
        {task.runner && (
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
            · {task.runner}
          </span>
        )}
      </div>
      {task.description && (
        <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--muted)", lineHeight: 1.5, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {task.description}
        </p>
      )}
    </div>
  );
}

// ── Approval row ───────────────────────────────────────────────────────

function ApprovalRow({ approval, slug }: { approval: any; slug: string }) {
  const isAuto = approval.resolutionNote?.includes("Auto-approved");
  const isGranted = approval.status === "granted";

  return (
    <div style={{
      borderBottom: "1px solid var(--border)",
      padding: "10px 14px",
      background: isAuto && isGranted ? "var(--s-running)05" : "none",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: "var(--fg)" }}>
            {String(approval.approvalType ?? "approval")}
          </div>
          {isAuto && isGranted && (
            <span style={{
              fontFamily: "JetBrains Mono, monospace", fontSize: 8,
              background: "var(--s-running)", color: "white",
              padding: "1px 4px", borderRadius: 2, letterSpacing: "0.05em"
            }}>AUTO</span>
          )}
        </div>
        <StatusPill value={String(approval.status ?? "pending")} />
      </div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", marginBottom: (approval.status === "pending" || approval.resolutionNote) ? 8 : 0 }}>
        {String(approval.requestedByRole ?? "planner")}
        {approval.taskId ? ` · task ${String(approval.taskId).slice(-6)}` : ""}
      </div>
      {approval.status === "pending" && (
        <ApprovalPanel slug={slug} approvals={[approval]} />
      )}
      {isGranted && approval.resolutionNote && (
        <div style={{
          fontSize: 11, fontStyle: "italic", color: "var(--muted)",
          padding: "6px 8px", background: "var(--panel-alt)", borderLeft: "2px solid var(--border)"
        }}>
          {approval.resolutionNote}
        </div>
      )}
    </div>
  );
}

// ── Main export ────────────────────────────────────────────────────────

export function TaskBoard({ board, slug }: { board: any; slug: string }) {
  const [selected, setSelected] = useState<any | null>(null);

  const ORDER = ["running", "awaiting_approval", "awaiting_input", "ready", "review", "blocked", "backlog", "done", "cancelled"];
  const byStatus: Record<string, any[]> = {};
  for (const task of board.tasks ?? []) {
    const s = task.status ?? "backlog";
    (byStatus[s] ??= []).push(task);
  }
  const sorted = ORDER.flatMap((s) => byStatus[s] ?? []);
  const rest = (board.tasks ?? []).filter((t: any) => !ORDER.includes(t.status ?? "backlog"));
  const allTasks = [...sorted, ...rest];

  return (
    <>
      {/* Approvals */}
      {board.approvals && board.approvals.length > 0 && (
        <div style={{ borderBottom: "1px solid var(--border)" }}>
          <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)" }}>
            <span className="rail-label">Approvals</span>
          </div>
          {board.approvals.map((a: any, i: number) => (
            <ApprovalRow key={i} approval={a} slug={slug} />
          ))}
        </div>
      )}

      {/* Task list */}
      <div>
        <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="rail-label">Tasks</span>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
            {allTasks.length}
          </span>
        </div>
        {allTasks.length === 0 ? (
          <div style={{ padding: "24px 14px", textAlign: "center", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
            No tasks yet.
          </div>
        ) : (
          allTasks.map((task) => (
            <TaskCard key={task._id} task={task} onClick={() => setSelected(task)} />
          ))
        )}
      </div>

      {/* Launch modal */}
      {selected && (
        <TaskModal
          slug={slug}
          task={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
