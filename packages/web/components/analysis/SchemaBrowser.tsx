"use client";
import { useEffect, useState } from "react";
import { sql } from "@/lib/api";
import { Database, Table, Columns, Search, ChevronRight, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface SchemaBrowserProps {
  projectId?: string;
  onSelect?: (name: string) => void;
}

export function SchemaBrowser({ projectId, onSelect }: SchemaBrowserProps) {
  const [schema, setSchema] = useState<Record<string, { name: string; type: string }[]>>({});
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFetchError(null);
    sql
      .schema(projectId)
      .then((data) => {
        if (!cancelled) setSchema(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setSchema({});
          setFetchError(e instanceof Error ? e.message : "Could not load schema.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const toggle = (tableName: string) => {
    setExpanded(prev => ({ ...prev, [tableName]: !prev[tableName] }));
  };

  const filteredTables = Object.entries(schema).filter(([name]) => 
    name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full bg-transparent">
      <div className="p-4 border-b border-[--border] space-y-4">
        <div className="flex items-center gap-2 text-[--muted-foreground]">
          <Database size={15} className="text-[--primary]" />
          <span className="text-[11px] font-extrabold uppercase tracking-[0.2em]">Project Schema</span>
        </div>
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[--muted-foreground] transition-colors group-focus-within:text-[--primary]" size={14} />
          <input
            type="text"
            placeholder="Filter tables..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[--background]/40 border border-[--border] rounded-xl pl-10 pr-4 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-[--primary]/20 focus:border-[--primary]/40 transition-all placeholder:text-[--muted-foreground]/40 font-medium"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 custom-scrollbar">
        {loading ? (
          <div className="space-y-3 p-1">
            {[1, 2, 3, 4, 5].map(i => <div key={i} className="h-10 bg-[--muted]/20 rounded-lg animate-pulse" />)}
          </div>
        ) : fetchError ? (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-[11px] text-amber-200/90 leading-relaxed">
            <p className="font-semibold text-amber-100 mb-1">Schema unavailable</p>
            <p className="text-[--muted-foreground] whitespace-pre-wrap">{fetchError}</p>
          </div>
        ) : filteredTables.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 opacity-30 text-center">
             <Database size={32} className="mb-2" />
             <p className="text-xs font-medium italic">No tables found</p>
          </div>
        ) : (
          <div className="space-y-1.5">
            {filteredTables.map(([tableName, columns]) => (
              <div key={tableName} className="space-y-1 animate-in fade-in slide-in-from-left-2 duration-300">
                <button
                  onClick={() => toggle(tableName)}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all group relative overflow-hidden",
                    expanded[tableName] 
                      ? "bg-[--primary]/10 text-[--foreground]" 
                      : "hover:bg-[--muted]/40 text-[--muted-foreground] hover:text-[--foreground]"
                  )}
                >
                  <div className={cn(
                    "transition-transform duration-300",
                    expanded[tableName] ? "rotate-90" : ""
                  )}>
                    <ChevronRight size={14} className="opacity-40" />
                  </div>
                  <Table size={16} className={cn(
                    "transition-colors",
                    expanded[tableName] ? "text-[--primary]" : "text-blue-400/60 group-hover:text-blue-400"
                  )} />
                  <span className="font-bold text-[13px] truncate">{tableName}</span>
                  <span className="ml-auto text-[10px] font-mono tabular-nums opacity-0 group-hover:opacity-40 transition-opacity">
                    {columns.length}
                  </span>
                </button>

                {expanded[tableName] && (
                  <div className="pl-8 pr-2 py-1 space-y-1 border-l-2 border-[--primary]/10 ml-5 mb-2 animate-in slide-in-from-top-2 duration-300">
                    {columns.map(col => (
                      <div 
                        key={col.name} 
                        className="flex items-center justify-between gap-3 group/col cursor-pointer py-1"
                        onClick={() => onSelect?.(col.name)}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Columns size={12} className="text-[--muted-foreground]/30 shrink-0 group-hover/col:text-[--primary] transition-colors" />
                          <span className="truncate text-[12px] font-medium text-[--muted-foreground] group-hover/col:text-[--foreground] transition-colors">
                            {col.name}
                          </span>
                        </div>
                        <span className="text-[9px] font-black text-[--muted-foreground]/20 uppercase tracking-tighter shrink-0 border border-[--border] px-1.5 rounded bg-[--muted]/5">
                          {col.type}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
