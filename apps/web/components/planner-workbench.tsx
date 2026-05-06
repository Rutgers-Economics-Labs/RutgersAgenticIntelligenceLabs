"use client";

import { useEffect, useMemo, useState } from "react";
import { ApprovalPanel } from "@/components/approval-panel";
import { ProjectShell } from "@/components/project-shell";
import { StatusPill } from "@/components/status-pill";
import { TaskBoard } from "@/components/task-board";
import {
  createPlannerTask,
  fetchAutopilotStatus,
  fetchPlannerBoard,
  toggleProjectAutopilot,
  updatePlannerTask,
} from "@/lib/api";
import { AutopilotStatus, PlannerApproval, PlannerBoard, PlannerTask, PlannerTaskDraft } from "@/lib/types";

const API_ROOT = process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const ROLE_OPTIONS = ["planner", "research", "data", "coding", "artifact", "health"];

const QUICK_PROMPTS = [
  "Create a phase-2 validation wave for this project, with concrete tasks, dependencies, and acceptance criteria.",
  "Look at the current planner board and tell me what work is duplicated, stale, or blocked.",
  "Propose the next best external sources to bring into this project and convert them into executable planner tasks.",
  "Review the current findings and suggest three stronger research questions that deserve new work.",
];

const TASK_PRESETS: Array<{
  label: string;
  draft: PlannerTaskDraft;
}> = [
  {
    label: "Null-rate profiling",
    draft: {
      title: "Profile identifier quality and placeholders",
      description:
        "Quantify null rates, placeholder values, and joinability proxies across the most important project records so downstream validation can target the strongest subsets first.",
      status: "ready",
      agentRole: "coding",
      repoPaths: ["scripts", "research", "artifacts"],
      acceptanceCriteria: [
        "A repo-backed profiling artifact identifies the highest-quality joinable subsets",
        "The artifact distinguishes structural nulls from optional missing fields",
        "The findings recommend the best next validation targets",
      ],
      approvalState: "granted",
      runner: "codex_cli",
    },
  },
  {
    label: "Source expansion wave",
    draft: {
      title: "Map and operationalize next external validation sources",
      description:
        "Identify the next high-value external sources for validation and either operationalize them or document the exact blockers, keys, and join strategy required.",
      status: "ready",
      agentRole: "research",
      repoPaths: ["research", "artifacts", "topics"],
      acceptanceCriteria: [
        "A prioritized source memo maps research questions to external datasets",
        "Immediately runnable sources are clearly separated from blocked ones",
        "The memo names identifiers and likely match-quality caveats",
      ],
      approvalState: "granted",
      runner: "codex_cli",
    },
  },
  {
    label: "Synthesis refresh",
    draft: {
      title: "Refresh synthesis and claim boundaries",
      description:
        "Update the project synthesis so validated subsets, unresolved gaps, and safe downstream reporting claims are clearly separated.",
      status: "backlog",
      agentRole: "coding",
      repoPaths: ["research", "artifacts", "topics"],
      acceptanceCriteria: [
        "A repo-backed memo distinguishes validated subsets from descriptive-only findings",
        "Claim boundaries are explicit and publication-safe",
        "The output recommends the strongest next narrative angles",
      ],
      approvalState: "granted",
      runner: "codex_cli",
    },
  },
];

function blankDraft(): PlannerTaskDraft {
  return {
    title: "",
    description: "",
    status: "backlog",
    agentRole: "research",
    repoPaths: [],
    acceptanceCriteria: [],
    dependsOnTaskIds: [],
    approvalState: "granted",
    runner: "codex_cli",
  };
}

function deriveTitle(prompt: string) {
  const singleLine = prompt.replace(/\s+/g, " ").trim();
  if (!singleLine) return "";
  return singleLine.length > 72 ? `${singleLine.slice(0, 69)}...` : singleLine;
}

