"use client";

import { Suspense, useEffect, useRef, useState, useCallback } from "react";
import { useMutation, useQuery } from "convex/react";
import { useRouter, useSearchParams } from "next/navigation";
import { Id } from "@/convex/_generated/dataModel";
import { api as convexApi } from "@/convex/_generated/api";
import { agent, AgentEvent, ModelInfo, sql } from "@/lib/api";
import { ANALYSIS_TEMPLATES } from "@/lib/analysis-templates";
import {
  Bot, User, Send, ChevronDown, ChevronRight,
  Code2, Loader2, Sparkles, RotateCcw, Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type MessageRole = "user" | "assistant";

interface ToolCallBlock {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
}

interface Message {
  id: string;
  role: MessageRole;
  content: string;
  toolCalls?: ToolCallBlock[];
  streaming?: boolean;
}

type SessionId = Id<"agentSessions">;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

function timeAgo(ms: number) {
  const diff = Math.floor((Date.now() - ms) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function isChatMessage(
  msg: { role: "user" | "assistant" | "tool"; content?: string }
): msg is { role: MessageRole; content?: string } {
  return msg.role === "user" || msg.role === "assistant";
}

function formatSchemaForPrompt(schema: Record<string, { name: string; type: string }[]>) {
  const tables = Object.entries(schema).map(([table, columns]) => {
    const cols = columns.map((column) => `${column.name}`).join(", ");
    return `${table}(${cols})`;
  });
  return tables.length > 0 ? `[Schema: ${tables.join("; ")}]` : "";
}

const TOOL_LABELS: Record<string, string> = {
  list_configs: "Listing configs",
  create_config: "Creating config",
  run_pipeline: "Running pipeline",
  query_ontology: "Querying ontology",
  run_sql: "Running SQL",
  get_sql_schema: "Reading schema",
  execute_python: "Executing Python",
  get_series_data: "Fetching series",
  search_entities: "Searching entities",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ToolCallCard({ tc }: { tc: ToolCallBlock }) {
  const [open, setOpen] = useState(false);
  const label = TOOL_LABELS[tc.name] ?? tc.name;

  return (
    <div className="my-1 rounded border border-[--border] bg-[--muted]/40 text-xs">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[--muted-foreground] hover:text-[--foreground] transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Code2 size={12} className="text-[--primary]" />
        <span className="font-medium text-[--primary]">{label}</span>
        {tc.result !== undefined && !open && (
          <span className="ml-auto text-[10px] text-green-400/70">done</span>
        )}
      </button>
      {open && (
        <div className="border-t border-[--border] px-3 py-2 space-y-2">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-[--muted-foreground] mb-1">Input</p>
            <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px] text-[--foreground]">
              {JSON.stringify(tc.args, null, 2)}
            </pre>
          </div>
          {tc.result !== undefined && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[--muted-foreground] mb-1">Result</p>
              <ToolResult name={tc.name} result={tc.result} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ToolResult({ name, result }: { name: string; result: unknown }) {
  if (!result || typeof result !== "object") {
    return (
      <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px] text-[--foreground]">
        {String(result)}
      </pre>
    );
  }

  const r = result as Record<string, unknown>;

  // SQL / table result
  if (Array.isArray(r.rows) && Array.isArray(r.columns)) {
    const cols = r.columns as string[];
    const rows = r.rows as Record<string, unknown>[];
    const rowCount = typeof r.rowCount === "number" ? r.rowCount : rows.length;
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-[11px] border-collapse">
          <thead>
            <tr>
              {cols.map(c => (
                <th key={c} className="border border-[--border] px-2 py-1 text-left text-[--muted-foreground] bg-black/20">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 20).map((row, i) => (
              <tr key={i} className="odd:bg-black/10">
                {cols.map(c => (
                  <td key={c} className="border border-[--border] px-2 py-1 text-[--foreground]">
                    {String(row[c] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > 20 && (
          <p className="mt-1 text-[10px] text-[--muted-foreground]">
            Showing 20 of {rowCount} rows
          </p>
        )}
      </div>
    );
  }

  // Code execution result
  if (name === "execute_python") {
    const dataframes =
      r.dataframes && typeof r.dataframes === "object"
        ? (r.dataframes as Record<string, unknown>)
        : null;

    return (
      <div className="space-y-2">
        {typeof r.error === "string" && r.error && (
          <pre className="rounded bg-red-900/30 p-2 text-[11px] text-red-300">{r.error}</pre>
        )}
        {typeof r.stdout === "string" && r.stdout && (
          <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px] text-[--foreground]">{r.stdout}</pre>
        )}
        {Array.isArray(r.figures) && r.figures.map((fig: string, i: number) => (
          <img key={i} src={`data:image/png;base64,${fig}`} alt="plot" className="max-w-full rounded" />
        ))}
        {dataframes &&
          Object.entries(dataframes).map(([dfName, df]) => {
            const d = df as { columns: string[]; rows: Record<string, unknown>[]; rowCount: number };
            return (
              <div key={dfName}>
                <p className="text-[10px] text-[--muted-foreground] mb-1">{dfName} ({d.rowCount} rows)</p>
                <ToolResult name="sql" result={{ columns: d.columns, rows: d.rows, rowCount: d.rowCount }} />
              </div>
            );
          })
        }
      </div>
    );
  }

  // Generic JSON
  return (
    <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px] text-[--foreground] max-h-48">
      {JSON.stringify(result, null, 2)}
    </pre>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";

  return (
    <div className={cn("flex gap-3 px-1", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-0.5 shrink-0 w-7 h-7 rounded-full bg-[--primary]/20 flex items-center justify-center">
          <Bot size={14} className="text-[--primary]" />
        </div>
      )}
      <div className={cn("max-w-[80%] space-y-1", isUser ? "items-end" : "items-start")}>
        {/* Tool calls */}
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="space-y-1">
            {msg.toolCalls.map(tc => (
              <ToolCallCard key={tc.id} tc={tc} />
            ))}
          </div>
        )}
        {/* Text content */}
        {(msg.content || msg.streaming) && (
          <div
            className={cn(
              "rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
              isUser
                ? "bg-[--primary] text-[--primary-foreground] rounded-tr-sm"
                : "bg-[--muted] text-[--foreground] rounded-tl-sm"
            )}
          >
            {msg.content}
            {msg.streaming && (
              <span className="inline-block w-1.5 h-4 ml-0.5 bg-current rounded-sm animate-pulse align-middle" />
            )}
          </div>
        )}
      </div>
      {isUser && (
        <div className="mt-0.5 shrink-0 w-7 h-7 rounded-full bg-[--muted] flex items-center justify-center">
          <User size={14} className="text-[--muted-foreground]" />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

function WorkspacePageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [schemaSummary, setSchemaSummary] = useState("");
  const [currentSessionId, setCurrentSessionId] = useState<SessionId | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Conversation history for API (role/content only)
  const historyRef = useRef<{ role: string; content: string }[]>([]);

  const sessions = useQuery(convexApi.agent.listSessions, { limit: 20 });
  const currentSession = useQuery(
    convexApi.agent.getSession,
    currentSessionId ? { sessionId: currentSessionId } : "skip"
  );
  const createSession = useMutation(convexApi.agent.createSession);
  const appendMessages = useMutation(convexApi.agent.appendMessages);
  const updateTitle = useMutation(convexApi.agent.updateTitle);
  const deleteSession = useMutation(convexApi.agent.deleteSession);

  useEffect(() => {
    agent.models().then(data => {
      setModels(data.models);
      setSelectedModel(data.default);
    }).catch(() => {});
    sql.schema()
      .then((schema) => setSchemaSummary(formatSchemaForPrompt(schema)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const sessionParam = searchParams.get("session");
    setCurrentSessionId(sessionParam ? (sessionParam as SessionId) : null);
  }, [searchParams]);

  useEffect(() => {
    if (!currentSessionId) {
      setMessages([]);
      historyRef.current = [];
      return;
    }
    if (currentSession === undefined) return;
    if (!currentSession) {
      setMessages([]);
      historyRef.current = [];
      return;
    }

    const restoredMessages: Message[] = currentSession.messages
      .filter(isChatMessage)
      .map((msg) => ({
        id: uid(),
        role: msg.role,
        content: msg.content ?? "",
      }));

    setMessages(restoredMessages);
    historyRef.current = currentSession.messages
      .filter((msg): msg is { role: MessageRole; content: string } => isChatMessage(msg) && typeof msg.content === "string")
      .map((msg) => ({
        role: msg.role,
        content: msg.content ?? "",
      }));
  }, [currentSessionId, currentSession]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    let activeSessionId = currentSessionId;
    const shouldCreateSession = !activeSessionId && historyRef.current.length === 0;
    if (!activeSessionId) {
      const created = await createSession({
        title: text.slice(0, 60),
        model: selectedModel || "unknown-model",
      });
      activeSessionId = created.sessionId;
      setCurrentSessionId(activeSessionId);
      router.push(`/workspace?session=${activeSessionId}`);
    }

    setInput("");
    setLoading(true);

    // Add user message
    const userMsg: Message = { id: uid(), role: "user", content: text };
    setMessages(prev => [...prev, userMsg]);

    // Placeholder assistant message
    const asstId = uid();
    const asstMsg: Message = { id: asstId, role: "assistant", content: "", toolCalls: [], streaming: true };
    setMessages(prev => [...prev, asstMsg]);

    // Track tool calls by id for result attachment
    const pendingToolCalls: Record<string, ToolCallBlock> = {};

    try {
      for await (const event of agent.chat(text, historyRef.current, selectedModel || undefined)) {
        if (event.type === "text_delta") {
          setMessages(prev => prev.map(m =>
            m.id === asstId ? { ...m, content: m.content + event.content } : m
          ));
        } else if (event.type === "tool_call") {
          const tc: ToolCallBlock = { id: event.id, name: event.name, args: event.args };
          pendingToolCalls[event.id] = tc;
          setMessages(prev => prev.map(m =>
            m.id === asstId ? { ...m, toolCalls: [...(m.toolCalls ?? []), tc] } : m
          ));
        } else if (event.type === "tool_result") {
          if (pendingToolCalls[event.id]) {
            pendingToolCalls[event.id].result = event.result;
          }
          setMessages(prev => prev.map(m => {
            if (m.id !== asstId) return m;
            return {
              ...m,
              toolCalls: (m.toolCalls ?? []).map(tc =>
                tc.id === event.id ? { ...tc, result: event.result } : tc
              ),
            };
          }));
        } else if (event.type === "done") {
          // Save new messages to history
          historyRef.current = [
            ...historyRef.current,
            ...event.new_messages,
          ];

          if (activeSessionId) {
            const persistedMessages = event.new_messages
              .filter((msg) => msg.role === "user" || msg.role === "assistant")
              .map((msg) => ({
                role: msg.role as "user" | "assistant",
                content: msg.content,
              }));

            if (persistedMessages.length > 0) {
              await appendMessages({
                sessionId: activeSessionId,
                messages: persistedMessages,
              });
            }

            if (shouldCreateSession) {
              const firstAssistantMessage = persistedMessages.find((msg) => msg.role === "assistant" && msg.content);
              if (firstAssistantMessage?.content) {
                await updateTitle({
                  sessionId: activeSessionId,
                  title: firstAssistantMessage.content.slice(0, 80),
                });
              }
            }
          }
        } else if (event.type === "error") {
          setMessages(prev => prev.map(m =>
            m.id === asstId
              ? { ...m, content: `Error: ${event.message}`, streaming: false }
              : m
          ));
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id === asstId
          ? { ...m, content: `Error: ${err instanceof Error ? err.message : String(err)}`, streaming: false }
          : m
      ));
    } finally {
      setMessages(prev => prev.map(m =>
        m.id === asstId ? { ...m, streaming: false } : m
      ));
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [appendMessages, createSession, currentSessionId, input, loading, router, selectedModel, updateTitle]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearSession = () => {
    setCurrentSessionId(null);
    setMessages([]);
    historyRef.current = [];
    router.push("/workspace");
  };

  const handleLoadSession = (sessionId: SessionId) => {
    setCurrentSessionId(sessionId);
    router.push(`/workspace?session=${sessionId}`);
  };

  const handleDeleteSession = async (sessionId: SessionId) => {
    await deleteSession({ sessionId });
    if (currentSessionId === sessionId) {
      clearSession();
    }
  };

  const isEmpty = messages.length === 0;
  const groupedTemplates = ANALYSIS_TEMPLATES.reduce<Record<string, typeof ANALYSIS_TEMPLATES>>((acc, template) => {
    acc[template.category] ??= [];
    acc[template.category].push(template);
    return acc;
  }, {});

  const applyTemplate = (prompt: string) => {
    const nextPrompt = schemaSummary ? `${schemaSummary}\n${prompt}` : prompt;
    setInput(nextPrompt);
    setTemplatesOpen(false);
    textareaRef.current?.focus();
  };

  return (
    <div className="flex h-screen bg-[--background]">
      <aside className="hidden md:flex w-72 shrink-0 flex-col border-r border-[--border] bg-[--card]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[--border]">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-[--primary]" />
            <span className="text-sm font-semibold text-[--foreground]">Workspace</span>
          </div>
          <button
            onClick={clearSession}
            title="New session"
            className="flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted] transition-colors"
          >
            <RotateCcw size={12} />
            New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {sessions === undefined && (
            <p className="text-xs text-[--muted-foreground] px-2 py-1">Loading sessions…</p>
          )}
          {sessions?.map((session) => (
            <button
              key={session._id}
              onClick={() => handleLoadSession(session._id)}
              className={cn(
                "w-full rounded-lg border px-3 py-2 text-left transition-colors",
                currentSessionId === session._id
                  ? "border-[--primary]/50 bg-[--primary]/10"
                  : "border-[--border] bg-[--background] hover:border-[--primary]/30 hover:bg-[--muted]"
              )}
            >
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-[--foreground]">{session.title}</p>
                  <p className="mt-1 text-[10px] text-[--muted-foreground]">{session.model}</p>
                  <p className="mt-1 text-[10px] text-[--muted-foreground]">Updated {timeAgo(session.updatedAt)}</p>
                </div>
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleDeleteSession(session._id);
                  }}
                  className="rounded p-1 text-[--muted-foreground] hover:bg-black/10 hover:text-red-400"
                >
                  <Trash2 size={12} />
                </span>
              </div>
            </button>
          ))}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header */}
        <header className="flex items-center justify-between px-5 py-3 border-b border-[--border] bg-[--card] shrink-0">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-[--primary]" />
            <span className="text-sm font-semibold text-[--foreground]">AI Research Workspace</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <select
                value={selectedModel}
                onChange={e => setSelectedModel(e.target.value)}
                className="appearance-none bg-[--muted] border border-[--border] rounded-md px-3 py-1.5 text-xs text-[--foreground] pr-7 cursor-pointer focus:outline-none focus:ring-1 focus:ring-[--primary]"
              >
                {models.map(m => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
              <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-[--muted-foreground] pointer-events-none" />
            </div>
            <button
              onClick={clearSession}
              title="New session"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted] transition-colors md:hidden"
            >
              <RotateCcw size={12} />
              New
            </button>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto py-6 px-4 space-y-5">
          {isEmpty && (
            <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
              <div className="w-14 h-14 rounded-2xl bg-[--primary]/10 flex items-center justify-center">
                <Bot size={28} className="text-[--primary]" />
              </div>
              <div>
                <p className="text-[--foreground] font-medium">RAIL Research Agent</p>
                <p className="text-sm text-[--muted-foreground] mt-1 max-w-sm">
                  Ask a research question. The agent can fetch data, build pipelines,
                  run SQL queries, and execute Python analysis autonomously.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2 max-w-xl w-full">
                {[
                  "What's the unemployment trend in NJ counties over the last 5 years?",
                  "Compare GDP growth across US states and cluster them by economic profile",
                  "Run a DiD analysis on housing prices before and after 2020",
                  "Which NJ municipalities have the highest income per capita?",
                ].map(prompt => (
                  <button
                    key={prompt}
                    onClick={() => { setInput(prompt); textareaRef.current?.focus(); }}
                    className="text-left px-3 py-2.5 rounded-lg border border-[--border] bg-[--muted]/40 text-xs text-[--muted-foreground] hover:text-[--foreground] hover:border-[--primary]/40 hover:bg-[--primary]/5 transition-all"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map(msg => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="shrink-0 px-4 pb-4">
          <div className="mb-3 rounded-xl border border-[--border] bg-[--card]">
            <button
              onClick={() => setTemplatesOpen((value) => !value)}
              className="flex w-full items-center justify-between px-4 py-3 text-left"
            >
              <div>
                <p className="text-sm font-medium text-[--foreground]">Templates</p>
                <p className="text-xs text-[--muted-foreground]">Insert a schema-aware analysis prompt.</p>
              </div>
              {templatesOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </button>
            {templatesOpen && (
              <div className="border-t border-[--border] px-4 py-4 space-y-4">
                {Object.entries(groupedTemplates).map(([category, templates]) => (
                  <div key={category} className="space-y-2">
                    <p className="text-[10px] uppercase tracking-wide text-[--muted-foreground]">{category}</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
                      {(templates ?? []).map((template) => (
                        <button
                          key={template.id}
                          onClick={() => applyTemplate(template.prompt)}
                          className="rounded-lg border border-[--border] bg-[--background] px-3 py-3 text-left hover:border-[--primary]/40 hover:bg-[--primary]/5"
                        >
                          <div className="flex items-center gap-2">
                            <span className="inline-block h-2 w-2 rounded-full bg-[--primary]" />
                            <p className="text-sm font-medium text-[--foreground]">{template.label}</p>
                          </div>
                          <p className="mt-1 text-xs text-[--muted-foreground]">{template.description}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="relative flex items-end gap-2 rounded-xl border border-[--border] bg-[--muted] p-2 focus-within:border-[--primary]/50 transition-colors">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a research question… (Enter to send, Shift+Enter for newline)"
              rows={1}
              disabled={loading}
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-[--foreground] placeholder:text-[--muted-foreground] focus:outline-none max-h-32 overflow-y-auto"
              style={{ fieldSizing: "content" } as React.CSSProperties}
            />
            <button
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              className={cn(
                "shrink-0 flex items-center justify-center w-8 h-8 rounded-lg transition-all",
                loading || !input.trim()
                  ? "bg-[--muted-foreground]/20 text-[--muted-foreground] cursor-not-allowed"
                  : "bg-[--primary] text-[--primary-foreground] hover:opacity-90"
              )}
            >
              {loading
                ? <Loader2 size={14} className="animate-spin" />
                : <Send size={14} />
              }
            </button>
          </div>
          <p className="mt-1.5 text-center text-[10px] text-[--muted-foreground]">
            Agent can create configs, run pipelines, execute SQL and Python automatically.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function WorkspacePage() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center text-sm text-[--muted-foreground]">Loading workspace…</div>}>
      <WorkspacePageInner />
    </Suspense>
  );
}
