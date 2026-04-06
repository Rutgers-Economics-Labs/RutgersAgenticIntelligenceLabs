"use client";
import { useState, useRef, useEffect } from "react";
import { projectAgent } from "@/lib/api";
import { Sparkles, Send, Loader2, Copy, CornerDownLeft, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";
import { toast } from "sonner";

interface AgentPanelProps {
  projectId: string;
  onInsertCode: (code: string) => void;
}

type Message =
  | { role: "user";      content: string }
  | { role: "assistant"; content: string; codeBlocks: string[] }
  | { role: "thinking";  content: string };

const QUICK_PROMPTS = [
  "Summarize the dataset",
  "Show distribution of all columns",
  "Run OLS regression on the main outcome",
  "Plot a time series for each numeric column",
  "Find missing values and outliers",
];

function extractCodeBlocks(text: string): string[] {
  const blocks: string[] = [];
  const re = /```(?:python)?\n?([\s\S]*?)```/g;
  let m;
  while ((m = re.exec(text)) !== null) blocks.push(m[1].trim());
  return blocks;
}

export function AgentPanel({ projectId, onInsertCode }: AgentPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<boolean>(false);
  const chatIdRef = useRef<Id<"projectChats"> | null>(null);

  const createChat = useMutation(api.projectChats.create);
  const appendMessages = useMutation(api.projectChats.appendMessages);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text: string) => {
    if (!text.trim() || streaming) return;
    setInput("");
    setStreaming(true);
    abortRef.current = false;

    const userMsg: Message = { role: "user", content: text };
    setMessages(prev => [...prev, userMsg]);

    // Build history for the API
    const history = messages
      .filter(m => m.role === "user" || m.role === "assistant")
      .map(m => ({ role: m.role as "user" | "assistant", content: (m as any).content }));

    let assistantText = "";
    setMessages(prev => [...prev, { role: "assistant", content: "", codeBlocks: [] }]);

    try {
      for await (const event of projectAgent.chat(projectId, text, history)) {
        if (abortRef.current) break;
        if (event.type === "text_delta") {
          assistantText += event.content;
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last.role === "assistant") {
              updated[updated.length - 1] = {
                role: "assistant",
                content: assistantText,
                codeBlocks: extractCodeBlocks(assistantText),
              };
            }
            return updated;
          });
        }
      }
    } catch {
      assistantText = "Something went wrong. Make sure the API is running.";
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.role === "assistant") {
          updated[updated.length - 1] = {
            role: "assistant",
            content: assistantText,
            codeBlocks: extractCodeBlocks(assistantText),
          };
        } else {
          updated.push({
            role: "assistant",
            content: assistantText,
            codeBlocks: [],
          });
        }
        return updated;
      });
    } finally {
      setStreaming(false);
      // Persist to projectChats (Convex id — not slug — was incorrectly passed as projectSlug before)
      try {
        const pair = [
          { role: "user" as const, content: text },
          { role: "assistant" as const, content: assistantText || "(no response)" },
        ];
        if (!chatIdRef.current) {
          const { chatId } = await createChat({
            projectId: projectId as Id<"projects">,
            title: text.slice(0, 60),
            messages: pair,
          });
          chatIdRef.current = chatId;
        } else {
          await appendMessages({ chatId: chatIdRef.current, messages: pair });
        }
      } catch (e) {
        console.error("[AgentPanel] Failed to save chat to Convex:", e);
        toast.error("Could not save this chat to history. Check your connection.");
      }
    }
  };

  return (
    <div className="flex flex-col h-full bg-[--card]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[--border] flex items-center gap-2">
        <Sparkles size={14} className="text-[--primary]" />
        <span className="text-xs font-semibold text-[--foreground]">AI Code Assistant</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar">
        {messages.length === 0 && (
          <div className="space-y-2 pt-2">
            <p className="text-[11px] text-[--muted-foreground] text-center">
              Describe what you want to analyze
            </p>
            {QUICK_PROMPTS.map(p => (
              <button
                key={p}
                onClick={() => send(p)}
                className="w-full text-left text-[11px] px-3 py-2 rounded-lg border border-[--border] text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted]/30 transition-colors"
              >
                {p}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={cn("text-[12px]", msg.role === "user" && "flex justify-end")}>
            {msg.role === "user" ? (
              <div className="max-w-[90%] px-3 py-2 rounded-xl bg-[--primary] text-white text-[11px]">
                {msg.content}
              </div>
            ) : (
              <div className="space-y-2">
                {/* Render text with code blocks */}
                {renderMessageContent(msg.content, (msg as any).codeBlocks, onInsertCode)}
              </div>
            )}
          </div>
        ))}

        {streaming && messages[messages.length - 1]?.role !== "assistant" && (
          <div className="flex items-center gap-2 text-[11px] text-[--muted-foreground]">
            <Loader2 size={12} className="animate-spin text-[--primary]" />
            Thinking...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-[--border]">
        <div className="flex items-end gap-2 rounded-lg border border-[--border] bg-[--muted]/20 px-3 py-2 focus-within:border-[--primary]/50 transition-colors">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
            }}
            placeholder="Describe your analysis…"
            rows={2}
            className="flex-1 bg-transparent text-[12px] text-[--foreground] placeholder:text-[--muted-foreground] resize-none focus:outline-none"
          />
          <button
            onClick={() => send(input)}
            disabled={streaming || !input.trim()}
            className="shrink-0 p-1.5 rounded-lg bg-[--primary] text-white hover:bg-[--primary]/90 disabled:opacity-40 transition-colors"
          >
            {streaming ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
          </button>
        </div>
        <p className="text-[10px] text-[--muted-foreground] mt-1.5 text-center">
          <CornerDownLeft size={9} className="inline mr-0.5" />Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}

function renderMessageContent(
  text: string,
  codeBlocks: string[],
  onInsert: (code: string) => void,
) {
  if (!text) return <Loader2 size={12} className="animate-spin text-[--primary] mt-1" />;

  let codeIdx = 0;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        p: ({ children }) => (
          <p className="text-[11px] text-[--foreground] leading-relaxed mb-1">{children}</p>
        ),
        h1: ({ children }) => <h1 className="text-sm font-bold text-[--foreground] mt-2 mb-1">{children}</h1>,
        h2: ({ children }) => <h2 className="text-[12px] font-bold text-[--foreground] mt-2 mb-1">{children}</h2>,
        h3: ({ children }) => <h3 className="text-[11px] font-semibold text-[--foreground] mt-1.5 mb-0.5">{children}</h3>,
        ul: ({ children }) => <ul className="text-[11px] text-[--foreground] list-disc list-inside space-y-0.5 mb-1">{children}</ul>,
        ol: ({ children }) => <ol className="text-[11px] text-[--foreground] list-decimal list-inside space-y-0.5 mb-1">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-[--foreground]">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-[--primary]/40 pl-2 my-1 text-[--muted-foreground] italic text-[11px]">{children}</blockquote>
        ),
        code: ({ className, children, ...props }) => {
          const isBlock = className?.includes("language-");
          if (isBlock) {
            const code = codeBlocks[codeIdx] ?? String(children).trim();
            const currentIdx = codeIdx++;
            const codeStr = codeBlocks[currentIdx] ?? String(children).trim();
            return (
              <div className="rounded-lg overflow-hidden border border-[--border] my-1">
                <div className="flex items-center justify-between px-3 py-1.5 bg-[--muted]/30 border-b border-[--border]">
                  <span className="text-[10px] font-mono text-[--muted-foreground]">
                    {className?.replace("language-", "") || "code"}
                  </span>
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => navigator.clipboard.writeText(codeStr)}
                      className="text-[10px] text-[--muted-foreground] hover:text-[--foreground] flex items-center gap-1 transition-colors"
                    >
                      <Copy size={10} /> Copy
                    </button>
                    <button
                      onClick={() => onInsert(codeStr)}
                      className="text-[10px] text-[--primary] hover:text-[--primary]/80 flex items-center gap-1 font-semibold transition-colors"
                    >
                      <CornerDownLeft size={10} /> Insert
                    </button>
                  </div>
                </div>
                <pre className="p-3 text-[11px] font-mono text-[--foreground] bg-[--muted]/40 overflow-x-auto">
                  <code>{codeStr}</code>
                </pre>
              </div>
            );
          }
          return (
            <code className="text-[10px] font-mono bg-[--muted]/50 text-[--primary] px-1 py-0.5 rounded" {...props}>
              {children}
            </code>
          );
        },
        pre: ({ children }) => <>{children}</>,
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
