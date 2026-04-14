"use client";

import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";
import { ListChecks, Loader2, Play, CheckCircle2, Circle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ActivePlanSummaryProps {
  projectId: Id<"projects">;
}

export function ActivePlanSummary({ projectId }: ActivePlanSummaryProps) {
  const boards = useQuery(api.taskBoards.listByProject, { projectId });
  const activeBoard = boards?.[0]; // Default to most recent
  
  const boardSummary = useQuery(
    api.taskBoards.getBoardSummary,
    activeBoard ? { boardId: activeBoard._id } : "skip"
  );

  if (!boards || (activeBoard && !boardSummary)) {
    return (
      <div className="flex items-center justify-center p-8 opacity-40">
        <Loader2 className="animate-spin" size={20} />
      </div>
    );
  }

  if (boards.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center space-y-2 opacity-40">
        <ListChecks size={24} />
        <p className="text-[10px] font-bold uppercase">No Active Plan</p>
      </div>
    );
  }

  const tasks = boardSummary?.tasks || [];
  const completedCount = tasks.filter(t => t.status === "done").length;
  const totalCount = tasks.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  
  const runningTask = tasks.find(t => t.status === "running");

  return (
    <div className="p-4 space-y-6 animate-in fade-in duration-500">
      {/* progress card */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[10px] font-black uppercase tracking-widest text-[--muted-foreground]">
            {activeBoard?.title}
          </h3>
          <span className="text-[10px] font-bold text-[--primary]">
            {completedCount} / {totalCount}
          </span>
        </div>
        <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
          <div 
            className="h-full bg-gradient-to-r from-[--primary] to-[--accent] transition-all duration-1000 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Running Task */}
      {runningTask ? (
        <div className="space-y-2">
           <p className="text-[9px] font-black uppercase tracking-widest text-[--muted-foreground] opacity-60">Currently Running</p>
           <div className="p-3 rounded-xl border border-[--primary]/20 bg-[--primary]/5 ring-1 ring-[--primary]/10 flex gap-3">
              <div className="mt-0.5 text-[--primary] animate-pulse">
                <Play size={14} fill="currentColor" />
              </div>
              <div>
                <p className="text-xs font-bold leading-tight">{runningTask.title}</p>
                <p className="text-[10px] text-[--muted-foreground] mt-1 line-clamp-2 leading-relaxed">
                  {runningTask.description}
                </p>
              </div>
           </div>
        </div>
      ) : (
        <div className="p-3 rounded-xl border border-white/5 bg-white/2 flex items-center justify-center gap-2 italic">
          <span className="text-[10px] text-[--muted-foreground]">Waiting for next task...</span>
        </div>
      )}

      {/* Mini task list */}
      <div className="space-y-2">
         <p className="text-[9px] font-black uppercase tracking-widest text-[--muted-foreground] opacity-60">Task Status</p>
         <div className="space-y-1">
            {tasks.slice(0, 5).map(task => (
              <div key={task._id} className="flex items-center gap-2 py-1">
                {task.status === "done" ? (
                  <CheckCircle2 size={12} className="text-green-500/60" />
                ) : task.status === "running" ? (
                  <div className="w-3 h-3 rounded-full border-2 border-[--primary] border-t-transparent animate-spin" />
                ) : (
                  <Circle size={12} className="text-[--muted-foreground] opacity-20" />
                )}
                <span className={cn(
                  "text-[11px] font-medium truncate",
                  task.status === "done" ? "text-[--muted-foreground] line-through opacity-40" : "text-[--foreground]"
                )}>
                  {task.title}
                </span>
              </div>
            ))}
            {totalCount > 5 && (
              <p className="text-[9px] text-[--muted-foreground] opacity-40 pl-5">
                + {totalCount - 5} more tasks
              </p>
            )}
         </div>
      </div>
    </div>
  );
}
