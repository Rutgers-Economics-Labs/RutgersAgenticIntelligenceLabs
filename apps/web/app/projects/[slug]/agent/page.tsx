"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ProjectShell } from "@/components/project-shell";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { fetchPlannerThread } from "@/lib/api";

const API_ROOT = process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

type MessageRole = "user" | "assistant" | "tool_result" | "error";

interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  isStreaming?: boolean;
}

function ToolArgPreview({ name, args }: { name?: string; args?: Record<string, unknown> }) {
  if (!args) return null;

  // run_bash — show the command
  if (name === "run_bash" || name === "run_shell") {
    const cmd = (args.command ?? args.cmd ?? args.script) as string | undefined;
    if (cmd) return (
      <span style={{ fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", marginLeft: 6, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 420, display: "inline-block", verticalAlign: "middle" }}>
        {cmd.slice(0, 120)}{cmd.length > 120 ? "…" : ""}
      </span>
    );
  }

  // spawn_research_agents — show focus areas and queries
  if (name === "spawn_research_agents") {
    const agents = (args.agents ?? []) as Array<{ focus: string; queries?: string[] }>;
    if (agents.length === 0) return null;
    return (
      <span style={{ fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", marginLeft: 6 }}>
        {agents.map(a => a.focus).join(" · ")}
      </span>
    );
  }

  // read_file / write_file — show the path
  if (name === "read_file" || name === "write_file") {
    const p = (args.path ?? args.file_path) as string | undefined;
    if (p) return (
      <span style={{ fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", marginLeft: 6 }}>
        {p}
      </span>
    );
  }

  // update_task / create_task — show task id/title
  if (name === "update_task" || name === "create_task") {
    const label = (args.task_id ?? args.title ?? args.id) as string | undefined;
    if (label) return (
      <span style={{ fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", marginLeft: 6 }}>
        {String(label).slice(0, 60)}
      </span>
    );
  }

  return null;
}

function ToolArgDetail({ name, args }: { name?: string; args?: Record<string, unknown> }) {
  if (!args) return null;

  // For spawn_research_agents, show each agent's full query list
  if (name === "spawn_research_agents") {
    const agents = (args.agents ?? []) as Array<{ focus: string; queries?: string[] }>;
    return (
      <div>
        {agents.map((a, i) => (
          <div key={i} style={{ marginBottom: 8 }}>
            <div style={{ fontWeight: 600, marginBottom: 2 }}>↳ {a.focus}</div>
            {(a.queries ?? []).map((q, j) => (
              <div key={j} style={{ paddingLeft: 10, opacity: 0.75 }}>• {q}</div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  return null;
}

function ToolRow({ msg }: { msg: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const isRunning = msg.isStreaming;
  const hasArgDetail = msg.toolName === "spawn_research_agents";

  return (
    <div style={{ marginBottom: 6 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 7,
          background: "none",
          border: "none",
          padding: "3px 0",
          cursor: "pointer",
          color: "var(--muted)",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 11,
          letterSpacing: "0.04em",
          width: "100%",
          textAlign: "left",
          minWidth: 0,
        }}
      >
        <span style={{
          display: "inline-block",
          width: 14,
          height: 14,
          border: "1px solid var(--border)",
          background: "var(--panel-alt)",
          flexShrink: 0,
          position: "relative",
        }}>
          {isRunning ? (
            <span style={{ position: "absolute", inset: 2, background: "var(--muted)", opacity: 0.5, animation: "pulse 1s infinite" }} />
          ) : (
            <span style={{ position: "absolute", inset: "3px 4px", borderLeft: "1px solid var(--muted)", borderBottom: "1px solid var(--muted)", transform: open ? "rotate(-135deg) translate(2px,-2px)" : "rotate(-45deg)", transition: "transform 120ms" }} />
          )}
        </span>
        <span style={{ color: "var(--fg)", fontWeight: 500, flexShrink: 0 }}>{msg.toolName}</span>
        {isRunning
          ? <span style={{ opacity: 0.5, flexShrink: 0 }}>running…</span>
          : <ToolArgPreview name={msg.toolName} args={msg.toolArgs} />
        }
      </button>

      {open && (
        <div style={{
          marginTop: 4,
          marginLeft: 21,
          padding: "8px 10px",
          background: "var(--panel-alt)",
          border: "1px solid var(--border)",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 11,
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          color: "var(--fg)",
          maxHeight: 400,
          overflowY: "auto",
        }}>
          {/* Show queries/args detail above result when running or has arg detail */}
          {(isRunning || hasArgDetail) && msg.toolArgs && (
            <div style={{ marginBottom: isRunning ? 0 : 10, opacity: 0.8 }}>
              <ToolArgDetail name={msg.toolName} args={msg.toolArgs} />
            </div>
          )}
          {!isRunning && msg.content && (
            <div style={{ borderTop: hasArgDetail ? "1px solid var(--border)" : "none", paddingTop: hasArgDetail ? 8 : 0 }}>
              {msg.content}
            </div>
          )}
          {isRunning && !hasArgDetail && <span style={{ opacity: 0.5 }}>running…</span>}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const isTool = msg.role === "tool_result";
  const isError = msg.role === "error";

  if (isTool) return <ToolRow msg={msg} />;

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: isUser ? "flex-end" : "flex-start",
      marginBottom: 16,
    }}>
      <div style={{
        maxWidth: "82%",
        padding: "10px 14px",
        border: `1px solid ${isError ? "var(--s-failed)" : isUser ? "var(--fg)" : "var(--border)"}`,
        background: isUser ? "var(--fg)" : "var(--panel)",
        color: isUser ? "var(--bg)" : isError ? "var(--s-failed)" : "var(--fg)",
        opacity: msg.isStreaming ? 0.85 : 1,
      }}>
        {isUser ? (
          <span style={{ fontFamily: "Inter, sans-serif", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {msg.content}
          </span>
        ) : (
          <div style={{ fontSize: 13, lineHeight: 1.6 }}>
            {msg.content
              ? <MarkdownRenderer content={msg.content + (msg.isStreaming ? " ▌" : "")} />
              : msg.isStreaming ? <span style={{ opacity: 0.5 }}>▌</span> : null
            }
          </div>
        )}
      </div>
    </div>
  );
}

export default function AgentPage() {
  const params = useParams<{ slug: string }>();
  const searchParams = useSearchParams();
  const slug = params.slug;
  const isWelcome = searchParams.get("welcome") === "1";

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState<object[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load existing planner thread on mount
  useEffect(() => {
    if (isWelcome) {
      const welcome = `I've set up your new project **${slug}** — a GitHub repo has been created and the initial ontology, pipeline, and data sources have been scaffolded.\n\nWhat would you like to research first? I can discover data sources, run a pipeline to populate the ontology, and start analysing once data is loaded.`;
      setMessages([{ id: "welcome", role: "assistant", content: welcome }]);
      setLoading(false);
      return;
    }
    fetchPlannerThread(slug)
      .then(({ messages: raw }) => {
        const loaded: ChatMessage[] = (raw as any[])
          .filter((m: any) => m.role === "user" || m.role === "assistant")
          .map((m: any, i: number) => ({
            id: `hist-${i}`,
            role: m.role as MessageRole,
            content: String(m.content ?? ""),
          }));
        setMessages(loaded);
        setHistory((raw as any[]).filter((m: any) => m.role === "user" || m.role === "assistant"));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [slug, isWelcome]);

  function startNewThread() {
    setMessages([]);
    setHistory([]);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  async function sendMessage(text: string) {
    if (!text.trim() || busy) return;
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: text.trim() };
    const assistantId = `a-${Date.now()}`;
    const assistantMsg: ChatMessage = { id: assistantId, role: "assistant", content: "", isStreaming: true };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setBusy(true);

    const newHistory = [...history, { role: "user", content: text.trim() }];

    try {
      const resp = await fetch(`${API_ROOT}/agent/chat?project=${encodeURIComponent(slug)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text.trim(), history: newHistory }),
      });

      if (!resp.ok || !resp.body) throw new Error(`Agent error: ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantContent = "";

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
              assistantContent += event.content ?? "";
              setMessages((prev) =>
                prev.map((m) => m.id === assistantId ? { ...m, content: assistantContent } : m)
              );
            } else if (event.type === "tool_call") {
              setMessages((prev) => [...prev, {
                id: `tool-${event.id}`,
                role: "tool_result" as MessageRole,
                toolName: event.name,
                toolArgs: event.args ?? {},
                content: "",
                isStreaming: true,
              }]);
            } else if (event.type === "tool_result") {
              const resultStr = typeof event.result === "string"
                ? event.result
                : JSON.stringify(event.result, null, 2);
              setMessages((prev) =>
                prev.map((m) => m.id === `tool-${event.id}`
                  ? { ...m, content: resultStr.slice(0, 600) + (resultStr.length > 600 ? "\n…" : ""), isStreaming: false }
                  : m
                )
              );
            } else if (event.type === "error") {
              setMessages((prev) =>
                prev.map((m) => m.id === assistantId
                  ? { ...m, role: "error" as MessageRole, content: event.message ?? "Agent error.", isStreaming: false }
                  : m
                )
              );
            } else if (event.type === "done") {
              setHistory(event.new_messages ?? newHistory);
            }
          } catch {}
        }
      }

      setMessages((prev) =>
        prev.map((m) => m.id === assistantId ? { ...m, isStreaming: false } : m)
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) => m.id === assistantId
          ? { ...m, role: "error" as MessageRole, content: err instanceof Error ? err.message : "Error contacting agent.", isStreaming: false }
          : m
        )
      );
    } finally {
      setBusy(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  return (
    <ProjectShell slug={slug} title="Research Agent" section="agent">
      <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

        {/* Thread bar */}
        <div style={{
          borderBottom: "1px solid var(--border)",
          padding: "6px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "var(--panel)",
          flexShrink: 0,
        }}>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
            {loading ? "Loading thread…" : messages.length > 0 ? `${messages.filter(m => m.role === "user" || m.role === "assistant").length} messages` : "New thread"}
          </span>
          <button
            onClick={startNewThread}
            disabled={busy}
            style={{
              background: "none",
              border: "1px solid var(--border)",
              padding: "2px 8px",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--muted)",
              cursor: "pointer",
            }}
          >
            + New thread
          </button>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
          {!loading && messages.length === 0 && (
            <div style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              gap: 8,
              color: "var(--muted)",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 12,
              textAlign: "center",
            }}>
              <div style={{ fontSize: 24, marginBottom: 4 }}>◎</div>
              <div>Research Agent</div>
              <div style={{ fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                {slug} · ready
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{
          borderTop: "1px solid var(--border)",
          background: "var(--panel)",
          padding: "12px 16px",
          display: "flex",
          gap: 10,
          alignItems: "flex-end",
        }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={busy ? "Agent is working…" : "Ask the research agent anything…"}
            disabled={busy}
            rows={1}
            style={{
              flex: 1,
              resize: "none",
              padding: "8px 12px",
              background: "var(--bg)",
              border: "1px solid var(--border)",
              color: "var(--fg)",
              fontFamily: "Inter, sans-serif",
              fontSize: 13,
              lineHeight: 1.5,
              outline: "none",
              overflowY: "auto",
              maxHeight: 120,
              opacity: busy ? 0.6 : 1,
            }}
            onInput={(e) => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = Math.min(el.scrollHeight, 120) + "px";
            }}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={busy || !input.trim()}
            style={{
              padding: "8px 14px",
              background: busy || !input.trim() ? "var(--panel-alt)" : "var(--fg)",
              color: busy || !input.trim() ? "var(--muted)" : "var(--bg)",
              border: "1px solid var(--border-strong)",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              cursor: busy || !input.trim() ? "not-allowed" : "pointer",
              flexShrink: 0,
            }}
          >
            {busy ? "…" : "Send"}
          </button>
        </div>
      </div>
    </ProjectShell>
  );
}
