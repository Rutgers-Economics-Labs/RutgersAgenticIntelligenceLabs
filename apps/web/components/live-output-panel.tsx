"use client";

import { useEffect, useRef, useState } from "react";

const API_ROOT = process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

type AgentInfo = {
  sessionId: string;
  role: string;
  runner: string;
  status: string;
  title: string;
  startedAt?: number;
  currentFocus?: string | null;
  thinkingSummary?: string | null;
  workingOn?: string | null;
  currentActivity?: {
    kind?: string | null;
    label?: string | null;
    summary?: string | null;
  } | null;
};

type TimelineItem = Record<string, unknown>;

type SessionOutput = {
  status?: string;
  stdoutTail?: string;
  stderrTail?: string;
  timeline?: TimelineItem[];
  currentFocus?: string | null;
  thinkingSummary?: string | null;
  workingOn?: string | null;
  activeFile?: string | null;
  activeCommand?: {
    name?: string | null;
    preview?: string | null;
    timestamp?: string | null;
    status?: string | null;
  } | null;
  waitingFor?: {
    kind?: string | null;
    summary?: string | null;
    timestamp?: string | null;
  } | null;
  currentActivity?: {
    kind?: string | null;
    label?: string | null;
    summary?: string | null;
    thinkingSummary?: string | null;
    workingOn?: string | null;
  } | null;
};

function statusColor(s: string): string {
  if (s === "running") return "var(--s-running)";
  if (s === "done" || s === "completed") return "var(--s-done)";
  if (s === "failed" || s === "error") return "var(--s-failed)";
  if (s === "awaiting_approval" || s === "awaiting_input") return "var(--s-awaiting)";
  return "var(--muted)";
}

function timelineEventColor(type: string): string {
  if (type.includes("error") || type.includes("fail")) return "var(--s-failed)";
  if (type.includes("tool") || type.includes("bash") || type.includes("exec")) return "var(--s-awaiting)";
  if (type.includes("complet") || type.includes("success")) return "var(--s-running)";
  return "var(--muted)";
}

