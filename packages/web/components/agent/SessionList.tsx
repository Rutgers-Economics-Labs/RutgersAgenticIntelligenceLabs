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
    <aside className="w-64 border-r border-[--border] bg-[--card] flex flex-col shrink-0 h-full hidden md:flex">
      <div className="p-4 border-b border-[--border] shrink-0">
        <button
          onClick={onNew}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-[--primary] px-4 py-2 text-sm font-medium text-[--primary-foreground] hover:opacity-90 transition-opacity"
        >
          <Plus size={16} />
          New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {sessions === undefined ? (
          <p className="text-xs text-[--muted-foreground] p-2">Loading sessions...</p>
        ) : sessions.length === 0 ? (
          <p className="text-xs text-[--muted-foreground] p-2 text-center mt-4">No past conversations.</p>
        ) : (
          sessions.map((session) => (
            <button
              key={session._id}
              onClick={() => onSelect(session._id)}
              className={cn(
                "w-full flex flex-col items-start gap-1 p-3 rounded-lg text-left transition-colors",
                activeSessionId === session._id
                  ? "bg-[--primary]/10 border border-[--primary]/20"
                  : "hover:bg-[--muted] border border-transparent"
              )}
            >
              <div className="flex items-center gap-2 w-full text-[--foreground]">
                <MessageSquare size={14} className="shrink-0 text-[--muted-foreground]" />
                <span className="text-sm font-medium truncate flex-1">{session.title || "New Conversation"}</span>
              </div>
              <div className="flex items-center justify-between w-full mt-1">
                <span className="text-[10px] text-[--muted-foreground]">
                  {session.messages?.filter((m: any) => m.role === "user" || m.role === "assistant").length || 0} msgs
                </span>
                <span className="text-[10px] text-[--muted-foreground]">
                  {timeAgo(session.updatedAt)}
                </span>
              </div>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
