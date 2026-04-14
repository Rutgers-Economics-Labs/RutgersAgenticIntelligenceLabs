"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";
import { cn } from "@/lib/utils";
import { Send, Sparkles, User, Loader2, HelpCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface PlannerChatProps {
  projectId: Id<"projects">;
}

export function PlannerChat({ projectId }: PlannerChatProps) {
  const messages = useQuery(api.plannerMessages.listLatestByProject, { projectId });
  const appendMessage = useMutation(api.plannerMessages.append);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isSending) return;
    setIsSending(true);
    try {
      await appendMessage({
        projectId,
        threadId: "planner",
        role: "user",
        content: input.trim(),
        messageType: "chat",
      });
      setInput("");
    } catch (err) {
      console.error("Failed to send message:", err);
    } finally {
      setIsSending(false);
    }
  };

  const sortedMessages = [...(messages || [])].sort((a, b) => a.createdAt - b.createdAt);

  return (
    <div className="flex flex-col h-full">
      {/* Message List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
        {!messages && (
          <div className="flex items-center justify-center h-full opacity-50">
            <Loader2 className="animate-spin" size={20} />
          </div>
        )}
        
        {messages?.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-2 opacity-40">
            <Sparkles size={32} />
            <p className="text-xs font-medium uppercase tracking-widest">Planner Thread Initialized</p>
            <p className="text-[10px] max-w-[200px]">Send a message to start planning your research project.</p>
          </div>
        )}

        {sortedMessages.map((msg) => {
          const isAssistant = msg.role === "assistant" || msg.role === "system";
          const isQuestion = msg.messageType === "question";

          return (
            <div
              key={msg._id}
              className={cn(
                "flex flex-col gap-1.5 max-w-[90%]",
                isAssistant ? "items-start" : "items-end ml-auto"
              )}
            >
              <div className="flex items-center gap-1.5 opacity-40">
                {isAssistant ? (
                  <>
                    <Sparkles size={10} className="text-[--primary]" />
                    <span className="text-[9px] font-bold uppercase tracking-tighter">Planner</span>
                  </>
                ) : (
                  <>
                    <span className="text-[9px] font-bold uppercase tracking-tighter">You</span>
                    <User size={10} />
                  </>
                )}
              </div>
              
              <div
                className={cn(
                  "px-3 py-2 rounded-2xl text-xs leading-relaxed shadow-sm",
                  isAssistant 
                    ? cn(
                        "bg-white/5 border border-white/10 rounded-tl-none",
                        isQuestion && "border-[--primary]/30 bg-[--primary]/5 ring-1 ring-[--primary]/10"
                      )
                    : "bg-[--primary] text-[--primary-foreground] rounded-tr-none"
                )}
              >
                {isQuestion && (
                  <div className="flex items-center gap-1.5 mb-2 text-[10px] font-bold uppercase tracking-widest text-[--primary]">
                    <HelpCircle size={12} />
                    Agent Question
                  </div>
                )}
                <div className="prose prose-sm prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-black/40 prose-pre:border prose-pre:border-white/5 font-medium">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              </div>
              <span className="text-[8px] opacity-20 px-1">
                {new Date(msg.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-[--border] bg-black/20">
        <div className="relative group">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Message the planner..."
            className="w-full bg-white/5 border border-white/10 rounded-xl py-3 px-4 pr-12 text-xs focus:outline-none focus:ring-1 focus:ring-[--primary]/40 transition-all resize-none max-h-32 custom-scrollbar"
            rows={1}
            style={{ fieldSizing: "content" } as any}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isSending}
            className={cn(
              "absolute right-2 bottom-2 p-2 rounded-lg transition-all",
              input.trim() && !isSending
                ? "bg-[--primary] text-[--primary-foreground] shadow-lg shadow-[--primary]/20"
                : "text-[--muted-foreground] opacity-40"
            )}
          >
            {isSending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  );
}
