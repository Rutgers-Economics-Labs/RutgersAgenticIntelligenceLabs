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
    <div className="flex flex-col h-full bg-transparent">
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {scripts === undefined ? (
          <div className="space-y-3">
             {[1,2,3,4].map(i => <div key={i} className="h-14 bg-[--muted]/20 rounded-xl animate-pulse" />)}
          </div>
        ) : scripts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 px-6 text-center space-y-4">
             <div className="w-14 h-14 rounded-2xl bg-[--muted]/10 flex items-center justify-center border border-[--border]">
                <FileText className="text-[--muted-foreground]/30" size={28} />
             </div>
             <div className="space-y-1">
                <p className="text-xs font-bold text-[--foreground]">First script awaits</p>
                <p className="text-[10px] text-[--muted-foreground] leading-relaxed">
                   Your saved analyses will appear here for quick access and iteration.
                </p>
             </div>
          </div>
        ) : (
          <div className="space-y-2">
            {scripts.map((script) => (
              <button
                key={script._id}
                onClick={() => onSelect(script)}
                className={cn(
                  "w-full text-left p-3 rounded-xl border transition-all duration-300 group relative overflow-hidden",
                  selectedId === script._id
                    ? "bg-[--background]/80 border-[--primary]/40 shadow-lg shadow-[--primary]/5 scale-[1.02] z-10"
                    : "bg-[--card]/20 border-transparent hover:bg-[--card]/40 hover:border-[--border]"
                )}
              >
                {selectedId === script._id && (
                  <div className="absolute left-0 top-0 bottom-0 w-1 bg-[--primary] shadow-[0_0_8px_var(--primary)]" />
                )}
                <div className="flex items-center justify-between gap-3 min-w-0">
                  <div className="flex items-center gap-3 min-w-0">
                     <div className={cn(
                        "w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border transition-colors",
                        selectedId === script._id 
                          ? "bg-[--primary]/15 border-[--primary]/20 text-[--primary]" 
                          : "bg-[--muted]/40 border-[--border] text-[--muted-foreground]"
                     )}>
                        <FileText size={16} />
                     </div>
                     <div className="flex flex-col min-w-0">
                        <span className={cn(
                          "text-sm font-bold truncate leading-tight transition-colors",
                          selectedId === script._id ? "text-[--foreground]" : "text-[--muted-foreground] group-hover:text-[--foreground]"
                        )}>
                          {script.name}
                        </span>
                        <div className="flex items-center gap-2 mt-1">
                           <span className="text-[9px] font-bold text-[--muted-foreground]/40 uppercase tracking-tighter">
                              {new Date(script.updatedAt).toLocaleDateString()}
                           </span>
                           {script.lastJobId && (
                             <div className="w-1 h-1 rounded-full bg-green-500/40" />
                           )}
                        </div>
                     </div>
                  </div>
                  <div className={cn(
                    "transition-all duration-300",
                    selectedId === script._id ? "opacity-100" : "opacity-0 group-hover:opacity-100 translate-x-1 group-hover:translate-x-0"
                  )}>
                     <Play size={14} className="text-[--primary]" fill={selectedId === script._id ? "currentColor" : "none"} />
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
