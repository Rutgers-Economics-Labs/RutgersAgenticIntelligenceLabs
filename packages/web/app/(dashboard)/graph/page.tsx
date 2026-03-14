"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { ontology, type GraphData } from "@/lib/api";

const NODE_COLORS: Record<string, string> = {
  State: "#F5A623", County: "#4A9EDD", Municipality: "#50C878",
  Individual: "#B07FD4", Measure: "#E05C5C",
};
const ALL_TYPES = ["State", "County", "Municipality", "Individual"];

export default function GraphPage() {
  const [types, setTypes] = useState<string[]>(["State", "County"]);
  const [stateFips, setStateFips] = useState<string>("");
  const [states, setStates] = useState<{ id: string; name: string; fips: string }[]>([]);
  const [showLabels, setShowLabels] = useState(true);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const graphRef = useRef<HTMLDivElement>(null);
  const ForceGraphRef = useRef<unknown>(null);

  // Load state list for filter
  useEffect(() => {
    ontology.instances("State", 1, 100)
      .then((r) => setStates(
        r.items.map((s) => ({
          id: s.id,
          name: String(s.properties.hasName ?? s.id),
          fips: String(s.properties.hasFIPS ?? ""),
        })).sort((a, b) => a.name.localeCompare(b.name))
      ))
      .catch(() => {});
  }, []);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await ontology.graph(types, stateFips || undefined);
      setGraph(data);
    } catch (e) {
      setError("Could not load graph. Is the FastAPI server running?");
    } finally { setLoading(false); }
  }, [types, stateFips]);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  // Dynamic import of react-force-graph (client only)
  const [FG, setFG] = useState<React.ComponentType<unknown> | null>(null);
  useEffect(() => {
    import("react-force-graph").then((m) => setFG(() => (m as { ForceGraph2D: React.ComponentType<unknown> }).ForceGraph2D));
  }, []);

  const toggleType = (t: string) =>
    setTypes((prev) => prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]);

  return (
    <div className="flex gap-6 h-[calc(100vh-4rem)]">
      {/* Controls */}
      <div className="w-52 shrink-0 flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Graph Explorer</h2>

        <div>
          <p className="text-xs text-[--muted-foreground] mb-2 uppercase tracking-wide">Entity Types</p>
          {ALL_TYPES.map((t) => (
            <label key={t} className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={types.includes(t)} onChange={() => toggleType(t)}
                className="accent-[--primary]" />
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: NODE_COLORS[t] }} />
              <span className="text-sm">{t}</span>
            </label>
          ))}
        </div>

        {(types.includes("County") || types.includes("Municipality")) && (
          <div>
            <p className="text-xs text-[--muted-foreground] mb-2 uppercase tracking-wide">Focus State</p>
            <select
              value={stateFips}
              onChange={(e) => setStateFips(e.target.value)}
              className="w-full px-2 py-1.5 rounded border border-[--border] bg-[--muted] text-sm text-[--foreground]"
            >
              <option value="">— All States —</option>
              {states.map((s) => (
                <option key={s.fips} value={s.fips}>{s.name}</option>
              ))}
            </select>
          </div>
        )}

        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)}
            className="accent-[--primary]" />
          Show edge labels
        </label>

        <div>
          <p className="text-xs text-[--muted-foreground] mb-2 uppercase tracking-wide">Legend</p>
          {types.map((t) => (
            <div key={t} className="flex items-center gap-2 py-0.5">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: NODE_COLORS[t] }} />
              <span className="text-xs text-[--muted-foreground]">{t}</span>
            </div>
          ))}
        </div>

        {graph && (
          <p className="text-xs text-[--muted-foreground]">
            {graph.nodes.length.toLocaleString()} nodes ·{" "}
            {graph.links.length.toLocaleString()} edges
          </p>
        )}
      </div>

      {/* Graph canvas */}
      <div className="flex-1 rounded-lg overflow-hidden border border-[--border] bg-[#0d1117]">
        {error && (
          <div className="flex items-center justify-center h-full text-sm text-red-400">{error}</div>
        )}
        {loading && (
          <div className="flex items-center justify-center h-full text-sm text-[--muted-foreground]">Loading graph…</div>
        )}
        {!loading && !error && graph && FG && (
          // @ts-ignore — react-force-graph types are loose
          <FG
            graphData={graph}
            width={graphRef.current?.clientWidth}
            height={graphRef.current?.clientHeight}
            backgroundColor="#0d1117"
            nodeColor={(n: { group: string }) => NODE_COLORS[n.group] ?? "#8b949e"}
            nodeLabel={(n: { label: string; group: string; properties: Record<string, unknown> }) => {
              const pop = n.properties.hasPopulation;
              return `<div style="background:#161b22;border:1px solid #30363d;padding:6px 10px;border-radius:6px;font-size:12px">
                <b style="color:${NODE_COLORS[n.group] ?? '#8b949e'}">${n.group}</b><br/>
                ${n.label}${pop != null ? `<br/><span style="color:#8b949e">Pop: ${Number(pop).toLocaleString()}</span>` : ""}
              </div>`;
            }}
            nodeVal={(n: { group: string; properties: Record<string, unknown> }) => {
              const pop = n.properties?.hasPopulation as number | undefined;
              if (!pop) return 4;
              return n.group === "State" ? 12 : n.group === "County" ? 6 : 3;
            }}
            linkLabel={showLabels ? (l: { label: string }) => l.label : undefined}
            linkColor={() => "#484f58"}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
          />
        )}
        {!loading && !error && graph && !FG && (
          <div className="flex items-center justify-center h-full text-sm text-[--muted-foreground]">Loading renderer…</div>
        )}
        <div ref={graphRef} className="absolute inset-0 pointer-events-none" />
      </div>
    </div>
  );
}