export function LiveOutputPanel({ slug }: { slug: string }) {
  const [open, setOpen] = useState(false);
  const [height, setHeight] = useState(280);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [output, setOutput] = useState<Record<string, SessionOutput>>({});
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef<{ y: number; h: number } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Ctrl+` to toggle
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "`") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Poll active agents
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const resp = await fetch(`${API_ROOT}/projects/${slug}/agents/active`, { cache: "no-store" });
        if (!resp.ok) return;
        const data = await resp.json();
        if (cancelled) return;
        const list: AgentInfo[] = data.agents ?? [];
        setAgents(list);
        setActiveTab((prev) => {
          if (prev && list.find((a) => a.sessionId === prev)) return prev;
          return list[0]?.sessionId ?? null;
        });
      } catch {}
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, [slug]);

  // Poll output for active tab (only when panel open)
  useEffect(() => {
    if (!activeTab || !open) return;
    let cancelled = false;
    async function poll() {
      try {
        const resp = await fetch(
          `${API_ROOT}/projects/${slug}/runner/sessions/${encodeURIComponent(activeTab!)}/detail`,
          { cache: "no-store" }
        );
        if (!resp.ok) return;
        const data = await resp.json();
        if (cancelled) return;
        setOutput((prev) => ({ ...prev, [activeTab!]: data }));
      } catch {}
    }
    poll();
    const id = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(id); };
  }, [activeTab, open, slug]);

  // Auto-scroll on new output
  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [output, open]);

  // Drag to resize
  function onResizeMouseDown(e: React.MouseEvent) {
    e.preventDefault();
    dragStart.current = { y: e.clientY, h: height };
    setDragging(true);
  }

  useEffect(() => {
    if (!dragging) return;
    function onMove(e: MouseEvent) {
      if (!dragStart.current) return;
      const delta = dragStart.current.y - e.clientY;
      setHeight(Math.max(120, Math.min(600, dragStart.current.h + delta)));
    }
    function onUp() { setDragging(false); }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [dragging]);

  const currentOutput = activeTab ? output[activeTab] : null;
  const activeAgent = agents.find((agent) => agent.sessionId === activeTab) ?? null;
  const timelineItems = (currentOutput?.timeline ?? []).slice(-80);
  const stdout = currentOutput?.stdoutTail ?? "";
  const runningCount = agents.filter((a) => a.status === "running").length;

  return (
    <div
      style={{
        position: "fixed", bottom: 0, left: 220, right: 0,
        zIndex: 150,
        background: "var(--panel)",
        borderTop: "1px solid var(--border)",
        height: open ? height : 30,
        display: "flex", flexDirection: "column",
        transition: dragging ? "none" : "height 150ms ease",
      }}
    >
      {/* Resize handle */}
      {open && (
        <div
          onMouseDown={onResizeMouseDown}
          style={{
            position: "absolute", top: -3, left: 0, right: 0,
            height: 6, cursor: "ns-resize", zIndex: 1,
          }}
        />
      )}

      {/* Header */}
      <div
        style={{
          height: 30, flexShrink: 0,
          display: "flex", alignItems: "center",
          padding: "0 8px",
          borderBottom: open ? "1px solid var(--border)" : "none",
          background: "var(--bg)",
          gap: 4,
          userSelect: "none",
        }}
      >
        {/* Toggle button */}
        <button
          onClick={() => setOpen((o) => !o)}
          style={{
            background: "none", border: "none", cursor: "pointer",
            display: "flex", alignItems: "center", gap: 6,
            padding: "0 4px",
            fontFamily: "JetBrains Mono, monospace", fontSize: 10,
            color: "var(--muted)", letterSpacing: "0.1em", textTransform: "uppercase",
          }}
        >
          {open ? "▾" : "▸"} Output
          {runningCount > 0 && (
            <span style={{
              width: 6, height: 6, borderRadius: "50%",
              background: "var(--s-running)",
              animation: "pulse 1.2s infinite",
              display: "inline-block",
            }} />
          )}
        </button>

        {/* Separator */}
        <span style={{ color: "var(--border)", fontSize: 14, margin: "0 4px" }}>|</span>

        {/* Agent tabs */}
        {agents.length === 0 ? (
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
            no active agents
          </span>
        ) : (
          agents.map((agent) => {
            const active = activeTab === agent.sessionId;
            return (
              <button
                key={agent.sessionId}
                onClick={() => { setActiveTab(agent.sessionId); if (!open) setOpen(true); }}
                style={{
                  background: active ? "var(--panel-alt)" : "none",
                  border: `1px solid ${active ? "var(--border-strong)" : "transparent"}`,
                  padding: "1px 10px",
                  fontFamily: "JetBrains Mono, monospace", fontSize: 10,
                  color: active ? "var(--fg)" : "var(--muted)",
                  cursor: "pointer",
                  letterSpacing: "0.06em",
                  display: "flex", alignItems: "center", gap: 5,
                }}
                title={agent.currentFocus ?? agent.workingOn ?? agent.thinkingSummary ?? ""}
              >
                <span style={{
                  width: 5, height: 5, borderRadius: "50%", flexShrink: 0,
                  background: statusColor(agent.status),
                  animation: agent.status === "running" ? "pulse 1.2s infinite" : "none",
                }} />
                {agent.role} · {agent.runner}
              </button>
            );
          })
        )}

        {/* Shortcut hint + close */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "var(--muted)", letterSpacing: "0.06em" }}>
            ^`
          </span>
          {open && (
            <button
              onClick={() => setOpen(false)}
              style={{
                background: "none", border: "none",
                color: "var(--muted)", cursor: "pointer",
                fontSize: 16, lineHeight: 1, padding: "0 2px",
              }}
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {open && (
        <div style={{ flex: 1, overflow: "auto", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
          {!activeTab ? (
            <div style={{ padding: "24px 14px", color: "var(--muted)", textAlign: "center" }}>
              No agent selected. Launch a task to see live output.
            </div>
          ) : (
            <div>
              {/* Focus line */}
              {currentOutput?.currentFocus && (
                <div style={{
                  padding: "4px 12px",
                  background: "var(--panel-alt)",
                  borderBottom: "1px solid var(--border)",
                  fontSize: 11, color: "var(--fg)",
                }}>
                  <span style={{ color: "var(--muted)", marginRight: 8 }}>focus</span>
                  {currentOutput.currentFocus}
                </div>
              )}

              {(currentOutput?.workingOn || currentOutput?.activeFile || currentOutput?.activeCommand?.preview) && (
                <div style={{
                  padding: "4px 12px",
                  background: "var(--panel)",
                  borderBottom: "1px solid var(--border)",
                  fontSize: 11, color: "var(--fg)",
                }}>
                  <span style={{ color: "var(--muted)", marginRight: 8 }}>working on</span>
                  {currentOutput.workingOn ?? currentOutput.activeFile ?? currentOutput.activeCommand?.preview}
                </div>
              )}

              {(currentOutput?.thinkingSummary || activeAgent?.thinkingSummary) && (
                <div style={{
                  padding: "4px 12px",
                  background: "var(--panel)",
                  borderBottom: "1px solid var(--border)",
                  fontSize: 11, color: "var(--fg)",
                }}>
                  <span style={{ color: "var(--muted)", marginRight: 8 }}>thinking</span>
                  {currentOutput?.thinkingSummary ?? activeAgent?.thinkingSummary}
                </div>
              )}

              {currentOutput?.waitingFor?.summary && (
                <div style={{
                  padding: "4px 12px",
                  background: "var(--panel)",
                  borderBottom: "1px solid var(--border)",
                  fontSize: 11, color: "var(--s-awaiting)",
                }}>
                  <span style={{ color: "var(--muted)", marginRight: 8 }}>waiting for</span>
                  {currentOutput.waitingFor.summary}
                </div>
              )}

              {/* Timeline events */}
              {timelineItems.map((item, i) => {
                const type = String(item.eventType ?? item.type ?? item.event_type ?? "event");
                const msg = String(item.summary ?? item.message ?? item.content ?? item.label ?? "");
                const ts = item.timestamp
                  ? new Date(String(item.timestamp)).toLocaleTimeString("en-US", { hour12: false })
                  : "";
                return (
                  <div
                    key={i}
                    style={{
                      display: "flex", gap: 8, padding: "2px 12px",
                      borderBottom: "1px solid var(--border)",
                      lineHeight: 1.6, alignItems: "baseline",
                    }}
                  >
                    <span style={{ color: "var(--muted)", flexShrink: 0, fontSize: 10, minWidth: 60 }}>
                      {ts}
                    </span>
                    <span style={{
                      color: timelineEventColor(type),
                      flexShrink: 0, minWidth: 130, fontSize: 10,
                      textTransform: "uppercase", letterSpacing: "0.06em",
                    }}>
                      {type.replace(/_/g, " ")}
                    </span>
                    <span style={{ color: "var(--fg)", wordBreak: "break-word" }}>
                      {msg.slice(0, 400) || "—"}
                    </span>
                  </div>
                );
              })}

              {/* stdout tail */}
              {stdout && (
                <pre style={{
                  margin: 0, padding: "6px 12px",
                  color: "var(--fg)", background: "var(--bg)",
                  whiteSpace: "pre-wrap", wordBreak: "break-all",
                  fontSize: 11, borderTop: "1px solid var(--border)",
                }}>
                  {stdout.slice(-4000)}
                </pre>
              )}

              {!timelineItems.length && !stdout && (
                <div style={{ padding: "24px 14px", color: "var(--muted)", textAlign: "center" }}>
                  Waiting for output…
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
