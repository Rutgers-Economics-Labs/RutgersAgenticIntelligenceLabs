"use client";

import { useState } from "react";
import { MessageSquare, ListChecks, ShieldAlert, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { PlannerChat } from "./planner/PlannerChat";
import { ActivePlanSummary } from "./planner/ActivePlanSummary";
import { PendingActionsList } from "./planner/PendingActionsList";

type Tab = "chat" | "board" | "actions";

export function PlannerPlane({ projectSlug }: { projectSlug: string }) {
  const [activeTab, setActiveTab] = useState<Tab>("chat");
  const project = useQuery(api.projects.getBySlug, { slug: projectSlug });

  if (!project) return null;

  const projectId = project._id;

  return (
    <div className="flex flex-col h-full bg-black/5 border-r border-[--border]">
      {/* Plane Header */}
      <div className="px-4 py-3 border-b border-[--border] flex items-center justify-between bg-black/20">
        <h2 className="text-[10px] font-black uppercase tracking-[0.2em] text-[--muted-foreground] flex items-center gap-2">
          <Sparkles size={12} className="text-[--primary]" />
          Planner
        </h2>
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-green-500/10 border border-green-500/20">
          <div className="w-1 h-1 rounded-full bg-green-500 animate-pulse" />
          <span className="text-[8px] font-black uppercase tracking-tighter text-green-500">Active</span>
        </div>
      </div>

      {/* Tabs Sub-nav */}
      <div className="flex border-b border-[--border] bg-black/10">
        <button
          onClick={() => setActiveTab("chat")}
          className={cn(
            "flex-1 flex flex-col items-center py-2.5 transition-all relative group",
            activeTab === "chat" ? "text-[--foreground]" : "text-[--muted-foreground] hover:text-[--foreground]"
          )}
        >
          <MessageSquare size={14} className={cn("mb-1 transition-transform group-hover:scale-110", activeTab === "chat" && "text-[--primary]")} />
          <span className="text-[9px] font-black uppercase tracking-widest">Chat</span>
          {activeTab === "chat" && (
            <div className="absolute bottom-0 left-2 right-2 h-0.5 bg-[--primary] rounded-t-full shadow-[0_-2px_8px_rgba(var(--primary-rgb),0.5)]" />
          )}
        </button>
        <button
          onClick={() => setActiveTab("board")}
          className={cn(
            "flex-1 flex flex-col items-center py-2.5 transition-all relative group",
            activeTab === "board" ? "text-[--foreground]" : "text-[--muted-foreground] hover:text-[--foreground]"
          )}
        >
          <ListChecks size={14} className={cn("mb-1 transition-transform group-hover:scale-110", activeTab === "board" && "text-[--primary]")} />
          <span className="text-[9px] font-black uppercase tracking-widest">Board</span>
          {activeTab === "board" && (
            <div className="absolute bottom-0 left-2 right-2 h-0.5 bg-[--primary] rounded-t-full shadow-[0_-2px_8px_rgba(var(--primary-rgb),0.5)]" />
          )}
        </button>
        <button
          onClick={() => setActiveTab("actions")}
          className={cn(
            "flex-1 flex flex-col items-center py-2.5 transition-all relative group",
            activeTab === "actions" ? "text-[--foreground]" : "text-[--muted-foreground] hover:text-[--foreground]"
          )}
        >
          <ShieldAlert size={14} className={cn("mb-1 transition-transform group-hover:scale-110", activeTab === "actions" && "text-[--primary]")} />
          <span className="text-[9px] font-black uppercase tracking-widest">Actions</span>
          {activeTab === "actions" && (
            <div className="absolute bottom-0 left-2 right-2 h-0.5 bg-[--primary] rounded-t-full shadow-[0_-2px_8px_rgba(var(--primary-rgb),0.5)]" />
          )}
        </button>
      </div>
      
      {/* Content Area */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "chat" && <PlannerChat projectId={projectId} />}
        {activeTab === "board" && <ActivePlanSummary projectId={projectId} />}
        {activeTab === "actions" && <PendingActionsList projectId={projectId} />}
      </div>
    </div>
  );
}
