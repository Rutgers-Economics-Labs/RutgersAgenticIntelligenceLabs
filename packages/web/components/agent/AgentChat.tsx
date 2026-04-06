"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useMutation, useQuery } from "convex/react";
import { api as convexApi } from "@/convex/_generated/api";
import { agent, ModelInfo, sql } from "@/lib/api";
import { ANALYSIS_TEMPLATES } from "@/lib/analysis-templates";
import { Bot, User, Send, ChevronDown, ChevronRight, Code2, Loader2, Plus, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { ToolResult } from "@/components/jobs/ToolResult";
import { Id } from "@/convex/_generated/dataModel";
import { ContextSnapshot } from "./ContextSnapshot";
import { toast } from "sonner";

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
  describe_database: "Inspecting database",
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
    <div className={cn("flex gap-5 px-6 py-2 group transition-all duration-500", isUser ? "flex-reverse items-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-1 shrink-0 w-10 h-10 rounded-2xl bg-[--primary]/10 flex items-center justify-center border border-[--primary]/20 shadow-inner group-hover:scale-110 transition-transform">
          <Sparkles size={18} className="text-[--primary]" />
        </div>
      )}
      <div className={cn("max-w-[85%] space-y-3", isUser ? "ml-auto items-end" : "items-start")}>
        {/* Tool calls */}
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="space-y-2 w-full min-w-[320px]">
            {msg.toolCalls.map(tc => (
              <ToolCallCard key={tc.id} tc={tc} />
            ))}
          </div>
        )}
        {/* Text content */}
        {(msg.content || msg.streaming) && (
          <div
            className={cn(
               "relative px-6 py-4 text-[14px] leading-relaxed shadow-sm transition-all duration-300",
               isUser
                 ? "bg-[--primary] text-[--primary-foreground] rounded-[24px] rounded-tr-none shadow-[--primary]/10"
                 : "bg-[--card]/40 backdrop-blur-md border border-[--border] text-[--foreground] rounded-[24px] rounded-tl-none"
            )}
          >
            {isUser ? (
              <p className="whitespace-pre-wrap font-medium">{msg.content}</p>
            ) : (
              <div className="prose prose-sm prose-invert max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkMath]}
                  rehypePlugins={[rehypeKatex]}
                  components={{
                    code({ className, children, ...props }) {
                      const isBlock = className?.startsWith("language-");
                      return isBlock ? (
                        <div className="relative group/code my-4">
                          <pre className="overflow-x-auto rounded-xl bg-black/40 p-4 font-mono text-[11px] border border-white/5 custom-scrollbar">
                            <code className={className} {...props}>{children}</code>
                          </pre>
                        </div>
                      ) : (
                        <code className="bg-[--primary]/10 text-[--primary] rounded-md px-1.5 py-0.5 text-[11px] font-bold font-mono" {...props}>
                          {children}
                        </code>
                      );
                    },
                    a({ href, children }) {
                      return <a href={href} target="_blank" rel="noopener noreferrer" className="text-[--primary] font-bold underline decoration-[--primary]/30 underline-offset-4 hover:decoration-[--primary] transition-all">{children}</a>;
                    },
                    ul({ children }) { return <ul className="list-disc pl-5 space-y-2 my-4">{children}</ul>; },
                    ol({ children }) { return <ol className="list-decimal pl-5 space-y-2 my-4">{children}</ol>; },
                    h1({ children }) { return <h1 className="text-xl font-black uppercase tracking-widest mt-8 mb-4 text-[--foreground] border-b border-[--border] pb-2">{children}</h1>; },
                    h2({ children }) { return <h2 className="text-sm font-black uppercase tracking-widest mt-6 mb-3 text-[--primary]">{children}</h2>; },
                    h3({ children }) { return <h3 className="text-sm font-bold mt-4 mb-2">{children}</h3>; },
                    blockquote({ children }) { return <blockquote className="border-l-4 border-[--primary]/40 pl-4 py-1 italic bg-[--primary]/5 rounded-r-lg my-4 text-[--muted-foreground]">{children}</blockquote>; },
                    table({ children }) { return <div className="overflow-x-auto my-4 rounded-xl border border-[--border] bg-black/20"><table className="w-full text-[11px] border-collapse">{children}</table></div>; },
                    th({ children }) { return <th className="px-4 py-2.5 text-left bg-white/5 text-[--muted-foreground] font-black uppercase tracking-tighter text-[10px]">{children}</th>; },
                    td({ children }) { return <td className="border-t border-[--border] px-4 py-2.5">{children}</td>; },
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              </div>
            )}
            {msg.streaming && (
              <span className="inline-block w-2 h-5 ml-1 bg-[--primary] rounded-sm animate-pulse align-middle" />
            )}
          </div>
        )}
      </div>
      {isUser && (
        <div className="mt-1 shrink-0 w-10 h-10 rounded-2xl bg-[--muted]/60 flex items-center justify-center border border-[--border] group-hover:scale-110 transition-transform">
          <User size={18} className="text-[--muted-foreground]" />
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
    let turnPersisted = false;

    const persistFallback = async (assistantContent: string) => {
      if (!activeSessionId || turnPersisted) return;
      turnPersisted = true;
      try {
        await appendMessages({
          sessionId: activeSessionId,
          messages: [
            { role: "user", content: text },
            { role: "assistant", content: assistantContent },
          ],
        });
      } catch (e) {
        console.error("[AgentChat] Failed to persist messages:", e);
        toast.error("Could not save this turn to your session history.");
      }
    };

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
            turnPersisted = true;

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
          const errBody = `Error: ${event.message}`;
          onMessages(prev => prev.map(m =>
            m.id === asstId
              ? { ...m, content: errBody, streaming: false }
              : m
          ));
          await persistFallback(errBody);
        }
      }
    } catch (err) {
      const errBody = `Error: ${err instanceof Error ? err.message : String(err)}`;
      onMessages(prev => prev.map(m =>
        m.id === asstId
          ? { ...m, content: errBody, streaming: false }
          : m
      ));
      await persistFallback(errBody);
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
      <div className="shrink-0 px-6 pb-6 relative">
        <div className="max-w-4xl mx-auto">
          {isEmpty && (
            <div className="mb-6 rounded-[28px] border border-[--border] bg-[--card]/40 backdrop-blur-xl shadow-2xl overflow-hidden transition-all duration-500">
              <button
                onClick={() => setTemplatesOpen((value) => !value)}
                className="flex w-full items-center justify-between px-8 py-5 text-left hover:bg-[--muted]/30 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-xl bg-[--primary]/10 flex items-center justify-center text-[--primary] border border-[--primary]/20">
                    <Code2 size={20} />
                  </div>
                  <div>
                    <p className="text-xs font-black uppercase tracking-widest text-[--foreground]">Research Templates</p>
                    <p className="text-[10px] uppercase font-bold tracking-tighter text-[--muted-foreground] opacity-60">Schema-aware analysis shortcuts</p>
                  </div>
                </div>
                {templatesOpen ? <ChevronDown size={20} className="text-[--muted-foreground]" /> : <ChevronRight size={20} className="text-[--muted-foreground]" />}
              </button>
              {templatesOpen && (
                <div className="border-t border-[--border] px-8 py-6 space-y-6 animate-in fade-in slide-in-from-top-4 duration-300">
                  {Object.entries(groupedTemplates).map(([category, templates]) => (
                    <div key={category} className="space-y-3">
                      <p className="text-[9px] font-black uppercase tracking-widest text-[--primary] opacity-80 pl-1">{category}</p>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {(templates ?? []).map((template) => (
                          <button
                            key={template.id}
                            onClick={() => applyTemplate(template.prompt)}
                            className="group relative rounded-2xl border border-[--border] bg-[--background]/40 p-4 text-left hover:border-[--primary]/40 hover:bg-[--primary]/5 transition-all duration-300"
                          >
                            <div className="flex items-center gap-3">
                              <div className="h-6 w-6 rounded-lg bg-[--muted]/60 flex items-center justify-center group-hover:bg-[--primary]/20 transition-colors">
                                 <Plus size={12} className="text-[--muted-foreground] group-hover:text-[--primary]" />
                              </div>
                              <p className="text-[12px] font-bold text-[--foreground] tracking-tight">{template.label}</p>
                            </div>
                            <p className="mt-1.5 text-[10px] leading-relaxed text-[--muted-foreground] opacity-80 font-medium">{template.description}</p>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="relative group">
            {/* Ambient focus glow */}
            <div className="absolute -inset-1 bg-gradient-to-r from-[--primary]/20 to-[--accent]/20 rounded-[32px] blur-xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
            
            <div className="relative flex items-end gap-3 rounded-[28px] border border-[--border] bg-[--background]/80 backdrop-blur-xl p-3 shadow-2xl focus-within:border-[--primary]/40 focus-within:ring-4 focus-within:ring-[--primary]/5 transition-all duration-300">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a research question..."
                rows={1}
                disabled={loading}
                className="flex-1 resize-none bg-transparent px-4 py-3 text-sm font-medium text-[--foreground] placeholder:text-[--muted-foreground]/40 focus:outline-none max-h-48 overflow-y-auto custom-scrollbar"
                style={{ fieldSizing: "content" } as React.CSSProperties}
              />
              <button
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                className={cn(
                  "shrink-0 flex items-center justify-center w-12 h-12 rounded-[22px] transition-all duration-300 relative overflow-hidden",
                  loading || !input.trim()
                    ? "bg-[--muted]/40 text-[--muted-foreground]/30 cursor-not-allowed"
                    : "bg-[--primary] text-[--primary-foreground] hover:scale-105 active:scale-95 shadow-lg shadow-[--primary]/20 hover:shadow-[--primary]/40"
                )}
              >
                {loading ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <Send size={18} />
                )}
              </button>
            </div>
          </div>
          
          <div className="mt-4 flex items-center justify-center gap-4 text-[9px] font-black uppercase tracking-[0.2em] text-[--muted-foreground] opacity-40">
            <span>Ontology Aware</span>
            <div className="h-1 w-1 rounded-full bg-[--muted-foreground]" />
            <span>SQL Processor</span>
            <div className="h-1 w-1 rounded-full bg-[--muted-foreground]" />
            <span>Python Runtime</span>
          </div>
        </div>
      </div>
    </div>
  );
}
