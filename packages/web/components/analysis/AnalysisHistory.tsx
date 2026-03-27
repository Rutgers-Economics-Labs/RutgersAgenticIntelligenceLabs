"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";
import { FileText, Clock, Trash2, Play, MousePointer2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface AnalysisHistoryProps {
  projectId: Id<"projects">;
  onSelect: (script: any) => void;
  selectedId?: string;
}

export function AnalysisHistory({ projectId, onSelect, selectedId }: AnalysisHistoryProps) {
  const scripts = useQuery(api.analysis.listScripts, { projectId });

  return (
    <div className="flex flex-col h-full bg-[--card] border-r border-[--border]">
      <div className="p-3 border-b border-[--border] space-y-3 shadow-sm bg-[--muted]/5 animate-in fade-in transition-all duration-300">
        <div className="flex items-center justify-between gap-2 text-[--muted-foreground]">
          <div className="flex items-center gap-2 font-semibold uppercase tracking-wider text-[11px]">
            <Clock size={14} />
            <span>Saved Analyses</span>
          </div>
          <span className="text-[10px] tabular-nums font-mono opacity-60">
            {scripts?.length ?? 0}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 custom-scrollbar">
        {scripts === undefined ? (
          <div className="space-y-2 p-2 pt-4">
             {[1,2,3].map(i => <div key={i} className="h-10 bg-[--muted]/30 rounded-lg animate-pulse" />)}
          </div>
        ) : scripts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
             <div className="w-12 h-12 rounded-full bg-[--muted]/20 flex items-center justify-center mb-4">
                <FileText className="text-[--muted-foreground]/40" size={24} />
             </div>
             <p className="text-[11px] font-medium text-[--muted-foreground] mb-1">Create your first analysis</p>
             <p className="text-[10px] text-[--muted-foreground]/60">Write scripts to explore your project's data</p>
          </div>
        ) : (
          <div className="space-y-1.5 overflow-hidden rounded-md pt-2">
            {scripts.map((script) => (
              <button
                key={script._id}
                onClick={() => onSelect(script)}
                className={cn(
                  "w-full text-left p-2.5 rounded-lg border transition-all duration-200 group relative overflow-hidden",
                  selectedId === script._id
                    ? "bg-[--accent]/10 border-[--primary]/50 shadow-sm"
                    : "bg-transparent border-transparent hover:bg-[--muted]/30 hover:border-[--border]"
                )}
              >
                {selectedId === script._id && (
                  <div className="absolute left-0 top-0 bottom-0 w-1 bg-[--primary]/80" />
                )}
                <div className="flex items-start justify-between gap-3 min-w-0">
                  <div className="flex items-center gap-2.5 min-w-0">
                     <div className={cn(
                        "w-7 h-7 rounded-md flex items-center justify-center shrink-0 border border-[--border]",
                        selectedId === script._id ? "bg-[--primary]/20" : "bg-[--muted]/40"
                     )}>
                        <FileText size={14} className={selectedId === script._id ? "text-[--primary]" : "text-[--muted-foreground]"} />
                     </div>
                     <div className="flex flex-col min-w-0">
                        <span className="text-[13px] font-semibold text-[--foreground] truncate leading-tight group-hover:text-[--primary] transition-colors">{script.name}</span>
                        <span className="text-[10px] text-[--muted-foreground] opacity-60 mt-0.5 font-mono">
                           {new Date(script.updatedAt).toLocaleDateString()}
                        </span>
                     </div>
                  </div>
                  <div className="opacity-0 group-hover:opacity-100 transition-opacity translate-x-1 group-hover:translate-x-0">
                     <Play size={14} className="text-[--primary]" />
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
