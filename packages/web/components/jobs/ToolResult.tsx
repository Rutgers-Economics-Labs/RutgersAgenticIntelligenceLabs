"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { FileCode2, Table as TableIcon, Image as ImageIcon, AlertTriangle, FolderOpen } from "lucide-react";

export function ToolResult({ name, result }: { name: string; result: unknown }) {
  if (!result || typeof result !== "object") {
    return (
      <div className="rounded-xl border border-[--border] bg-[--muted]/20 p-4 font-mono text-[11px] text-[--foreground]">
        <div className="flex items-center gap-2 mb-2 text-[--muted-foreground] font-bold text-[10px] uppercase">
          <FileCode2 size={12} />
          Raw Response
        </div>
        <pre className="overflow-x-auto whitespace-pre-wrap">{String(result)}</pre>
      </div>
    );
  }

  const r = result as Record<string, unknown>;

  // SQL / table result
  if (Array.isArray(r.rows) && Array.isArray(r.columns)) {
    const cols = r.columns as string[];
    const rows = r.rows as Record<string, unknown>[];
    const rowCount = typeof r.rowCount === "number" ? r.rowCount : rows.length;
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between text-[11px]">
          <div className="flex items-center gap-2 font-bold text-[--muted-foreground] uppercase tracking-wider">
            <TableIcon size={14} className="text-blue-500" />
            Dataset Result
          </div>
          <div className="px-2 py-0.5 rounded-full bg-[--muted]/30 text-[--muted-foreground] font-semibold">
            {rowCount} rows • {cols.length} columns
          </div>
        </div>
        <div className="overflow-hidden border border-[--border] rounded-xl shadow-sm">
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full text-[11px] border-collapse bg-[--card]/50">
              <thead>
                <tr>
                  {cols.map(c => (
                    <th key={c} className="border-b border-[--border] px-4 py-2.5 text-left text-[--foreground] font-bold bg-[--muted]/30">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[--border]">
                {rows.slice(0, 50).map((row, i) => (
                  <tr key={i} className="hover:bg-[--primary]/5 transition-colors">
                    {cols.map(c => (
                      <td key={c} className="px-4 py-2 text-[--muted-foreground]">
                        {row[c] === null ? (
                          <span className="opacity-30 italic">null</span>
                        ) : String(row[c] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        {rows.length > 50 && (
          <p className="px-1 text-[10px] text-[--muted-foreground] font-medium italic">
            Showing first 50 of {rowCount} rows
          </p>
        )}
      </div>
    );
  }

  // Code execution result
  if (name === "execute_python" || name === "code") {
    const dataframes =
      r.dataframes && typeof r.dataframes === "object"
        ? (r.dataframes as Record<string, unknown>)
        : null;

    return (
      <div className="space-y-6">
        {typeof r.error === "string" && r.error && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center gap-2 mb-2 text-red-500 font-bold text-[10px] uppercase">
              <AlertTriangle size={12} />
              Runtime Error
            </div>
            <pre className="font-mono text-[11px] text-red-400 overflow-x-auto whitespace-pre-wrap">{r.error}</pre>
          </div>
        )}
        
        {typeof r.stdout === "string" && r.stdout && (
          <div className="rounded-xl border border-[--border] bg-[--muted]/10 p-4 font-mono text-[11px]">
            <div className="flex items-center gap-2 mb-2 text-[--muted-foreground]/60 font-bold text-[10px] uppercase border-b border-[--border] pb-1.5">
              Console Output
            </div>
            <pre className="text-[--foreground] overflow-x-auto">{r.stdout}</pre>
          </div>
        )}

        {Array.isArray(r.figures) && r.figures.length > 0 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-[11px] font-bold text-[--muted-foreground] uppercase tracking-wider">
              <ImageIcon size={14} className="text-pink-500" />
              Generated Visualizations ({r.figures.length})
            </div>
            <div className="grid grid-cols-1 gap-6">
              {r.figures.map((fig: string, i: number) => (
                <div key={i} className="rounded-2xl overflow-hidden border border-[--border] bg-white p-2 shadow-inner">
                  <img src={`data:image/png;base64,${fig}`} alt="plot" className="w-full h-auto rounded-xl" />
                </div>
              ))}
            </div>
          </div>
        )}

        {dataframes && Object.keys(dataframes).length > 0 && (
          <div className="space-y-6 pt-2">
            {Object.entries(dataframes).map(([dfName, df]) => {
              const d = df as { columns: string[]; rows: Record<string, unknown>[]; rowCount: number };
              return (
                <div key={dfName} className="space-y-2">
                  <div className="flex items-center gap-2 px-1">
                    <span className="text-[11px] font-bold font-mono px-2 py-0.5 rounded bg-[--primary]/10 text-[--primary]">
                      df:{dfName}
                    </span>
                    <span className="text-[10px] text-[--muted-foreground]">({d.rowCount} total rows)</span>
                  </div>
                  <ToolResult name="sql" result={{ columns: d.columns, rows: d.rows, rowCount: d.rowCount }} />
                </div>
              );
            })}
          </div>
        )}

        {Array.isArray(r.artifacts) && r.artifacts.length > 0 && (
          <div className="rounded-xl border border-[--border] bg-[--muted]/10 p-4 space-y-2">
            <div className="flex items-center gap-2 text-[11px] font-bold text-[--muted-foreground] uppercase tracking-wider">
              <FolderOpen size={14} className="text-amber-500" />
              Saved files ({r.artifacts.length})
            </div>
            <ul className="space-y-1.5 text-[11px] font-mono">
              {(r.artifacts as { filename?: string; storageKey?: string }[]).map((a, i) => (
                <li key={i} className="text-[--foreground] break-all">
                  <span className="text-[--primary]">{a.filename ?? "file"}</span>
                  {a.storageKey ? (
                    <span className="block text-[10px] text-[--muted-foreground] mt-0.5">{a.storageKey}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  if (name === "describe_database" && Array.isArray((r as { tables?: unknown }).tables)) {
    const tables = (r as { tables: { name: string; row_count: number | null; columns: { name: string; type?: string; geometry_hint?: boolean }[] }[] }).tables;
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-[11px] font-bold text-[--muted-foreground] uppercase tracking-wider">
          <TableIcon size={14} className="text-cyan-500" />
          Live database ({tables.length} tables)
        </div>
        <div className="max-h-96 overflow-y-auto custom-scrollbar space-y-3 border border-[--border] rounded-xl p-3 bg-[--card]/30">
          {tables.map((t) => (
            <div key={t.name} className="text-[11px] border-b border-[--border]/60 pb-2 last:border-0">
              <div className="font-mono font-bold text-[--primary]">
                {t.name}
                <span className="ml-2 font-normal text-[--muted-foreground]">
                  {t.row_count != null ? `${t.row_count} rows` : "row count n/a"}
                </span>
              </div>
              <ul className="mt-1 pl-3 text-[10px] text-[--muted-foreground] space-y-0.5">
                {t.columns.map((c) => (
                  <li key={c.name}>
                    {c.name}{" "}
                    <span className="opacity-70">({c.type ?? "?"})</span>
                    {c.geometry_hint ? <span className="text-cyan-400/90 ml-1">· spatial hint</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Generic JSON
  return (
    <div className="rounded-xl border border-[--border] bg-[--muted]/10 p-4 overflow-hidden">
      <div className="flex items-center gap-2 mb-2 text-[--muted-foreground]/60 font-bold text-[10px] uppercase">
        Result Data (JSON)
      </div>
      <pre className="overflow-x-auto text-[11px] text-[--muted-foreground] max-h-96 custom-scrollbar">
        {JSON.stringify(result, null, 2)}
      </pre>
    </div>
  );
}