function normalizeTitle(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function formatTaskCounts(tasks: PlannerTask[]) {
  const counts = tasks.reduce<Record<string, number>>((acc, task) => {
    const key = task.status || "unknown";
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  return [
    { label: "Running", value: counts.running ?? 0 },
    { label: "Ready", value: counts.ready ?? 0 },
    { label: "Review", value: counts.review ?? 0 },
    { label: "Blocked", value: counts.blocked ?? 0 },
    { label: "Done", value: counts.done ?? 0 },
  ];
}

function computeDiagnostics(board: PlannerBoard | null) {
  if (!board) return [];
  const diagnostics: Array<{ label: string; severity: "info" | "warn"; detail: string }> = [];

  const titleMap = new Map<string, PlannerTask[]>();
  for (const task of board.tasks) {
    const key = normalizeTitle(task.title);
    if (!key) continue;
    const existing = titleMap.get(key) ?? [];
    existing.push(task);
    titleMap.set(key, existing);
  }
  for (const [, tasks] of titleMap) {
    if (tasks.length > 1) {
      diagnostics.push({
        label: "Duplicate task title",
        severity: "warn",
        detail: `${tasks[0].title} appears ${tasks.length} times on the board.`,
      });
    }
  }

  for (const task of board.tasks) {
    if (task.status === "awaiting_approval" && task.approvalState === "granted") {
      diagnostics.push({
        label: "Approval state mismatch",
        severity: "warn",
        detail: `${task.title} is still awaiting approval even though approvalState is granted.`,
      });
    }
  }

  const taskIds = new Set(board.tasks.map((task) => task._id));
  for (const approval of board.approvals ?? []) {
    if (approval.taskId && !taskIds.has(String(approval.taskId))) {
      diagnostics.push({
        label: "Orphan approval",
        severity: "info",
        detail: `Approval ${approval._id ?? approval.taskId} points at a task that is not on the current board snapshot.`,
      });
    }
  }

  if (diagnostics.length === 0) {
    diagnostics.push({
      label: "Board hygiene",
      severity: "info",
      detail: "No duplicate titles or approval-state mismatches were detected in the current board snapshot.",
    });
  }

  return diagnostics;
}

function TaskDraftPanel({
  draft,
  setDraft,
  onCreate,
  creating,
  lastPrompt,
}: {
  draft: PlannerTaskDraft;
  setDraft: (next: PlannerTaskDraft) => void;
  onCreate: (startAutopilot: boolean) => Promise<void>;
  creating: boolean;
  lastPrompt: string;
}) {
  const repoPathsText = (draft.repoPaths ?? []).join("\n");
  const criteriaText = (draft.acceptanceCriteria ?? []).join("\n");

  return (
    <div style={{ border: "1px solid var(--border)", background: "var(--panel)" }}>
      <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)" }}>
        <span className="rail-label">Task Drafts</span>
      </div>
      <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {TASK_PRESETS.map((preset) => (
            <button
              key={preset.label}
              onClick={() => setDraft({ ...preset.draft })}
              style={{
                border: "1px solid var(--border)",
                background: "var(--bg)",
                color: "var(--fg)",
                padding: "6px 10px",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                cursor: "pointer",
              }}
            >
              {preset.label}
            </button>
          ))}
          <button
            onClick={() =>
              setDraft({
                ...draft,
                title: draft.title || deriveTitle(lastPrompt),
                description: draft.description || lastPrompt,
              })
            }
            disabled={!lastPrompt}
            style={{
              border: "1px solid var(--border)",
              background: lastPrompt ? "var(--bg)" : "var(--panel-alt)",
              color: lastPrompt ? "var(--fg)" : "var(--muted)",
              padding: "6px 10px",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              cursor: lastPrompt ? "pointer" : "not-allowed",
            }}
          >
            Seed from last prompt
          </button>
        </div>

        <input
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          placeholder="Task title"
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            color: "var(--fg)",
            padding: "8px 10px",
            fontSize: 13,
            outline: "none",
          }}
        />

        <textarea
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          placeholder="Describe what the planner should do and how success will be judged."
          rows={6}
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            color: "var(--fg)",
            padding: "8px 10px",
            fontSize: 12,
            outline: "none",
            resize: "vertical",
            lineHeight: 1.6,
          }}
        />

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
          <select
            value={draft.agentRole}
            onChange={(e) => setDraft({ ...draft, agentRole: e.target.value })}
            style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", padding: "8px 10px", fontSize: 12 }}
          >
            {ROLE_OPTIONS.map((role) => (
              <option key={role} value={role}>{role}</option>
            ))}
          </select>
          <select
            value={draft.status ?? "backlog"}
            onChange={(e) => setDraft({ ...draft, status: e.target.value })}
            style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", padding: "8px 10px", fontSize: 12 }}
          >
            {["backlog", "ready", "review", "blocked"].map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
          <input
            value={draft.runner ?? "codex_cli"}
            onChange={(e) => setDraft({ ...draft, runner: e.target.value })}
            placeholder="runner"
            style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", padding: "8px 10px", fontSize: 12, outline: "none" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <textarea
            value={repoPathsText}
            onChange={(e) => setDraft({
              ...draft,
              repoPaths: e.target.value.split("\n").map((item) => item.trim()).filter(Boolean),
            })}
            rows={6}
            placeholder="One repo path per line"
            style={{
              background: "var(--bg)",
              border: "1px solid var(--border)",
              color: "var(--fg)",
              padding: "8px 10px",
              fontSize: 11,
              outline: "none",
              resize: "vertical",
              fontFamily: "JetBrains Mono, monospace",
            }}
          />
          <textarea
            value={criteriaText}
            onChange={(e) => setDraft({
              ...draft,
              acceptanceCriteria: e.target.value.split("\n").map((item) => item.trim()).filter(Boolean),
            })}
            rows={6}
            placeholder="One acceptance criterion per line"
            style={{
              background: "var(--bg)",
              border: "1px solid var(--border)",
              color: "var(--fg)",
              padding: "8px 10px",
              fontSize: 11,
              outline: "none",
              resize: "vertical",
              fontFamily: "JetBrains Mono, monospace",
            }}
          />
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => onCreate(false)}
            disabled={creating || !draft.title.trim() || !draft.description.trim()}
            style={{
              flex: 1,
              border: "1px solid var(--border-strong)",
              background: creating ? "var(--panel-alt)" : "var(--fg)",
              color: creating ? "var(--muted)" : "var(--bg)",
              padding: "9px 10px",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              textTransform: "uppercase",
              cursor: creating ? "not-allowed" : "pointer",
            }}
          >
            {creating ? "Creating..." : "Create Task"}
          </button>
          <button
            onClick={() => onCreate(true)}
            disabled={creating || !draft.title.trim() || !draft.description.trim()}
            style={{
              flex: 1,
              border: "1px solid var(--border)",
              background: "var(--bg)",
              color: "var(--fg)",
              padding: "9px 10px",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              textTransform: "uppercase",
              cursor: creating ? "not-allowed" : "pointer",
            }}
          >
            Create + Autopilot
          </button>
        </div>
      </div>
    </div>
  );
}

