"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useMutation, useQuery } from "convex/react";
import { api as convexApi } from "@/convex/_generated/api";
import { agent, ModelInfo, sql } from "@/lib/api";
import { ANALYSIS_TEMPLATES } from "@/lib/analysis-templates";
import { Bot, User, Send, ChevronDown, ChevronRight, Code2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { ToolResult } from "@/components/jobs/ToolResult";
import { Id } from "@/convex/_generated/dataModel";
import { ContextSnapshot } from "./ContextSnapshot";

type MessageRole = "user" | "assistant";

interface ToolCallBlock {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  toolCalls?: ToolCallBlock[];
  streaming?: boolean;
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

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

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
          <div className="space-y-1 w-full min-w-[300px]">
            {msg.toolCalls.map(tc => (
              <ToolCallCard key={tc.id} tc={tc} />
            ))}
          </div>
        )}
        {/* Text content */}
        {(msg.content || msg.streaming) && (
          <div
            className={cn(
              "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
              isUser
                ? "bg-[--primary] text-[--primary-foreground] rounded-tr-sm whitespace-pre-wrap"
                : "bg-[--muted] text-[--foreground] rounded-tl-sm"
            )}
          >
            {isUser ? (
              msg.content
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                  code({ className, children, ...props }) {
                    const isBlock = className?.startsWith("language-");
                    return isBlock ? (
                      <pre className="overflow-x-auto rounded bg-black/30 p-3 text-[11px] my-2">
                        <code className={className} {...props}>{children}</code>
                      </pre>
                    ) : (
                      <code className="bg-black/20 rounded px-1 py-0.5 text-[11px] font-mono" {...props}>
                        {children}
                      </code>
                    );
                  },
                  a({ href, children }) {
                    return <a href={href} target="_blank" rel="noopener noreferrer" className="text-[--primary] underline underline-offset-2">{children}</a>;
                  },
                  ul({ children }) { return <ul className="list-disc list-inside space-y-0.5 my-1">{children}</ul>; },
                  ol({ children }) { return <ol className="list-decimal list-inside space-y-0.5 my-1">{children}</ol>; },
                  h1({ children }) { return <h1 className="text-base font-semibold mt-3 mb-1">{children}</h1>; },
                  h2({ children }) { return <h2 className="text-sm font-semibold mt-2 mb-1">{children}</h2>; },
                  h3({ children }) { return <h3 className="text-sm font-medium mt-2 mb-0.5">{children}</h3>; },
                  blockquote({ children }) { return <blockquote className="border-l-2 border-[--primary] pl-3 italic text-[--muted-foreground]">{children}</blockquote>; },
                  table({ children }) { return <div className="overflow-x-auto my-2"><table className="w-full text-[11px] border-collapse">{children}</table></div>; },
                  th({ children }) { return <th className="border border-[--border] px-2 py-1 text-left bg-black/20 text-[--muted-foreground]">{children}</th>; },
                  td({ children }) { return <td className="border border-[--border] px-2 py-1">{children}</td>; },
                }}
              >
                {msg.content}
              </ReactMarkdown>
            )}
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

interface AgentChatProps {
  projectSlug: string;
  sessionId?: string;
  messages: Message[];
  onMessages: (messages: Message[] | ((prev: Message[]) => Message[])) => void;
  onContextSnapshot?: (snapshot: any) => void;
  onSessionCreated?: (sessionId: string) => void;
  schemaSummary?: string;
  models: ModelInfo[];
  selectedModel: string;
  contextSnapshot?: any;
}

