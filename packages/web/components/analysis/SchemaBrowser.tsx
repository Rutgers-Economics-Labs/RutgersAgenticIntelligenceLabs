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
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [search, setSearch] = useState("");

  useEffect(() => {
    sql.schema(projectId)
      .then(setSchema)
      .finally(() => setLoading(false));
  }, [projectId]);

  const toggle = (tableName: string) => {
    setExpanded(prev => ({ ...prev, [tableName]: !prev[tableName] }));
  };

  const filteredTables = Object.entries(schema).filter(([name]) => 
    name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full bg-[--card] border-l border-[--border]">
      <div className="p-3 border-b border-[--border] space-y-3">
        <div className="flex items-center gap-2 text-[--muted-foreground]">
          <Database size={14} />
          <span className="text-xs font-semibold uppercase tracking-wider">Project Schema</span>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[--muted-foreground]" size={12} />
          <input
            type="text"
            placeholder="Filter tables..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[--muted]/50 border border-[--border] rounded-md pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[--primary]/50"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 custom-scrollbar">
        {loading ? (
          <div className="space-y-2 p-2">
            {[1, 2, 3].map(i => <div key={i} className="h-6 bg-[--muted]/50 rounded animate-pulse" />)}
          </div>
        ) : filteredTables.length === 0 ? (
          <p className="text-center text-[--muted-foreground] text-xs py-10 italic">No tables found</p>
        ) : (
          <div className="space-y-1">
            {filteredTables.map(([tableName, columns]) => (
              <div key={tableName} className="space-y-0.5">
                <button
                  onClick={() => toggle(tableName)}
                  className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-[--muted]/50 text-xs text-[--foreground] transition-colors group"
                >
                  {expanded[tableName] ? <ChevronDown size={14} className="text-[--muted-foreground]" /> : <ChevronRight size={14} className="text-[--muted-foreground]" />}
                  <Table size={14} className="text-blue-400/80" />
                  <span className="font-medium truncate">{tableName}</span>
                  <span className="ml-auto text-[10px] text-[--muted-foreground] opacity-0 group-hover:opacity-100">{columns.length} cols</span>
                </button>

                {expanded[tableName] && (
                  <div className="pl-6 pr-2 py-1 space-y-1">
                    {columns.map(col => (
                      <div 
                        key={col.name} 
                        className="flex items-center justify-between gap-2 group cursor-pointer"
                        onClick={() => onSelect?.(col.name)}
                      >
                        <div className="flex items-center gap-1.5 min-w-0">
                          <Columns size={12} className="text-[--muted-foreground]/60 shrink-0" />
                          <span className="truncate text-[11px] text-[--muted-foreground] group-hover:text-[--primary]">{col.name}</span>
                        </div>
                        <span className="text-[9px] text-[--muted-foreground]/40 font-mono uppercase shrink-0">{col.type}</span>
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
