import { useQuery } from "convex/react";
import { api as convexApi } from "@/convex/_generated/api";
import { Plus, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

function timeAgo(ms: number) {
  const diff = Math.floor((Date.now() - ms) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

interface SessionListProps {
  projectSlug: string;
  activeSessionId?: string;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
}

export function SessionList({ projectSlug, activeSessionId, onSelect, onNew }: SessionListProps) {
  const sessions = useQuery(convexApi.agent.listByProject, { projectSlug });

  return (
    <aside className="w-72 border-r border-[--border] bg-[--background]/40 backdrop-blur-xl flex flex-col shrink-0 h-full hidden md:flex relative z-10 transition-all duration-500">
      <div className="p-6 shrink-0 relative">
        <button
          onClick={onNew}
          className="group relative flex w-full items-center justify-center gap-2.5 rounded-2xl bg-[--primary] px-6 py-3.5 text-xs font-black uppercase tracking-widest text-[--primary-foreground] shadow-xl shadow-[--primary]/20 hover:scale-[1.02] active:scale-[0.98] transition-all duration-300 overflow-hidden"
        >
          <div className="absolute inset-0 bg-white/10 translate-y-full group-hover:translate-y-0 transition-transform duration-500" />
          <Plus size={16} className="relative z-10" />
          <span className="relative z-10">New Research Chat</span>
        </button>
      </div>

      <div className="p-4 pt-0">
        <div className="h-px w-full bg-gradient-to-r from-transparent via-[--border] to-transparent opacity-50 mb-4" />
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-6 space-y-2 custom-scrollbar">
        {sessions === undefined ? (
          <div className="space-y-4 p-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 rounded-xl bg-[--muted]/20 animate-pulse" />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-center mt-10 space-y-3 opacity-30">
            <div className="w-12 h-12 rounded-2xl bg-[--muted] flex items-center justify-center">
              <MessageSquare size={20} />
            </div>
            <p className="text-[10px] uppercase font-black tracking-widest leading-loose">Initialize<br/>Conversation</p>
          </div>
        ) : (
          sessions.map((session) => {
            const isActive = activeSessionId === session._id;
            return (
              <button
                key={session._id}
                onClick={() => onSelect(session._id)}
                className={cn(
                  "w-full flex flex-col items-start gap-2 p-4 rounded-2xl text-left transition-all duration-300 group relative overflow-hidden",
                  isActive
                    ? "bg-[--primary]/10 border border-[--primary]/20 shadow-lg shadow-[--primary]/5"
                    : "hover:bg-[--muted]/40 border border-transparent"
                )}
              >
                {isActive && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-[--primary] rounded-r-full" />
                )}
                
                <div className="flex items-center gap-3 w-full">
                  <div className={cn(
                    "w-8 h-8 rounded-xl flex items-center justify-center transition-colors shadow-inner",
                    isActive ? "bg-[--primary]/20 text-[--primary]" : "bg-[--muted]/60 text-[--muted-foreground] group-hover:bg-[--muted]"
                  )}>
                    <MessageSquare size={14} />
                  </div>
                  <span className={cn(
                    "text-[12px] font-bold truncate flex-1 tracking-tight",
                    isActive ? "text-[--foreground]" : "text-[--muted-foreground] group-hover:text-[--foreground]"
                  )}>
                    {session.title || "Untitled Research"}
                  </span>
                </div>
                
                <div className="flex items-center justify-between w-full mt-1.5 pl-11">
                  <span className="text-[9px] font-black uppercase tracking-tighter text-[--muted-foreground]/60 group-hover:text-[--muted-foreground] transition-colors">
                    {session.messages?.filter((m: any) => m.role === "user" || m.role === "assistant").length || 0} signals
                  </span>
                  <span className="text-[9px] font-bold text-[--muted-foreground]/40 group-hover:text-[--muted-foreground]/60 transition-colors">
                    {timeAgo(session.updatedAt)}
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}