export function AgentChat({
  projectSlug,
  sessionId,
  messages,
  onMessages,
  onContextSnapshot,
  onSessionCreated,
  schemaSummary,
  models,
  selectedModel,
  contextSnapshot,
}: AgentChatProps) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [templatesOpen, setTemplatesOpen] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const historyRef = useRef<{ role: string; content: string }[]>([]);

  const createSession = useMutation(convexApi.agent.createSession);
  const appendMessages = useMutation(convexApi.agent.appendMessages);
  const updateTitle = useMutation(convexApi.agent.updateTitle);

  // Sync history based on messages prop when loaded from an existing session
  useEffect(() => {
    if (sessionId && messages.length > 0 && historyRef.current.length === 0) {
      historyRef.current = messages.map(m => ({ role: m.role, content: m.content }));
    }
  }, [sessionId, messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    let activeSessionId = sessionId as Id<"agentSessions"> | undefined;
    const shouldCreateSession = !activeSessionId && messages.length === 0;

    const activeModel = selectedModel || models[0]?.id || "unknown-model";

    if (shouldCreateSession) {
      const created = await createSession({
        title: text.slice(0, 60),
        model: activeModel,
        projectSlug,
      });
      activeSessionId = created.sessionId;
      onSessionCreated?.(activeSessionId);
    }

    setInput("");
    setLoading(true);

    const userMsg: Message = { id: uid(), role: "user", content: text };
    onMessages(prev => [...prev, userMsg]);

    const asstId = uid();
    const asstMsg: Message = { id: asstId, role: "assistant", content: "", toolCalls: [], streaming: true };
    onMessages(prev => [...prev, asstMsg]);

    const pendingToolCalls: Record<string, ToolCallBlock> = {};

    try {
      for await (const event of agent.chat(text, historyRef.current, activeModel, projectSlug)) {
        if (event.type === "context_snapshot") {
          onContextSnapshot?.(event.data);
        } else if (event.type === "text_delta") {
          onMessages(prev => prev.map(m =>
            m.id === asstId ? { ...m, content: m.content + event.content } : m
          ));
        } else if (event.type === "tool_call") {
          const tc: ToolCallBlock = { id: event.id, name: event.name, args: event.args };
          pendingToolCalls[event.id] = tc;
          onMessages(prev => prev.map(m =>
            m.id === asstId ? { ...m, toolCalls: [...(m.toolCalls ?? []), tc] } : m
          ));
        } else if (event.type === "tool_result") {
          if (pendingToolCalls[event.id]) {
            pendingToolCalls[event.id].result = event.result;
          }
          onMessages(prev => prev.map(m => {
            if (m.id !== asstId) return m;
            return {
              ...m,
              toolCalls: (m.toolCalls ?? []).map(tc =>
                tc.id === event.id ? { ...tc, result: event.result } : tc
              ),
            };
          }));
        } else if (event.type === "done") {
          historyRef.current = [...historyRef.current, ...event.new_messages];

          if (activeSessionId) {
            const persistedMessages = event.new_messages
              .filter((msg) => msg.role === "user" || msg.role === "assistant" || msg.role === "tool")
              .map((msg) => ({
                role: msg.role as "user" | "assistant" | "tool",
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
          onMessages(prev => prev.map(m =>
            m.id === asstId
              ? { ...m, content: `Error: ${event.message}`, streaming: false }
              : m
          ));
        }
      }
    } catch (err) {
      onMessages(prev => prev.map(m =>
        m.id === asstId
          ? { ...m, content: `Error: ${err instanceof Error ? err.message : String(err)}`, streaming: false }
          : m
      ));
    } finally {
      onMessages(prev => prev.map(m =>
        m.id === asstId ? { ...m, streaming: false } : m
      ));
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [appendMessages, createSession, input, loading, models, onMessages, onSessionCreated, projectSlug, selectedModel, sessionId, updateTitle, onContextSnapshot]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const applyTemplate = (prompt: string) => {
    const nextPrompt = schemaSummary ? `${schemaSummary}\n${prompt}` : prompt;
    setInput(nextPrompt);
    setTemplatesOpen(false);
    textareaRef.current?.focus();
  };

  const groupedTemplates = ANALYSIS_TEMPLATES.reduce<Record<string, typeof ANALYSIS_TEMPLATES>>((acc, template) => {
    acc[template.category] ??= [];
    acc[template.category].push(template);
    return acc;
  }, {});

  const isEmpty = messages.length === 0;

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
      {/* Messages */}
      <div className={cn("flex-1 overflow-y-auto py-6 px-4", !isEmpty && "space-y-5")}>
        {isEmpty && contextSnapshot && (
          <ContextSnapshot context={contextSnapshot} />
        )}
        {isEmpty && !contextSnapshot && (
           <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center">
             <div className="w-14 h-14 rounded-2xl bg-[--primary]/10 flex items-center justify-center">
               <Bot size={28} className="text-[--primary]" />
             </div>
             <div>
               <p className="text-[--foreground] font-medium">RAIL Research Agent</p>
               <p className="text-sm text-[--muted-foreground] mt-1 max-w-sm">
                 Ask me anything about this project.
               </p>
             </div>
           </div>
        )}
        {messages.map(msg => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="shrink-0 px-4 pb-4">
        {isEmpty && (
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
        )}

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
  );
}
