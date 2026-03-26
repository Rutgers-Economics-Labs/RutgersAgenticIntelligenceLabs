"use client";

import { useEffect, useState, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { sql, SqlResult } from "@/lib/api";
import { Play, Sparkles, Table2, ChevronDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const EXAMPLE_QUERIES = [
  { label: "All states", query: 'SELECT * FROM "State" LIMIT 20' },
  { label: "Top counties by population", query: 'SELECT _id, hasName, hasPopulation FROM "County" ORDER BY hasPopulation DESC LIMIT 20' },
  { label: "Measures with values", query: 'SELECT _id, hasSeries, hasDate, hasValue FROM "Measure" WHERE hasValue IS NOT NULL ORDER BY hasDate DESC LIMIT 50' },
  { label: "Municipality count by state", query: `SELECT LEFT(_id, 8) as state_prefix, COUNT(*) as count FROM "Municipality" GROUP BY 1 ORDER BY count DESC LIMIT 20` },
];

function SqlPageInner() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("projectId") || undefined;

  const [query, setQuery] = useState('SELECT * FROM "State" LIMIT 20');
  const [nlQuestion, setNlQuestion] = useState("");
  const [result, setResult] = useState<SqlResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [schema, setSchema] = useState<Record<string, { name: string; type: string }[]>>({});
  const [schemaOpen, setSchemaOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    sql.schema(projectId).then(setSchema).catch(() => {});
  }, [projectId]);

  async function runQuery() {
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await sql.query(query, projectId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function translateAndRun() {
    if (!nlQuestion.trim() || translating) return;
    setTranslating(true);
    setError(null);
    setResult(null);
    try {
      const res = await sql.translate(nlQuestion, undefined, projectId);
      setQuery(res.sql ?? "");
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTranslating(false);
    }
  }

  const tables = Object.keys(schema);

  return (
    <div className="flex flex-col h-screen bg-[--background]">
      {/* Header */}
      <header className="px-5 py-3 border-b border-[--border] bg-[--card] shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Table2 size={16} className="text-[--primary]" />
          <span className="text-sm font-semibold text-[--foreground]">SQL Explorer</span>
          {tables.length > 0 && (
            <span className="text-xs text-[--muted-foreground]">({tables.join(", ")})</span>
          )}
        </div>
        <button
          onClick={() => setSchemaOpen(v => !v)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted] rounded-md transition-colors"
        >
          Schema
          <ChevronDown size={11} className={cn("transition-transform", schemaOpen && "rotate-180")} />
        </button>
      </header>

      {/* Schema panel */}
      {schemaOpen && tables.length > 0 && (
        <div className="px-5 py-3 border-b border-[--border] bg-[--muted]/30 shrink-0">
          <div className="flex flex-wrap gap-4">
            {tables.map(t => (
              <div key={t} className="text-xs">
                <p className="font-medium text-[--primary] mb-1">{t}</p>
                <ul className="space-y-0.5 text-[--muted-foreground]">
                  {schema[t].slice(0, 8).map(c => (
                    <li key={c.name}>{c.name} <span className="opacity-50">{c.type}</span></li>
                  ))}
                  {schema[t].length > 8 && <li className="opacity-50">+{schema[t].length - 8} more</li>}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col overflow-hidden p-4 gap-3">
        {/* NL → SQL */}
        <div className="flex gap-2 shrink-0">
          <div className="flex-1 flex items-center gap-2 rounded-lg border border-[--border] bg-[--muted] px-3 py-2">
            <Sparkles size={13} className="text-[--primary] shrink-0" />
            <input
              value={nlQuestion}
              onChange={e => setNlQuestion(e.target.value)}
              onKeyDown={e => e.key === "Enter" && translateAndRun()}
              placeholder="Ask in plain English — AI will write the SQL…"
              className="flex-1 bg-transparent text-sm text-[--foreground] placeholder:text-[--muted-foreground] focus:outline-none"
            />
          </div>
          <button
            onClick={translateAndRun}
            disabled={translating || !nlQuestion.trim()}
            className="px-3 py-2 rounded-lg bg-[--primary]/15 text-[--primary] text-xs font-medium hover:bg-[--primary]/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {translating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            Translate
          </button>
        </div>

        {/* Example queries */}
        <div className="flex gap-2 flex-wrap shrink-0">
          {EXAMPLE_QUERIES.map(ex => (
            <button
              key={ex.label}
              onClick={() => setQuery(ex.query)}
              className="px-2.5 py-1 rounded-md border border-[--border] text-xs text-[--muted-foreground] hover:text-[--foreground] hover:border-[--primary]/40 transition-colors"
            >
              {ex.label}
            </button>
          ))}
        </div>

        {/* SQL editor */}
        <div className="relative shrink-0">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.preventDefault();
                runQuery();
              }
            }}
            rows={4}
            spellCheck={false}
            placeholder="SELECT * FROM ..."
            className="w-full resize-none rounded-lg border border-[--border] bg-[--muted] px-4 py-3 text-sm font-mono text-[--foreground] placeholder:text-[--muted-foreground] focus:outline-none focus:border-[--primary]/50 transition-colors"
          />
          <button
            onClick={runQuery}
            disabled={loading || !query.trim()}
            className="absolute bottom-3 right-3 flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-[--primary] text-[--primary-foreground] text-xs font-medium hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
          >
            {loading ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            Run <kbd className="opacity-60 ml-1">⌘↵</kbd>
          </button>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-auto rounded-lg border border-[--border] bg-[--card]">
          {error && (
            <div className="p-4 text-sm text-red-400 bg-red-900/10">
              <p className="font-medium mb-1">Error</p>
              <pre className="text-xs whitespace-pre-wrap">{error}</pre>
            </div>
          )}

          {result && !error && (
            <>
              {result.explanation && (
                <div className="px-4 py-2.5 border-b border-[--border] text-xs text-[--muted-foreground] bg-[--muted]/30">
                  {result.explanation}
                </div>
              )}
              {result.sql && result.sql !== query && (
                <div className="px-4 py-2 border-b border-[--border] bg-[--muted]/20">
                  <p className="text-[10px] uppercase text-[--muted-foreground] mb-1">Generated SQL</p>
                  <pre className="text-xs font-mono text-[--foreground]">{result.sql}</pre>
                </div>
              )}
              <div className="px-4 py-2 border-b border-[--border] text-xs text-[--muted-foreground]">
                {result.rowCount} row{result.rowCount !== 1 ? "s" : ""}
              </div>
              {result.rows.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border-collapse">
                    <thead className="sticky top-0 bg-[--muted]">
                      <tr>
                        {result.columns.map(c => (
                          <th key={c} className="border-b border-[--border] px-3 py-2 text-left text-[--muted-foreground] font-medium whitespace-nowrap">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, i) => (
                        <tr key={i} className="border-b border-[--border]/50 hover:bg-[--muted]/30 transition-colors">
                          {result.columns.map(c => (
                            <td key={c} className="px-3 py-2 text-[--foreground] whitespace-nowrap max-w-xs truncate">
                              {String(row[c] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="p-4 text-sm text-[--muted-foreground]">No rows returned.</p>
              )}
            </>
          )}

          {!result && !error && !loading && (
            <div className="flex items-center justify-center h-full text-[--muted-foreground] text-sm">
              Run a query to see results
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center h-full gap-2 text-[--muted-foreground] text-sm">
              <Loader2 size={16} className="animate-spin" />
              Executing…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function SqlPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-[--muted-foreground]">Loading SQL…</div>}>
      <SqlPageInner />
    </Suspense>
  );
}