export function PlannerWorkbench({ slug }: { slug: string }) {
  const [board, setBoard] = useState<PlannerBoard | null>(null);
  const [autopilot, setAutopilot] = useState<AutopilotStatus>({ enabled: false, autoApprove: false });
  const [draft, setDraft] = useState<PlannerTaskDraft>(blankDraft());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [composerError, setComposerError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [plannerPrompt, setPlannerPrompt] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [sendingPrompt, setSendingPrompt] = useState(false);

  async function load() {
    try {
      setError(null);
      const [nextBoard, nextAutopilot] = await Promise.all([
        fetchPlannerBoard(slug),
        fetchAutopilotStatus(slug),
      ]);
      setBoard(nextBoard);
      setAutopilot(nextAutopilot);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load planner state");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, [slug]);

  const metrics = useMemo(() => formatTaskCounts(board?.tasks ?? []), [board]);
  const diagnostics = useMemo(() => computeDiagnostics(board), [board]);
  const pendingApprovals = useMemo(
    () => (board?.approvals ?? []).filter((approval) => approval.status === "pending"),
    [board],
  );
  const lastPrompt = useMemo(() => {
    for (let i = chatMessages.length - 1; i >= 0; i -= 1) {
      if (chatMessages[i].role === "user") return chatMessages[i].content;
    }
    return "";
  }, [chatMessages]);

  async function handleAutopilot(nextEnabled: boolean, nextAutoApprove = autopilot.autoApprove) {
    await toggleProjectAutopilot(slug, { enabled: nextEnabled, autoApprove: nextAutoApprove });
    setAutopilot({ enabled: nextEnabled, autoApprove: nextAutoApprove });
    await load();
  }

  async function handlePromptSend(message: string) {
    const trimmed = message.trim();
    if (!trimmed || sendingPrompt) return;

    const nextHistory = [...chatMessages, { role: "user" as const, content: trimmed }];
    setSendingPrompt(true);
    setPlannerPrompt("");
    setChatMessages((prev) => [...prev, { role: "user", content: trimmed }, { role: "assistant", content: "" }]);

    try {
      const resp = await fetch(`${API_ROOT}/agent/chat?project=${encodeURIComponent(slug)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          history: nextHistory.map((item) => ({ role: item.role, content: item.content })),
        }),
      });
      if (!resp.ok || !resp.body) {
        throw new Error(`Planner chat failed: ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let content = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          try {
            const event = JSON.parse(line.slice(5).trim());
            if (event.type === "text_delta") {
              content += event.content ?? "";
              setChatMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = { role: "assistant", content };
                return next;
              });
            }
          } catch {
            // Ignore malformed SSE lines from intermediate events.
          }
        }
      }
      await load();
    } catch (err) {
      setChatMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: err instanceof Error ? err.message : "Planner chat failed.",
        };
        return next;
      });
    } finally {
      setSendingPrompt(false);
    }
  }

  async function handleCreate(startAutopilot: boolean) {
    setCreating(true);
    setComposerError(null);
    try {
      await createPlannerTask(slug, {
        ...draft,
        title: draft.title.trim(),
        description: draft.description.trim(),
        repoPaths: draft.repoPaths ?? [],
        acceptanceCriteria: draft.acceptanceCriteria ?? [],
        dependsOnTaskIds: draft.dependsOnTaskIds ?? [],
      });

      if (startAutopilot) {
        await handleAutopilot(true, autopilot.autoApprove);
      } else {
        await load();
      }

      setDraft(blankDraft());
    } catch (err) {
      setComposerError(err instanceof Error ? err.message : "Could not create planner task");
    } finally {
      setCreating(false);
    }
  }

  async function fixTaskState(task: PlannerTask) {
    await updatePlannerTask(slug, task._id, { status: "ready", approvalState: "granted" });
    await load();
  }

  return (
    <ProjectShell
      slug={slug}
      title="Planner"
      section="planner"
      rightRail={board ? <TaskBoard board={board} slug={slug} /> : undefined}
    >
      <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 10 }}>
          {metrics.map((metric) => (
            <div key={metric.label} style={{ border: "1px solid var(--border)", background: "var(--panel)", padding: "12px 14px" }}>
              <div className="rail-label">{metric.label}</div>
              <div style={{ marginTop: 8, fontSize: 24, fontWeight: 700, color: "var(--fg)" }}>{metric.value}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16, alignItems: "start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ border: "1px solid var(--border)", background: "var(--panel)" }}>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="rail-label">Planner Copilot</span>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <StatusPill value={autopilot.enabled ? "active" : "paused"} />
                  <button
                    onClick={() => handleAutopilot(!autopilot.enabled)}
                    style={{
                      border: "1px solid var(--border)",
                      background: "var(--bg)",
                      color: "var(--fg)",
                      padding: "5px 10px",
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      cursor: "pointer",
                    }}
                  >
                    {autopilot.enabled ? "Stop autopilot" : "Start autopilot"}
                  </button>
                  <button
                    onClick={() => handleAutopilot(autopilot.enabled, !autopilot.autoApprove)}
                    style={{
                      border: "1px solid var(--border)",
                      background: autopilot.autoApprove ? "var(--fg)" : "var(--bg)",
                      color: autopilot.autoApprove ? "var(--bg)" : "var(--fg)",
                      padding: "5px 10px",
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      cursor: "pointer",
                    }}
                  >
                    auto-approve: {autopilot.autoApprove ? "on" : "off"}
                  </button>
                </div>
              </div>

              <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {QUICK_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => setPlannerPrompt(prompt)}
                      style={{
                        border: "1px solid var(--border)",
                        background: "var(--bg)",
                        color: "var(--fg)",
                        padding: "6px 10px",
                        fontSize: 10,
                        fontFamily: "JetBrains Mono, monospace",
                        cursor: "pointer",
                        textAlign: "left",
                      }}
                    >
                      {deriveTitle(prompt)}
                    </button>
                  ))}
                </div>

                <div style={{ border: "1px solid var(--border)", background: "var(--bg)", minHeight: 180, maxHeight: 320, overflowY: "auto", padding: 12 }}>
                  {chatMessages.length === 0 ? (
                    <div style={{ color: "var(--muted)", fontSize: 12, lineHeight: 1.7 }}>
                      Ask the planner to create a research wave, clean up stale tasks, or propose the next validation pass. This uses the same project-aware chat surface that works from Codex, but directly inside the UI.
                    </div>
                  ) : (
                    chatMessages.map((message, index) => (
                      <div key={`${message.role}-${index}`} style={{ marginBottom: 12 }}>
                        <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", textTransform: "uppercase", marginBottom: 4 }}>
                          {message.role}
                        </div>
                        <div style={{
                          border: `1px solid ${message.role === "user" ? "var(--fg)" : "var(--border)"}`,
                          background: message.role === "user" ? "var(--fg)" : "var(--panel)",
                          color: message.role === "user" ? "var(--bg)" : "var(--fg)",
                          padding: "10px 12px",
                          whiteSpace: "pre-wrap",
                          lineHeight: 1.6,
                          fontSize: 12,
                        }}>
                          {message.content || (sendingPrompt && index === chatMessages.length - 1 ? "thinking..." : "")}
                        </div>
                      </div>
                    ))
                  )}
                </div>

                <textarea
                  value={plannerPrompt}
                  onChange={(e) => setPlannerPrompt(e.target.value)}
                  rows={4}
                  placeholder="Tell the planner what to do next..."
                  style={{
                    background: "var(--bg)",
                    border: "1px solid var(--border)",
                    color: "var(--fg)",
                    padding: "10px 12px",
                    resize: "vertical",
                    outline: "none",
                    fontSize: 12,
                    lineHeight: 1.6,
                  }}
                />

                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    onClick={() => handlePromptSend(plannerPrompt)}
                    disabled={sendingPrompt || !plannerPrompt.trim()}
                    style={{
                      border: "1px solid var(--border-strong)",
                      background: sendingPrompt ? "var(--panel-alt)" : "var(--fg)",
                      color: sendingPrompt ? "var(--muted)" : "var(--bg)",
                      padding: "8px 12px",
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      textTransform: "uppercase",
                      cursor: sendingPrompt ? "not-allowed" : "pointer",
                    }}
                  >
                    {sendingPrompt ? "Running..." : "Run planner prompt"}
                  </button>
                  <button
                    onClick={() => setDraft({
                      ...draft,
                      title: draft.title || deriveTitle(plannerPrompt),
                      description: draft.description || plannerPrompt,
                    })}
                    disabled={!plannerPrompt.trim()}
                    style={{
                      border: "1px solid var(--border)",
                      background: "var(--bg)",
                      color: "var(--fg)",
                      padding: "8px 12px",
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      textTransform: "uppercase",
                      cursor: plannerPrompt.trim() ? "pointer" : "not-allowed",
                    }}
                  >
                    Convert to task draft
                  </button>
                </div>
              </div>
            </div>

            <TaskDraftPanel
              draft={draft}
              setDraft={setDraft}
              onCreate={handleCreate}
              creating={creating}
              lastPrompt={lastPrompt}
            />
            {composerError && (
              <div style={{ border: "1px solid var(--s-failed)", background: "var(--s-failed)11", color: "var(--s-failed)", padding: "10px 12px", fontSize: 12 }}>
                {composerError}
              </div>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ border: "1px solid var(--border)", background: "var(--panel)" }}>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="rail-label">Approvals</span>
                <StatusPill value={pendingApprovals.length ? "pending" : "done"} />
              </div>
              <div style={{ padding: 14 }}>
                <ApprovalPanel approvals={pendingApprovals as PlannerApproval[]} slug={slug} />
              </div>
            </div>

            <div style={{ border: "1px solid var(--border)", background: "var(--panel)" }}>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)" }}>
                <span className="rail-label">Planner Diagnostics</span>
              </div>
              <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
                {diagnostics.map((item, index) => (
                  <div
                    key={`${item.label}-${index}`}
                    style={{
                      border: "1px solid var(--border)",
                      background: item.severity === "warn" ? "var(--s-awaiting)11" : "var(--bg)",
                      padding: "10px 12px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
                      <strong style={{ color: "var(--fg)", fontSize: 12 }}>{item.label}</strong>
                      <StatusPill value={item.severity === "warn" ? "awaiting_approval" : "info"} />
                    </div>
                    <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>{item.detail}</div>
                  </div>
                ))}
                {(board?.tasks ?? [])
                  .filter((task) => task.status === "awaiting_approval" && task.approvalState === "granted")
                  .map((task) => (
                    <button
                      key={task._id}
                      onClick={() => fixTaskState(task)}
                      style={{
                        border: "1px solid var(--border)",
                        background: "var(--bg)",
                        color: "var(--fg)",
                        padding: "8px 10px",
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 10,
                        textAlign: "left",
                        cursor: "pointer",
                      }}
                    >
                      Repair state: {task.title}
                    </button>
                  ))}
              </div>
            </div>
          </div>
        </div>

        {loading && !board && (
          <div style={{ color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>Loading planner state...</div>
        )}
        {error && (
          <div style={{ border: "1px solid var(--s-failed)", background: "var(--s-failed)11", color: "var(--s-failed)", padding: "10px 12px", fontSize: 12 }}>
            {error}
          </div>
        )}
      </div>
    </ProjectShell>
  );
}
