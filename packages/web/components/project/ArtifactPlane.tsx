"use client";

import { History, Archive, CheckCircle2, Clock } from "lucide-react";

export function ArtifactPlane({ projectSlug }: { projectSlug: string }) {
  return (
    <div className="flex flex-col h-full bg-black/5">
      <div className="p-4 border-b border-[--border] flex items-center justify-between">
        <h2 className="text-xs font-bold uppercase tracking-wider text-[--muted-foreground] flex items-center gap-2">
          <Archive size={14} />
          Artifacts & Timeline
        </h2>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-6">
        <div className="space-y-2">
          <h3 className="text-[10px] font-bold text-[--muted-foreground] uppercase tracking-widest">Latest Artifacts</h3>
          <div className="grid gap-2">
            {[
              { name: "market_analysis.pdf", type: "PDF", time: "1h ago" },
              { name: "competitor_data.json", type: "Data", time: "3h ago" },
              { name: "summary_report.md", type: "Report", time: "5h ago" },
            ].map((art, i) => (
              <div key={i} className="group p-2 rounded-lg border border-[--border] bg-white/5 hover:bg-white/10 transition-colors cursor-pointer flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Archive size={12} className="text-[--muted-foreground]" />
                  <div>
                    <p className="text-[10px] font-medium truncate max-w-[120px]">{art.name}</p>
                    <p className="text-[9px] text-[--muted-foreground]">{art.type}</p>
                  </div>
                </div>
                <p className="text-[8px] text-[--muted-foreground] opacity-0 group-hover:opacity-100 transition-opacity">{art.time}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <h3 className="text-[10px] font-bold text-[--muted-foreground] uppercase tracking-widest">Execution Timeline</h3>
          <div className="relative pl-4 space-y-6 before:absolute before:left-[7px] before:top-1 before:bottom-1 before:w-[1px] before:bg-[--border]">
            {[
              { title: "Verification Passed", status: "success", time: "10:45 AM" },
              { title: "Artifact Generated", status: "success", time: "10:42 AM" },
              { title: "Worker Session Started", status: "running", time: "10:30 AM" },
            ].map((run, i) => (
              <div key={i} className="relative">
                <div className={cn(
                  "absolute -left-[13px] w-3 h-3 rounded-full border-2 border-black",
                  run.status === "success" ? "bg-emerald-500" : "bg-sky-500 animate-pulse"
                )} />
                <div className="space-y-0.5">
                  <p className="text-xs font-medium">{run.title}</p>
                  <p className="text-[9px] text-[--muted-foreground] flex items-center gap-1">
                    <Clock size={8} /> {run.time}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function cn(...classes: any[]) {
  return classes.filter(Boolean).join(" ");
}
