"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import { questions as questionsApi } from "@/lib/api";
import { ToolResult } from "@/components/jobs/ToolResult";
import {
  Send, Loader2, AlertTriangle, Plus, Database,
  Sparkles, BookOpen, BarChart2, ChevronRight,
} from "lucide-react";
import Link from "next/link";
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
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

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
          // Check for scope exceeded sentinel
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
            // Remove thinking indicator for other tools
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
          }).catch(() => {/* ignore persistence errors */});
        }
        return prev;
      });
    }
  }, [projectId, globalStreaming, saveSession]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-56px)] max-w-4xl mx-auto w-full px-4">
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
        <Link
          href={`/context${projectId ? `?projectId=${projectId}` : ""}`}
          className="flex items-center gap-2 text-xs text-[--muted-foreground] hover:text-[--foreground] border border-[--border] px-3 py-1.5 rounded-lg transition-colors hover:bg-[--muted]/30"
        >
          <BookOpen size={13} /> Knowledge Base
        </Link>
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
    </div>
  );
}

function AnswerBlockView({ block, projectId }: { block: AnswerBlock; projectId?: string }) {
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
            <Link
              href={`/projects/${projectId}?tab=data`}
              className="inline-flex items-center gap-2 text-xs font-semibold text-[--primary] hover:text-[--primary]/80 transition-colors mt-1"
            >
              <Plus size={13} /> Add data sources to this project
              <ChevronRight size={12} />
            </Link>
          )}
        </div>
      </div>
    );
  }

  return null;
}
