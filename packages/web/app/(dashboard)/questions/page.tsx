"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import { questions as questionsApi, projectAgent } from "@/lib/api";
import { ToolResult } from "@/components/jobs/ToolResult";
import {
  Send, Loader2, AlertTriangle, Plus, Database,
  Sparkles, BookOpen, BarChart2, ChevronRight, History,
  X, CheckCircle2, Clock, Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

type AnswerBlock =
  | { kind: "text";           text: string }
  | { kind: "tool_result";    name: string; result: unknown }
  | { kind: "scope_exceeded"; explanation: string; missing: string; sources: string[] }
  | { kind: "thinking";       name: string };

type QAEntry = {
  id: string;
  question: string;
  blocks: AnswerBlock[];
  streaming: boolean;
};

const EXAMPLES = [
  "What is the unemployment rate by state?",
  "Which counties have the highest GDP growth?",
  "Show me the trend in household income over the past decade",
  "Compare NJ vs NY economic indicators",
  "Which municipalities have the highest population density?",
];

// ─── Data Source Agent Modal ─────────────────────────────────────────────────

function DataSourceAgentModal({
  projectId,
  sources,
  missing,
  onClose,
}: {
  projectId: string;
  sources: string[];
  missing: string;
  onClose: () => void;
}) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const job = useQuery(api.executions.get, jobId ? { jobId } : "skip");

  const launch = async () => {
    setLaunching(true);
    setError(null);
    try {
      const goal = [
        `The user needs the following data added to this project: ${missing}`,
        sources.length > 0
          ? `Suggested registry sources: ${sources.join(", ")}.`
          : "",
        "Please:",
        "1. Search the data registry to find the best available datasets.",
        "2. For each relevant dataset, create a YAML API config file that will hydrate this data into the project ontology.",
        "3. Link the new config(s) to this project.",
        "4. Provide a summary of what you added and next steps.",
      ].filter(Boolean).join(" ");
      const { jobId: id } = await projectAgent.runTask(projectId, goal);
      setJobId(id);
    } catch (e: any) {
      setError(e.message || "Failed to start agent");
    } finally {
      setLaunching(false);
    }
  };

  const status = job?.status;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-2xl border border-[--border] bg-[--card] shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-[--border] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-[--primary]" />
            <span className="font-semibold text-[--foreground]">Research & Add Data Sources</span>
          </div>
          <button onClick={onClose} className="p-1 text-[--muted-foreground] hover:text-[--foreground]">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* What's needed */}
          <div className="rounded-lg bg-[--muted]/30 px-4 py-3 text-sm text-[--foreground]">
            <p className="text-xs font-semibold text-[--muted-foreground] mb-1 uppercase tracking-wide">Data needed</p>
            <p>{missing}</p>
          </div>

          {/* Suggested sources */}
          {sources.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-[--muted-foreground] mb-2 uppercase tracking-wide">Starting points</p>
              <div className="flex flex-wrap gap-2">
                {sources.map(s => (
                  <span key={s} className="px-2.5 py-1 rounded-full bg-[--primary]/10 text-[--primary] text-xs font-mono">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Status */}
          {!jobId && !error && (
            <p className="text-sm text-[--muted-foreground]">
              The AI agent will search the data registry, create a YAML config, and link it to this project automatically.
            </p>
          )}

          {error && (
            <div className="flex items-center gap-2 text-sm text-red-500 bg-red-500/10 px-3 py-2 rounded-lg">
              <AlertTriangle size={14} /> {error}
            </div>
          )}

          {jobId && (
            <div className="space-y-2">
              <div className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium",
                status === "running" ? "bg-[--primary]/10 text-[--primary]" :
                status === "success" ? "bg-green-500/10 text-green-500" :
                status === "failed" ? "bg-red-500/10 text-red-500" :
                "bg-[--muted]/30 text-[--muted-foreground]",
              )}>
                {status === "running" && <Loader2 size={14} className="animate-spin" />}
                {status === "success" && <CheckCircle2 size={14} />}
                {status === "failed" && <AlertTriangle size={14} />}
                {(!status || status === "queued") && <Clock size={14} />}
                <span>
                  {status === "running" ? "Agent is researching and configuring data sources…" :
                   status === "success" ? "Done! Check Configs to see what was created." :
                   status === "failed" ? "Agent encountered an error. Check Jobs for details." :
                   "Queued…"}
                </span>
              </div>
              {status === "success" && job?.result?.output && (
                <div className="rounded-lg bg-[--muted]/20 p-3 text-xs text-[--foreground] font-mono max-h-40 overflow-y-auto">
                  {String(job.result.output).slice(0, 800)}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-[--border] flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-[--muted-foreground] hover:text-[--foreground] transition-colors">
            {jobId && status === "success" ? "Close" : "Cancel"}
          </button>
          {!jobId && (
            <button
              onClick={launch}
              disabled={launching}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--primary] text-white text-sm font-semibold hover:bg-[--primary]/90 disabled:opacity-50 transition-colors"
            >
              {launching ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
              Start Research Agent
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── History Panel ────────────────────────────────────────────────────────────

function HistoryPanel({
  projectId,
  onSelect,
  onClose,
}: {
  projectId?: string;
  onSelect: (session: any) => void;
  onClose: () => void;
}) {
  const sessions = useQuery(
    api.questionSessions.list,
    { projectId: projectId as any, limit: 50 }
  );

  return (
    <div className="absolute right-0 top-0 h-full w-80 z-30 flex flex-col border-l border-[--border] bg-[--card] shadow-xl animate-in slide-in-from-right duration-200">
      <div className="px-4 py-3 border-b border-[--border] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <History size={14} className="text-[--primary]" />
          <span className="text-sm font-semibold text-[--foreground]">Past Questions</span>
        </div>
        <button onClick={onClose} className="p-1 text-[--muted-foreground] hover:text-[--foreground]">
          <X size={15} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {!sessions && (
          <div className="flex items-center gap-2 p-4 text-sm text-[--muted-foreground]">
            <Loader2 size={13} className="animate-spin" /> Loading…
          </div>
        )}
        {sessions?.length === 0 && (
          <div className="p-6 text-center text-sm text-[--muted-foreground]">
            <History size={28} className="mx-auto mb-2 opacity-30" />
            No past questions yet
          </div>
        )}
        <div className="divide-y divide-[--border]">
          {sessions?.map((s: any) => (
            <button
              key={s._id}
              onClick={() => { onSelect(s); onClose(); }}
              className="w-full text-left px-4 py-3 hover:bg-[--muted]/20 transition-colors group"
            >
              <p className="text-sm text-[--foreground] font-medium truncate group-hover:text-[--primary] transition-colors">
                {s.question}
              </p>
              <p className="text-[11px] text-[--muted-foreground] mt-0.5">
                {new Date(s.createdAt).toLocaleDateString()} · {s.blocks.length} block{s.blocks.length !== 1 ? "s" : ""}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function QuestionsPage() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("projectId") ?? undefined;

  const project = useQuery(
    api.projects.get,
    projectId ? { slug: projectId as any } : "skip"
  );

  const saveSession = useMutation(api.questionSessions.save);

  const [entries, setEntries] = useState<QAEntry[]>([]);
  const [input, setInput] = useState("");
  const [globalStreaming, setGlobalStreaming] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  // Load a past session from history
  const loadSession = (session: any) => {
    const entry: QAEntry = {
      id: session._id,
      question: session.question,
      blocks: session.blocks.map((b: any) => {
        if (b.kind === "scope_exceeded") {
          return { kind: "scope_exceeded", explanation: b.explanation ?? "", missing: b.missing ?? "", sources: b.sources ?? [] };
        }
        if (b.kind === "tool_result") {
          return { kind: "tool_result", name: b.name ?? "", result: b.result };
        }
        if (b.kind === "thinking") {
          return { kind: "thinking", name: b.name ?? "" };
        }
        return { kind: "text", text: b.text ?? "" };
      }),
      streaming: false,
    };
    setEntries(prev => {
      // Don't duplicate
      if (prev.some(e => e.id === entry.id)) return prev;
      return [...prev, entry];
    });
  };

  const ask = useCallback(async (q: string) => {
    if (!q.trim() || globalStreaming) return;
    setInput("");
    setGlobalStreaming(true);

    const id = crypto.randomUUID();
    const entry: QAEntry = { id, question: q, blocks: [], streaming: true };
    setEntries(prev => [...prev, entry]);

    const updateEntry = (updater: (e: QAEntry) => QAEntry) =>
      setEntries(prev => prev.map(e => e.id === id ? updater(e) : e));

    let currentText = "";

    try {
      for await (const event of questionsApi.ask(q, projectId)) {
        if (event.type === "text_delta") {
          currentText += event.content;
          updateEntry(e => ({
            ...e,
            blocks: [
              ...e.blocks.filter(b => b.kind !== "text"),
              { kind: "text", text: currentText },
            ],
          }));
        } else if (event.type === "tool_call") {
          updateEntry(e => ({
            ...e,
            blocks: [...e.blocks, { kind: "thinking", name: event.name }],
          }));
        } else if (event.type === "tool_result") {
          const result = event.result as any;
          if (result?.__scope_exceeded__) {
            updateEntry(e => ({
              ...e,
              blocks: [
                ...e.blocks.filter(b => b.kind !== "thinking"),
                {
                  kind: "scope_exceeded",
                  explanation: result.explanation,
                  missing: result.missing_data,
                  sources: result.suggested_sources ?? [],
                },
              ],
            }));
          } else if (
            event.name === "run_sql" || event.name === "execute_python" ||
            event.name === "query_ontology"
          ) {
            updateEntry(e => ({
              ...e,
              blocks: [
                ...e.blocks.filter(b => b.kind !== "thinking"),
                { kind: "tool_result", name: event.name, result: event.result },
              ],
            }));
          } else {
            updateEntry(e => ({
              ...e,
              blocks: e.blocks.filter(b => b.kind !== "thinking"),
            }));
          }
        } else if (event.type === "done") {
          updateEntry(e => ({ ...e, streaming: false }));
        }
      }
    } catch (err: any) {
      updateEntry(e => ({
        ...e,
        streaming: false,
        blocks: [...e.blocks, { kind: "text", text: `Error: ${err.message}` }],
      }));
    } finally {
      updateEntry(e => ({ ...e, streaming: false }));
      setGlobalStreaming(false);
      // Persist completed session
      setEntries(prev => {
        const finished = prev.find(e => e.id === id);
        if (finished && finished.blocks.length > 0) {
          saveSession({
            projectId: projectId as any,
            question: q,
            blocks: finished.blocks.map(b => ({
              kind: b.kind,
              text: b.kind === "text" ? (b as any).text : undefined,
              name: b.kind === "tool_result" || b.kind === "thinking" ? (b as any).name : undefined,
              result: b.kind === "tool_result" ? (b as any).result : undefined,
              explanation: b.kind === "scope_exceeded" ? (b as any).explanation : undefined,
              missing: b.kind === "scope_exceeded" ? (b as any).missing : undefined,
              sources: b.kind === "scope_exceeded" ? (b as any).sources : undefined,
            })),
          }).catch(() => {/* ignore */});
        }
        return prev;
      });
    }
  }, [projectId, globalStreaming, saveSession]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-56px)] max-w-4xl mx-auto w-full px-4 relative">
      {/* Header */}
      <div className="py-6 border-b border-[--border] flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-bold text-[--foreground] flex items-center gap-2">
            <BookOpen size={20} className="text-[--primary]" />
            Ask a Question
          </h1>
          <p className="text-xs text-[--muted-foreground] mt-0.5">
            Natural language queries over your knowledge graph
            {project && <span className="ml-1 text-[--primary]">· {project.name}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowHistory(v => !v)}
            className={cn(
              "flex items-center gap-1.5 text-xs border px-3 py-1.5 rounded-lg transition-colors",
              showHistory
                ? "border-[--primary]/40 text-[--primary] bg-[--primary]/5"
                : "border-[--border] text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted]/30"
            )}
          >
            <History size={13} /> History
          </button>
          <a
            href={`/context${projectId ? `?projectId=${projectId}` : ""}`}
            className="flex items-center gap-2 text-xs text-[--muted-foreground] hover:text-[--foreground] border border-[--border] px-3 py-1.5 rounded-lg transition-colors hover:bg-[--muted]/30"
          >
            <BookOpen size={13} /> Knowledge Base
          </a>
        </div>
      </div>

      {/* Conversation */}
      <div className="flex-1 overflow-y-auto py-6 space-y-8 custom-scrollbar">
        {entries.length === 0 && (
          <div className="space-y-6">
            <div className="text-center pt-8">
              <div className="w-16 h-16 rounded-2xl bg-[--primary]/10 flex items-center justify-center mx-auto mb-4">
                <Sparkles size={28} className="text-[--primary]" />
              </div>
              <h2 className="text-lg font-semibold text-[--foreground]">Ask anything about your data</h2>
              <p className="text-sm text-[--muted-foreground] mt-1 max-w-md mx-auto">
                I'll check what's available, run the analysis, and explain the results.
                If the data doesn't exist yet, I'll tell you what to add.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl mx-auto">
              {EXAMPLES.map(ex => (
                <button
                  key={ex}
                  onClick={() => ask(ex)}
                  className="text-left text-sm px-4 py-3 rounded-xl border border-[--border] text-[--muted-foreground] hover:text-[--foreground] hover:border-[--primary]/40 hover:bg-[--primary]/5 transition-all"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {entries.map(entry => (
          <div key={entry.id} className="space-y-4">
            {/* Question */}
            <div className="flex justify-end">
              <div className="max-w-[75%] px-4 py-3 rounded-2xl rounded-tr-sm bg-[--primary] text-white text-sm">
                {entry.question}
              </div>
            </div>

            {/* Answer blocks */}
            <div className="space-y-3 pl-2">
              {entry.blocks.map((block, i) => (
                <AnswerBlockView key={i} block={block} projectId={projectId} />
              ))}
              {entry.streaming && entry.blocks.length === 0 && (
                <div className="flex items-center gap-2 text-sm text-[--muted-foreground]">
                  <Loader2 size={14} className="animate-spin text-[--primary]" />
                  Analyzing your question...
                </div>
              )}
            </div>
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 py-4 border-t border-[--border]">
        <div className={cn(
          "flex items-end gap-3 rounded-2xl border px-4 py-3 transition-colors",
          "border-[--border] bg-[--card] focus-within:border-[--primary]/50",
        )}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={projectId ? "Ask a question about your data…" : "Select a project first, then ask a question…"}
            rows={2}
            className="flex-1 bg-transparent text-sm text-[--foreground] placeholder:text-[--muted-foreground] resize-none focus:outline-none"
          />
          <button
            onClick={() => ask(input)}
            disabled={globalStreaming || !input.trim()}
            className="shrink-0 p-2.5 rounded-xl bg-[--primary] text-white hover:bg-[--primary]/90 disabled:opacity-40 transition-colors"
          >
            {globalStreaming
              ? <Loader2 size={16} className="animate-spin" />
              : <Send size={16} />}
          </button>
        </div>
        <p className="text-[10px] text-[--muted-foreground] text-center mt-2">
          Enter to send · Shift+Enter for newline
        </p>
      </div>

      {/* History slide-over panel */}
      {showHistory && (
        <HistoryPanel
          projectId={projectId}
          onSelect={loadSession}
          onClose={() => setShowHistory(false)}
        />
      )}
    </div>
  );
}

// ─── Answer block renderer ────────────────────────────────────────────────────

function AnswerBlockView({ block, projectId }: { block: AnswerBlock; projectId?: string }) {
  const [agentModal, setAgentModal] = useState<{ sources: string[]; missing: string } | null>(null);

  if (block.kind === "thinking") {
    return (
      <div className="flex items-center gap-2 text-xs text-[--muted-foreground] italic">
        <Loader2 size={11} className="animate-spin text-[--primary]" />
        Running <span className="font-mono">{block.name}</span>…
      </div>
    );
  }

  if (block.kind === "text" && block.text) {
    return (
      <div className="text-sm text-[--foreground] leading-relaxed prose prose-sm dark:prose-invert max-w-none
        [&_p]:mb-2 [&_p]:text-[--foreground] [&_p]:leading-relaxed
        [&_h1]:text-lg [&_h1]:font-bold [&_h1]:text-[--foreground] [&_h1]:mt-4 [&_h1]:mb-2
        [&_h2]:text-base [&_h2]:font-bold [&_h2]:text-[--foreground] [&_h2]:mt-3 [&_h2]:mb-1.5
        [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-[--foreground] [&_h3]:mt-2 [&_h3]:mb-1
        [&_ul]:list-disc [&_ul]:list-inside [&_ul]:space-y-1 [&_ul]:mb-2 [&_ul]:text-[--foreground]
        [&_ol]:list-decimal [&_ol]:list-inside [&_ol]:space-y-1 [&_ol]:mb-2 [&_ol]:text-[--foreground]
        [&_li]:text-[--foreground] [&_li]:leading-relaxed
        [&_strong]:font-semibold [&_strong]:text-[--foreground]
        [&_code]:text-xs [&_code]:font-mono [&_code]:bg-[--muted]/50 [&_code]:text-[--primary] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded
        [&_pre]:bg-[--muted]/20 [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:overflow-x-auto [&_pre]:my-2
        [&_pre_code]:bg-transparent [&_pre_code]:text-[--foreground] [&_pre_code]:px-0
        [&_blockquote]:border-l-2 [&_blockquote]:border-[--primary]/40 [&_blockquote]:pl-3 [&_blockquote]:my-2 [&_blockquote]:text-[--muted-foreground] [&_blockquote]:italic
        [&_table]:w-full [&_table]:border-collapse [&_table]:my-2
        [&_th]:border [&_th]:border-[--border] [&_th]:px-3 [&_th]:py-1.5 [&_th]:bg-[--muted]/30 [&_th]:text-xs [&_th]:font-semibold [&_th]:text-left
        [&_td]:border [&_td]:border-[--border] [&_td]:px-3 [&_td]:py-1.5 [&_td]:text-xs [&_td]:text-[--foreground]
      ">
        <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
          {block.text}
        </ReactMarkdown>
      </div>
    );
  }

  if (block.kind === "tool_result") {
    return (
      <div className="rounded-xl overflow-hidden border border-[--border]">
        <div className="px-3 py-2 bg-[--muted]/20 border-b border-[--border] flex items-center gap-2">
          <BarChart2 size={12} className="text-[--primary]" />
          <span className="text-[11px] font-semibold text-[--muted-foreground] uppercase tracking-wide">
            {block.name === "execute_python" ? "Analysis Results" : "Query Results"}
          </span>
        </div>
        <div className="p-4">
          <ToolResult name={block.name} result={block.result as any} />
        </div>
      </div>
    );
  }

  if (block.kind === "scope_exceeded") {
    return (
      <>
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 overflow-hidden">
          <div className="px-4 py-3 border-b border-amber-500/20 flex items-center gap-2">
            <AlertTriangle size={14} className="text-amber-500" />
            <span className="text-sm font-semibold text-amber-600 dark:text-amber-400">
              Data not available in current ontology
            </span>
          </div>
          <div className="p-4 space-y-3">
            <p className="text-sm text-[--foreground]">{block.explanation}</p>
            <div className="rounded-lg bg-[--muted]/30 px-3 py-2">
              <p className="text-xs font-semibold text-[--muted-foreground] mb-1">What's needed:</p>
              <p className="text-sm text-[--foreground]">{block.missing}</p>
            </div>
            {block.sources.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-[--muted-foreground] mb-2">Suggested data sources:</p>
                <div className="flex flex-wrap gap-2">
                  {block.sources.map(s => (
                    <span key={s} className="px-2.5 py-1 rounded-full bg-[--primary]/10 text-[--primary] text-xs font-mono">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {projectId && (
              <button
                onClick={() => setAgentModal({ sources: block.sources, missing: block.missing })}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-[--primary] text-white text-xs font-semibold hover:bg-[--primary]/90 transition-colors mt-1"
              >
                <Zap size={12} /> Research & Add Data Sources
                <ChevronRight size={12} />
              </button>
            )}
          </div>
        </div>

        {agentModal && projectId && (
          <DataSourceAgentModal
            projectId={projectId}
            sources={agentModal.sources}
            missing={agentModal.missing}
            onClose={() => setAgentModal(null)}
          />
        )}
      </>
    );
  }

  return null;
}
