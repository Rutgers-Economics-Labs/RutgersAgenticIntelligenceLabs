"use client";

import React from "react";

export function ToolResult({ name, result }: { name: string; result: unknown }) {
  if (!result || typeof result !== "object") {
    return (
      <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px] text-[--foreground]">
        {String(result)}
      </pre>
    );
  }

  const r = result as Record<string, unknown>;

  // SQL / table result
  if (Array.isArray(r.rows) && Array.isArray(r.columns)) {
    const cols = r.columns as string[];
    const rows = r.rows as Record<string, unknown>[];
    const rowCount = typeof r.rowCount === "number" ? r.rowCount : rows.length;
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-[11px] border-collapse">
          <thead>
            <tr>
              {cols.map(c => (
                <th key={c} className="border border-[--border] px-2 py-1 text-left text-[--muted-foreground] bg-black/20">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 20).map((row, i) => (
              <tr key={i} className="odd:bg-black/10">
                {cols.map(c => (
                  <td key={c} className="border border-[--border] px-2 py-1 text-[--foreground]">
                    {String(row[c] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > 20 && (
          <p className="mt-1 text-[10px] text-[--muted-foreground]">
            Showing 20 of {rowCount} rows
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
      <div className="space-y-2">
        {typeof r.error === "string" && r.error && (
          <pre className="rounded bg-red-900/30 p-2 text-[11px] text-red-300">{r.error}</pre>
        )}
        {typeof r.stdout === "string" && r.stdout && (
          <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px] text-[--foreground]">{r.stdout}</pre>
        )}
        {Array.isArray(r.figures) && r.figures.map((fig: string, i: number) => (
          <img key={i} src={`data:image/png;base64,${fig}`} alt="plot" className="max-w-full rounded" />
        ))}
        {dataframes &&
          Object.entries(dataframes).map(([dfName, df]) => {
            const d = df as { columns: string[]; rows: Record<string, unknown>[]; rowCount: number };
            return (
              <div key={dfName}>
                <p className="text-[10px] text-[--muted-foreground] mb-1">{dfName} ({d.rowCount} rows)</p>
                <ToolResult name="sql" result={{ columns: d.columns, rows: d.rows, rowCount: d.rowCount }} />
              </div>
            );
          })
        }
      </div>
    );
  }

  // Generic JSON
  return (
    <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[11px] text-[--foreground] max-h-48">
      {JSON.stringify(result, null, 2)}
    </pre>
  );
}
