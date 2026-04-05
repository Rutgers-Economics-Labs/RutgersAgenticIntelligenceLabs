import { Database, Layers, Network, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface ContextSnapshotProps {
  context: {
    project: { name: string; status: string; last_hydrated?: string };
    ontology: { classes: { name: string; instance_count: number }[] };
    data_sources: { slug: string; name: string }[];
    pipelines: { slug: string; name: string; last_run?: string }[];
  };
}

export function ContextSnapshot({ context }: ContextSnapshotProps) {
  const totalClasses = context.ontology.classes.length;
  const topClasses = context.ontology.classes.slice(0, 3);
  const totalSources = context.data_sources.length;
  const totalPipelines = context.pipelines.length;

  return (
    <div className="w-full max-w-2xl mx-auto my-6 rounded-xl border border-[--border] bg-[--card] overflow-hidden shadow-sm">
      <div className="px-5 py-4 border-b border-[--border] flex items-center justify-between bg-[--muted]/30">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-[--primary]/10 text-[--primary]">
            <Database size={18} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[--foreground] flex items-center gap-2">
              {context.project.name}
              <span className={cn(
                "px-2 py-0.5 rounded-full text-[10px] font-medium tracking-wide uppercase",
                context.project.status === "hydrated" ? "bg-green-500/10 text-green-500" : "bg-yellow-500/10 text-yellow-500"
              )}>
                {context.project.status}
              </span>
            </h3>
            <p className="text-xs text-[--muted-foreground] mt-0.5">Project context loaded</p>
          </div>
        </div>
      </div>

      <div className="px-5 py-4 space-y-4">
        <p className="text-sm font-medium text-[--foreground]">I have access to:</p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-[--muted-foreground] uppercase tracking-wider">
              <Network size={14} /> Ontology
            </div>
            <p className="text-sm text-[--foreground]">
              <span className="font-semibold">{totalClasses}</span> classes
            </p>
            <div className="text-xs text-[--muted-foreground] space-y-1">
              {topClasses.map(c => (
                <div key={c.name} className="flex justify-between items-center bg-[--muted]/50 px-2 py-1 rounded">
                  <span className="truncate">{c.name}</span>
                  <span className="font-mono text-[10px] bg-[--background] px-1 rounded">{c.instance_count.toLocaleString()}</span>
                </div>
              ))}
              {totalClasses > 3 && <div className="text-[10px] text-center pt-1 text-[--muted-foreground]/70">+{totalClasses - 3} more</div>}
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-[--muted-foreground] uppercase tracking-wider">
              <Layers size={14} /> Data Sources
            </div>
            <p className="text-sm text-[--foreground]">
              <span className="font-semibold">{totalSources}</span> sources
            </p>
            <div className="text-xs text-[--muted-foreground] flex flex-wrap gap-1">
              {context.data_sources.map(ds => (
                <span key={ds.slug} className="bg-[--muted]/50 px-2 py-1 rounded truncate max-w-[120px] inline-block" title={ds.name}>
                  {ds.slug}
                </span>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-[--muted-foreground] uppercase tracking-wider">
              <Zap size={14} /> Pipelines
            </div>
            <p className="text-sm text-[--foreground]">
              <span className="font-semibold">{totalPipelines}</span> pipelines
            </p>
            <div className="text-xs text-[--muted-foreground] space-y-1">
              {context.pipelines.map(p => (
                <div key={p.slug} className="bg-[--muted]/50 px-2 py-1 rounded flex flex-col gap-0.5">
                  <span className="truncate font-medium">{p.slug}</span>
                  {p.last_run && <span className="text-[10px] text-[--muted-foreground]/70">Run: {p.last_run}</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="px-5 py-3 border-t border-[--border] bg-[--muted]/20">
        <p className="text-xs text-center text-[--muted-foreground]">
          Ask me anything about this project's data, ontology, or pipelines.
        </p>
      </div>
    </div>
  );
}
