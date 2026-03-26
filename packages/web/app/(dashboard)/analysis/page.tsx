"use client";
import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { analysis, type AnalysisPlugin, type AnalysisResult, type AnalysisSection } from "@/lib/api";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

function AnalysisPageInner() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("projectId") || undefined;

  const [plugins, setPlugins] = useState<AnalysisPlugin[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    analysis.plugins()
      .then((p) => { setPlugins(p); if (p.length) setSelected(p[0].slug); })
      .catch(() => setError("Could not connect to API. Is the FastAPI server running?"));
  }, []);

  async function run() {
    if (!selected) return;
    setRunning(true); setResult(null); setError("");
    try {
      setResult(await analysis.run(selected, {}, projectId));
    } catch (e) {
      setError(String(e));
    } finally { setRunning(false); }
  }

  return (
    <div className="flex gap-6">
      {/* Sidebar */}
      <div className="w-52 shrink-0">
        <h2 className="text-lg font-semibold mb-4">Analysis</h2>
        {error && <p className="text-xs text-red-400 mb-3">{error}</p>}
        <div className="flex flex-col gap-1 mb-4">
          {plugins.map((p) => (
            <button
              key={p.slug}
              onClick={() => setSelected(p.slug)}
              className={`text-left px-3 py-2 rounded text-sm transition-colors border ${
                selected === p.slug
                  ? "bg-[--accent]/25 text-[--foreground] border-[--primary]/60 font-medium shadow-[inset_2px_0_0_0_var(--primary)]"
                  : "border-transparent text-[--muted-foreground] hover:text-[--foreground] hover:bg-white/5 hover:border-[--border]"
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
        <button
          onClick={run}
          disabled={running || !selected}
          className="w-full py-2 rounded bg-[--primary] text-[--primary-foreground] text-sm font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
        >
          {running ? "Running…" : "Run"}
        </button>
      </div>

      {/* Results */}
      <div className="flex-1">
        {!result && !running && (
          <div className="flex items-center justify-center h-64 text-[--muted-foreground] text-sm border border-dashed border-[--border] rounded-lg">
            Select a module and click Run
          </div>
        )}
        {running && (
          <div className="flex items-center justify-center h-64 text-[--muted-foreground] text-sm">
            Running analysis…
          </div>
        )}
        {result && (
          <div>
            <h3 className="text-xl font-semibold mb-6">{result.title}</h3>
            {result.sections.map((sec, i) => <Section key={i} sec={sec} />)}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AnalysisPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-[--muted-foreground]">Loading analysis…</div>}>
      <AnalysisPageInner />
    </Suspense>
  );
}

function Section({ sec }: { sec: AnalysisSection }) {
  if (sec.type === "divider") return <hr className="my-6 border-[--border]" />;

  return (
    <div className="mb-6">
      {"title" in sec && sec.title && <h4 className="font-medium mb-3 text-[--foreground]">{sec.title}</h4>}

      {sec.type === "metrics" && (
        <div className="flex gap-4 flex-wrap">
          {sec.items.map((item, i) => (
            <div key={i} className="flex-1 min-w-32 p-4 rounded-lg border border-[--border] bg-[--card]">
              <p className="text-xs text-[--muted-foreground] mb-1">{item.label}</p>
              <p className="text-lg font-semibold text-[--foreground]">{String(item.value)}</p>
            </div>
          ))}
        </div>
      )}

      {sec.type === "table" && (
        <div className="rounded border border-[--border] overflow-auto max-h-96">
          <table className="w-full text-sm">
            <thead className="bg-[--muted] sticky top-0">
              <tr>
                {sec.columns.map((col) => (
                  <th key={col} className="text-left px-3 py-2 text-[--muted-foreground] font-medium whitespace-nowrap">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sec.data.map((row, i) => (
                <tr key={i} className="border-t border-[--border] hover:bg-white/[0.02]">
                  {sec.columns.map((col) => (
                    <td key={col} className="px-3 py-2 text-[--foreground]">{String(row[col] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {sec.type === "chart" && (
        <div className="h-64 rounded border border-[--border] bg-[--card] p-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sec.data}>
              <XAxis dataKey={sec.x} tick={{ fill: "#8b949e", fontSize: 11 }} />
              <YAxis tick={{ fill: "#8b949e", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 6 }}
                labelStyle={{ color: "#e6edf3" }}
              />
              <Line type="monotone" dataKey={sec.y} stroke="#58a6ff" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {sec.type === "text" && (
        <p className="text-sm text-[--muted-foreground] leading-6">{sec.content}</p>
      )}

      {sec.type === "group" && sec.items.map((s, i) => <Section key={i} sec={s} />)}
    </div>
  );
}
