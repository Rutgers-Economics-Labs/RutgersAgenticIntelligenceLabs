"use client";

import { useEffect, useRef, useState } from "react";
import { MarkdownRenderer } from "@/components/markdown-renderer";

const API_ROOT = process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

const SECTION_STARTERS: Record<string, string> = {
  overview:  "What's the current status of this project and what should I focus on?",
  zen:       "Give me a quick status update on this project.",
  dashboard: "Walk me through what the dashboard visualizations are showing.",
  planner:   "What are the next planner actions I should take, and is autopilot in a healthy state?",
  agent:     "What's the current research plan and what tasks are next?",
  launch:    "What should I know before launching a new research workflow?",
  sessions:  "What's the current state of the agent runs and are any stuck?",
  review:    "Are there pending approvals or review issues I should address?",
  skills:    "What capabilities do the agents have for this project?",
  sources:   "Why were these data sources chosen and what are their known limitations?",
  artifacts: "What outputs has the research produced and how reliable are they?",
  integrity: "Explain the assumptions and claims here — are there concerns I should address?",
  repo:      "Where are the key files I should look at in this repo?",
  ontology:  "Why were these ontology entities and relationships chosen for this project?",
  settings:  "What project settings should I review or update?",
};

type Msg = { role: "user" | "assistant"; content: string };

export function FloatingPlannerChat({ slug, section }: { slug: string; section: string }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      inputRef.current?.focus();
    }
  }, [messages, open]);

  // reset when navigating to a different section
  useEffect(() => {
    setMessages([]);
    setInput("");
  }, [section]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: trimmed }, { role: "assistant", content: "" }]);
    setInput("");
    setBusy(true);

    try {
      const resp = await fetch(`${API_ROOT}/agent/chat?project=${encodeURIComponent(slug)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, history }),
      });
      if (!resp.ok || !resp.body) throw new Error(`${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let acc = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          try {
            const ev = JSON.parse(line.slice(5).trim());
            if (ev.type === "text_delta") {
              acc += ev.content ?? "";
              setMessages((prev) => {
                const copy = [...prev];
                copy[copy.length - 1] = { role: "assistant", content: acc };
                return copy;
              });
            }
          } catch {}
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = { role: "assistant", content: `Error: ${err}` };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  const starter = SECTION_STARTERS[section];

  return (
    <>
      {/* trigger button */}
      <button
        onClick={() => setOpen((o) => !o)}
        title="Ask the planner"
        style={{
          position: "fixed",
          right: 24,
          bottom: 68,
          zIndex: 200,
          width: 36,
          height: 36,
          borderRadius: "50%",
          background: open ? "var(--fg)" : "var(--panel)",
          border: "1px solid var(--border-strong, var(--border))",
          color: open ? "var(--bg)" : "var(--fg)",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 16,
          fontWeight: 700,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 2px 10px rgba(0,0,0,0.18)",
          transition: "background 120ms, color 120ms",
        }}
      >
        {open ? "×" : "?"}
      </button>

      {/* chat panel */}
      {open && (
        <div
          style={{
            position: "fixed",
            right: 24,
            bottom: 112,
            width: 360,
            height: 420,
            zIndex: 199,
            background: "var(--panel)",
            border: "1px solid var(--border)",
            boxShadow: "0 4px 24px rgba(0,0,0,0.2)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {/* header */}
          <div
            style={{
              padding: "9px 14px",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "var(--panel-alt, var(--panel))",
            }}
          >
            <span
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "var(--muted)",
              }}
            >
              Ask Planner
            </span>
            <span style={{ color: "var(--border)", fontSize: 11 }}>·</span>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
              {section}
            </span>
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                style={{
                  marginLeft: "auto",
                  background: "none",
                  border: "none",
                  color: "var(--muted)",
                  fontSize: 9,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  cursor: "pointer",
                  fontFamily: "JetBrains Mono, monospace",
                  padding: 0,
                }}
              >
                clear
              </button>
            )}
          </div>

          {/* messages */}
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "12px 14px",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            {/* section-aware quick starter */}
            {messages.length === 0 && starter && (
              <button
                onClick={() => send(starter)}
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  padding: "9px 12px",
                  textAlign: "left",
                  cursor: "pointer",
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 11,
                  color: "var(--fg)",
                  lineHeight: 1.5,
                }}
              >
                <span
                  style={{
                    display: "block",
                    fontSize: 9,
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    color: "var(--muted)",
                    marginBottom: 5,
                  }}
                >
                  Ask about this page →
                </span>
                {starter}
              </button>
            )}

            {messages.map((m, i) => (
              <div key={i} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <span
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 9,
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    color: "var(--muted)",
                  }}
                >
                  {m.role === "user" ? "You" : "Planner"}
                </span>
                <div style={{ fontSize: 12, color: "var(--fg)", lineHeight: 1.55 }}>
                  {m.role === "assistant" ? (
                    m.content ? (
                      <MarkdownRenderer content={m.content} />
                    ) : (
                      <span
                        style={{
                          color: "var(--muted)",
                          fontFamily: "JetBrains Mono, monospace",
                          fontSize: 11,
                        }}
                      >
                        thinking…
                      </span>
                    )
                  ) : (
                    <span style={{ color: "var(--muted)" }}>{m.content}</span>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {/* input */}
          <div
            style={{
              padding: "10px 14px",
              borderTop: "1px solid var(--border)",
              display: "flex",
              gap: 8,
            }}
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder="Ask anything…"
              disabled={busy}
              style={{
                flex: 1,
                background: "var(--bg)",
                border: "1px solid var(--border)",
                color: "var(--fg)",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 11,
                padding: "6px 9px",
                outline: "none",
              }}
            />
            <button
              onClick={() => send(input)}
              disabled={busy || !input.trim()}
              style={{
                background: "var(--fg)",
                color: "var(--bg)",
                border: "none",
                padding: "6px 12px",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                letterSpacing: "0.08em",
                cursor: busy || !input.trim() ? "not-allowed" : "pointer",
                opacity: busy || !input.trim() ? 0.45 : 1,
                transition: "opacity 120ms",
              }}
            >
              {busy ? "…" : "↑"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
