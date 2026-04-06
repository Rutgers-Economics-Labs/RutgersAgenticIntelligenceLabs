"use client";
import { useState, useEffect, useRef, useCallback, Suspense, use } from "react";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";

import { ontology, type GraphData, isSyncRequiredError, jobs } from "@/lib/api";
import { useArtifactLink } from "@/components/ontology/useArtifactLink";
import { Activity, Link2, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const PRESET_COLORS: Record<string, string> = {
  State: "#F5A623", County: "#4A9EDD", Municipality: "#50C878",
  Individual: "#B07FD4", Measure: "#E05C5C",
  University: "#3b82f6", Department: "#8b5cf6", Faculty: "#f43f5e",
  PhDStudent: "#10b981", Course: "#eab308", Publication: "#6366f1", ResearchGrant: "#14b8a6",
  AcademicPerson: "#ec4899"
};

function hashColor(str: string) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  const h = Math.abs(hash) % 360;
  return `hsl(${h}, 70%, 65%)`;
}

function getNodeColor(group: string) {
  return PRESET_COLORS[group] || hashColor(group);
}

function GraphClient({ projectSlug }: { projectSlug: string }) {
  const convexProject = useQuery(api.projects.get, { slug: projectSlug });
  const { linking, linkArtifacts } = useArtifactLink(projectSlug);
  const autoGraphLoaded = useRef(false);

  const [availableTypes, setAvailableTypes] = useState<string[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [stateFips, setStateFips] = useState<string>("");
  const [states, setStates] = useState<{ id: string; name: string; fips: string }[]>([]);
  const [showLabels, setShowLabels] = useState(true);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isStale, setIsStale] = useState(false);
  const graphRef = useRef<HTMLDivElement>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [FG, setFG] = useState<React.ElementType<any> | null>(null);
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    import("react-force-graph-2d").then((m) => setFG(() => (m as any).default));
  }, []);

  useEffect(() => {
    autoGraphLoaded.current = false;
  }, [projectSlug]);

  // Fetch dynamically available classes
  useEffect(() => {
    ontology.classes(projectSlug)
      .then((res) => {
        // Sort by instance count (descending)
        const sortedRes = [...res].sort((a, b) => b.instanceCount - a.instanceCount);
        const tList = sortedRes.map(c => c.name);
        setAvailableTypes(tList);
        setTypes(tList.slice(0, 5)); // Auto-select top 5 most populated

        // If State exists, load states for filtering
        if (tList.includes("State")) {
          ontology.instances("State", 1, 100, "", projectSlug)
            .then((r) => setStates(
              r.items.map((s) => ({
                id: s.id,
                name: String(s.properties.hasName ?? s.id),
                fips: String(s.properties.hasFIPS ?? ""),
              })).sort((a, b) => a.name.localeCompare(b.name))
            ))
            .catch(() => {});
        }
      })
      .catch((e) => {
        if (isSyncRequiredError(e)) {
           setError("SYNC_REQUIRED");
        } else {
           setError("Could not load ontology classes. Is the API running?");
        }
      });
  }, [projectSlug]);

  const [isRunning, setIsRunning] = useState(false);

  async function handleLinkArtifacts() {
    try {
      await linkArtifacts((cls) => {
        const sortedRes = [...cls].sort((a, b) => b.instanceCount - a.instanceCount);
        const tList = sortedRes.map((c) => c.name);
        setAvailableTypes(tList);
        setTypes(tList.slice(0, 5));
        setError("");
      });
    } catch {
      /* toast in hook */
    }
  }

  async function handleInitialSync() {
    const pipelineSlug = convexProject?.pipelineConfigSlug;
    if (!pipelineSlug) {
      toast.error("No pipeline is configured for this project (Settings / Pipelines).");
      return;
    }
    try {
      setIsRunning(true);
      await jobs.trigger(pipelineSlug, projectSlug);
      toast.success("Pipeline job queued");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to trigger pipeline");
    } finally {
      setIsRunning(false);
    }
  }

  const loadGraph = useCallback(async () => {
    if (types.length === 0 && availableTypes.length > 0) {
      setGraph({ nodes: [], links: [] });
      return;
    }
    if (types.length === 0) return;
    
    setLoading(true);
    setError("");
    try {
      const data = await ontology.graph(types, stateFips || undefined, 500, projectSlug);
      setGraph(data);
    } catch (e) {
      setError("Could not load graph. Is the FastAPI server running?");
    } finally { 
      setLoading(false); 
      setIsStale(false);
    }
  }, [types, stateFips, projectSlug, availableTypes]);

  // After classes load, fetch the graph once (user can still change types and click Update)
  useEffect(() => {
    if (error === "SYNC_REQUIRED" || availableTypes.length === 0 || types.length === 0) return;
    if (autoGraphLoaded.current) return;
    autoGraphLoaded.current = true;
    void loadGraph();
  }, [availableTypes.length, types.length, error, loadGraph]);

  const toggleType = (t: string) => {
    setTypes((prev) => prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]);
    setIsStale(true);
  };

  return (
    <div className="flex gap-10 h-full w-full max-w-7xl mx-auto p-10 pb-20">
      {/* Controls */}
      <div className="w-52 shrink-0 flex flex-col gap-4 overflow-y-auto pr-2 pb-10">
        <h2 className="text-lg font-semibold">Graph Explorer</h2>

        <div>
          <p className="text-xs text-[--muted-foreground] mb-2 uppercase tracking-wide">Entity Types</p>
          {availableTypes.length === 0 && !error && <span className="text-xs text-[--muted-foreground]">Loading...</span>}
          {availableTypes.map((t) => (
            <label key={t} className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="checkbox" checked={types.includes(t)} onChange={() => toggleType(t)}
                className="accent-[--primary]" />
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: getNodeColor(t) }} />
              <span className="text-sm truncate" title={t}>{t}</span>
            </label>
          ))}
        </div>

        {availableTypes.includes("State") && (types.includes("County") || types.includes("Municipality")) && (
          <div>
            <p className="text-xs text-[--muted-foreground] mb-2 uppercase tracking-wide">Focus State</p>
            <select
              value={stateFips}
              onChange={(e) => { setStateFips(e.target.value); setIsStale(true); }}
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

        <button
          onClick={loadGraph}
          disabled={loading || types.length === 0}
          className={`mt-4 w-full py-2 px-4 rounded font-medium transition-all ${
            isStale || !graph 
              ? "bg-[--primary] text-[--primary-foreground] hover:opacity-90 shadow-lg shadow-[--primary]/20" 
              : "bg-[--muted] text-[--foreground] hover:bg-[--border]"
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {loading ? "Updating..." : graph ? (isStale ? "Update Graph" : "Refresh Graph") : "Show Graph"}
        </button>

        {isStale && graph && (
          <p className="text-[10px] text-[--primary] animate-pulse text-center">
            Settings changed. Click update to refresh.
          </p>
        )}

        {graph && (
          <p className="text-xs text-[--muted-foreground] mt-4">
            {graph.nodes.length.toLocaleString()} nodes ·{" "}
            {graph.links.length.toLocaleString()} edges
          </p>
        )}
      </div>

      {/* Graph canvas */}
      <div className="flex-1 rounded-lg overflow-hidden border border-[--border] bg-[#0d1117] relative">
        {error === "SYNC_REQUIRED" ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center z-20 p-8 text-center bg-[#0d1117] bg-opacity-95">
             <div className="w-16 h-16 rounded-full bg-amber-500/10 flex items-center justify-center mb-6 text-amber-500">
                <RefreshCw size={32} className="animate-spin-slow" />
             </div>
             <h3 className="text-xl font-bold text-white mb-3 uppercase tracking-tight">API can’t open ontology files</h3>
             <p className="text-sm text-slate-400 mb-4 max-w-md leading-relaxed">
               Hydration may have finished, but this project isn’t linked to artifact paths in Convex yet (HTTP 428).
               If you already ran a successful job on <strong className="text-slate-200">this machine</strong>, link paths from that job first.
             </p>
             <div className="flex flex-col sm:flex-row gap-3">
               <button
                 type="button"
                 onClick={() => void handleLinkArtifacts()}
                 disabled={linking}
                 className="px-8 py-3 rounded-full bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-bold shadow-lg shadow-emerald-600/20 transition-all flex items-center justify-center gap-2"
               >
                 {linking ? <Loader2 size={18} className="animate-spin" /> : <Link2 size={18} />}
                 Link latest hydration job
               </button>
               <button
                 type="button"
                 onClick={handleInitialSync}
                 disabled={isRunning || !convexProject?.pipelineConfigSlug}
                 className="px-8 py-3 rounded-full bg-amber-600 hover:bg-amber-500 text-white text-sm font-bold shadow-lg shadow-amber-600/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
               >
                 {isRunning ? <Loader2 size={18} className="animate-spin" /> : <Activity size={18} />}
                 Run pipeline again
               </button>
             </div>
          </div>
        ) : error && (
          <div className="absolute inset-0 flex items-center justify-center z-10 p-4 text-center">
             <div className="p-4 rounded bg-red-900/30 border border-red-700 text-red-300 text-sm max-w-md">{error}</div>
          </div>
        )}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10 bg-[#0d1117]/50 backdrop-blur-sm">
            <div className="text-sm text-[--muted-foreground]">Loading graph…</div>
          </div>
        )}
        {!loading && !error && graph && FG && (
          // @ts-ignore
          <FG
            graphData={graph}
            width={graphRef.current?.clientWidth}
            height={graphRef.current?.clientHeight}
            backgroundColor="#0d1117"
            nodeColor={(n: { group: string }) => getNodeColor(n.group)}
            nodeLabel={(n: { label: string; group: string; properties: Record<string, unknown> }) => {
              const pop = n.properties?.hasPopulation;
              return `<div style="background:#161b22;border:1px solid #30363d;padding:6px 10px;border-radius:6px;font-size:12px">
                <b style="color:${getNodeColor(n.group)}">${n.group}</b><br/>
                ${n.label}${pop != null ? `<br/><span style="color:#8b949e">Pop: ${Number(pop).toLocaleString()}</span>` : ""}
              </div>`;
            }}
            nodeVal={() => 4}
            linkLabel={showLabels ? (l: { label: string }) => l.label : undefined}
            linkColor={() => "#484f58"}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            onNodeClick={(n: { id: string }) => {
              window.location.href = `/explorer/${encodeURIComponent(n.id)}${projectSlug ? `?projectSlug=${encodeURIComponent(projectSlug)}` : ""}`;
            }}
          />
        )}
        <div ref={graphRef} className="absolute inset-0 pointer-events-none" />
      </div>
    </div>
  );
}

export default function GraphPage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = use(params);
  return (
    <Suspense fallback={<div className="p-8 text-[--muted-foreground]">Loading graph...</div>}>
      <GraphClient projectSlug={project} />
    </Suspense>
  );
}
