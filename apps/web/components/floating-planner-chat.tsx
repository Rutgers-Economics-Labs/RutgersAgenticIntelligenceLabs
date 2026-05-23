"use client";

import { useEffect, useRef, useState } from "react";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { fetchPendingQa, answerPendingQuestion } from "@/lib/api";

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
  const [activeTab, setActiveTab] = useState<"chat" | "inbox">("chat");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingQuestions, setPendingQuestions] = useState<any[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Poll pending Q&As
  useEffect(() => {
    let active = true;

    async function loadQa() {
      try {
        const data = await fetchPendingQa(slug);
        if (active) {
          setPendingQuestions(data);
        }
      } catch (err) {
        console.error("Failed to fetch pending Q&A:", err);
      }
    }

    loadQa();
    const interval = setInterval(loadQa, 4000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [slug]);

  useEffect(() => {
    if (open && activeTab === "chat") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      inputRef.current?.focus();
    }
  }, [messages, open, activeTab]);

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

  async function handleAnswer(questionId: string) {
    const answerText = answers[questionId]?.trim();
    if (!answerText) return;

    try {
      await answerPendingQuestion(slug, questionId, answerText);
      setAnswers((prev) => {
        const copy = { ...prev };
        delete copy[questionId];
        return copy;
      });
      // Refresh pending Q&As immediately
      const data = await fetchPendingQa(slug);
      setPendingQuestions(data);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to submit answer");
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
        {pendingQuestions.length > 0 && !open && (
          <span
            style={{
              position: "absolute",
              top: "-4px",
              right: "-4px",
              background: "#ef4444",
              color: "#fff",
              borderRadius: "50%",
              padding: "2px 6px",
              fontSize: "9px",
              fontWeight: "bold",
              boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
            }}
          >
            {pendingQuestions.length}
          </span>
        )}
      </button>

      {/* chat panel */}
      {open && (
        <div
          style={{
            position: "fixed",
            right: 24,
            bottom: 112,
            width: 360,
            height: 440,
            zIndex: 199,
            background: "var(--panel)",
            border: "1px solid var(--border)",
            boxShadow: "0 4px 24px rgba(0,0,0,0.2)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            borderRadius: "8px",
          }}
        >
          {/* Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--border)", background: "var(--panel-alt, var(--panel))" }}>
            <button
              onClick={() => setActiveTab("chat")}
              style={{
                flex: 1,
                padding: "10px 12px",
                border: "none",
                background: activeTab === "chat" ? "var(--panel)" : "none",
                color: activeTab === "chat" ? "var(--fg)" : "var(--muted)",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: "10px",
                cursor: "pointer",
                borderBottom: activeTab === "chat" ? "2px solid var(--fg)" : "none",
                textTransform: "uppercase",
                fontWeight: "bold",
              }}
            >
              Chat
            </button>
            <button
              onClick={() => setActiveTab("inbox")}
              style={{
                flex: 1,
                padding: "10px 12px",
                border: "none",
                background: activeTab === "inbox" ? "var(--panel)" : "none",
                color: activeTab === "inbox" ? "var(--fg)" : "var(--muted)",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: "10px",
                cursor: "pointer",
                borderBottom: activeTab === "inbox" ? "2px solid var(--fg)" : "none",
                textTransform: "uppercase",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "6px",
                fontWeight: "bold",
              }}
            >
              Inbox
              {pendingQuestions.length > 0 && (
                <span
                  style={{
                    background: "#ef4444",
                    color: "#fff",
                    borderRadius: "10px",
                    padding: "1px 6px",
                    fontSize: "9px",
                    fontWeight: "bold",
                  }}
                >
                  {pendingQuestions.length}
                </span>
              )}
            </button>
          </div>

          {activeTab === "chat" ? (
            <>
              {/* header / section status */}
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
            </>
          ) : (
            /* Inbox Tab */
            <div
              style={{
                flex: 1,
                overflowY: "auto",
                padding: "12px 14px",
                display: "flex",
                flexDirection: "column",
                gap: 16,
              }}
            >
              {pendingQuestions.length === 0 ? (
                <div style={{ color: "var(--muted)", fontSize: 12, textAlign: "center", marginTop: 40, fontStyle: "italic" }}>
                  No pending questions in inbox.
                </div>
              ) : (
                pendingQuestions.map((q) => (
                  <div
                    key={q.question_id}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                      borderBottom: "1px solid var(--border)",
                      paddingBottom: 16,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span
                        style={{
                          fontFamily: "JetBrains Mono, monospace",
                          fontSize: 9,
                          color: "var(--fg-accent, #60a5fa)",
                          fontWeight: "bold",
                          textTransform: "uppercase",
                        }}
                      >
                        Session: {q.session_id.slice(0, 8)}…
                      </span>
                      <span style={{ fontSize: "10px", color: "var(--muted)" }}>
                        {q.timestamp ? new Date(q.timestamp).toLocaleTimeString() : ""}
                      </span>
                    </div>
                    <div style={{ fontSize: "12px", color: "var(--fg)", lineHeight: 1.5, fontWeight: "bold" }}>
                      {q.question}
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                      <input
                        placeholder="Type your answer…"
                        value={answers[q.question_id] || ""}
                        onChange={(e) => setAnswers({ ...answers, [q.question_id]: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            handleAnswer(q.question_id);
                          }
                        }}
                        style={{
                          flex: 1,
                          background: "var(--bg)",
                          border: "1px solid var(--border)",
                          color: "var(--fg)",
                          fontFamily: "JetBrains Mono, monospace",
                          fontSize: 11,
                          padding: "6px 8px",
                          outline: "none",
                        }}
                      />
                      <button
                        onClick={() => handleAnswer(q.question_id)}
                        disabled={!answers[q.question_id]?.trim()}
                        style={{
                          background: "var(--fg)",
                          color: "var(--bg)",
                          border: "none",
                          padding: "6px 12px",
                          fontFamily: "JetBrains Mono, monospace",
                          fontSize: 10,
                          cursor: answers[q.question_id]?.trim() ? "pointer" : "not-allowed",
                          opacity: answers[q.question_id]?.trim() ? 1 : 0.5,
                          fontWeight: "bold",
                        }}
                      >
                        Submit
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
