"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ProjectShell } from "@/components/project-shell";

const API_ROOT = process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

type MessageRole = "user" | "assistant" | "tool_result";

interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  toolName?: string;
  isStreaming?: boolean;
}

function ToolBadge({ name }: { name: string }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 7px",
      fontFamily: "JetBrains Mono, monospace",
      fontSize: 10,
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      background: "var(--panel-alt)",
      border: "1px solid var(--border)",
      color: "var(--muted)",
      marginBottom: 4,
    }}>
      {name}
    </span>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const isTool = msg.role === "tool_result";
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: isUser ? "flex-end" : "flex-start",
      marginBottom: 16,
    }}>
      {isTool && msg.toolName && <ToolBadge name={msg.toolName} />}
      <div style={{
        maxWidth: "82%",
        padding: "10px 14px",
        background: isUser ? "var(--fg)" : isTool ? "var(--panel-alt)" : "var(--panel)",
        color: isUser ? "var(--bg)" : "var(--fg)",
        border: `1px solid ${isTool ? "var(--border)" : isUser ? "var(--fg)" : "var(--border)"}`,
        fontFamily: isTool ? "JetBrains Mono, monospace" : "Inter, sans-serif",
        fontSize: isTool ? 11 : 13,
        lineHeight: 1.6,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        opacity: msg.isStreaming ? 0.85 : 1,
      }}>
        {msg.content || (msg.isStreaming ? "▌" : "")}
        {msg.isStreaming && msg.content && "▌"}
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
  const [history, setHistory] = useState<object[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Pre-seed welcome message on fresh project creation
  useEffect(() => {
    if (isWelcome && messages.length === 0) {
      const welcome = `I've set up your new project **${slug}** — a GitHub repo has been created and the initial ontology, pipeline, and data sources have been scaffolded.\n\nWhat would you like to research first? I can discover data sources, run a pipeline to populate the ontology, and start analysing once data is loaded.`;
      setMessages([{ id: "welcome", role: "assistant", content: welcome }]);
    }
  }, [isWelcome, slug]);

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
      const toolMessages: ChatMessage[] = [];

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
              const toolMsg: ChatMessage = {
                id: `tool-${event.id}`,
                role: "tool_result",
                toolName: event.name,
                content: `Calling ${event.name}…`,
                isStreaming: true,
              };
              toolMessages.push(toolMsg);
              setMessages((prev) => [...prev, toolMsg]);
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
          ? { ...m, content: err instanceof Error ? err.message : "Error contacting agent.", isStreaming: false }
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

        {/* Messages */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
          {messages.length === 0 && (
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
