"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ontology, type EntityDetail, type GraphData } from "@/lib/api";

const CLASS_COLORS: Record<string, string> = {
  State: "#F5A623",
  County: "#4A9EDD",
  Municipality: "#50C878",
  Individual: "#B07FD4",
  Measure: "#E05C5C",
};

function errorMessage(err: unknown) {
  if (err instanceof Error) return err.message;
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}

export default function EntityDetailClient({
  id,
  projectId,
}: {
  id: string;
  projectId?: string;
}) {
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [FG, setFG] = useState<React.ElementType<any> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    import("react-force-graph-2d").then((m) => setFG(() => (m as any).default));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");

    Promise.all([ontology.entity(id, projectId), ontology.entityGraph(id, projectId)])
      .then(([e, g]) => {
        if (cancelled) return;
        setEntity(e);
        setGraph(g);
      })
      .catch((err) => {
        if (cancelled) return;
        // Surface the backend detail (helps diagnose encoding/project issues)
        setError(errorMessage(err) || "Entity not found.");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id, projectId]);

  const color = entity ? (CLASS_COLORS[entity.class] ?? "#8b949e") : "#8b949e";

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-[--muted-foreground] text-sm">
        Loading…
      </div>
    );
  }

  if (error || !entity) {
    return (
      <div>
        <Link
          href={`/explorer${projectId ? `?projectId=${projectId}` : ""}`}
          className="text-sm text-[--primary] hover:underline mb-4 inline-block"
        >
          ← Back to Explorer
        </Link>
        <div className="p-4 rounded bg-red-900/30 border border-red-700 text-red-300 text-sm">
          {error || "Entity not found."}
        </div>
      </div>
    );
  }

  const propEntries = Object.entries(entity.properties).filter(([, v]) => v != null);

  return (
    <div className="max-w-5xl">
      <Link
        href={`/explorer${projectId ? `?projectId=${projectId}` : ""}`}
        className="text-sm text-[--primary] hover:underline mb-4 inline-block"
      >
        ← Back to Explorer
      </Link>

      <div className="flex items-start gap-4 mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span
              className="px-2 py-0.5 rounded text-xs font-medium"
              style={{ background: color + "22", color, border: `1px solid ${color}44` }}
            >
              {entity.class}
            </span>
            <span className="font-mono text-xs text-[--muted-foreground]">{entity.id}</span>
          </div>
          <h1 className="text-2xl font-semibold" style={{ color }}>
            {String(entity.properties.hasName ?? entity.id)}
          </h1>
          <p className="text-xs text-[--muted-foreground] mt-1 font-mono break-all">{entity.iri}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h2 className="text-sm font-semibold text-[--muted-foreground] uppercase tracking-wide mb-3">
            Properties
          </h2>
          <div className="rounded-lg border border-[--border] overflow-hidden">
            {propEntries.length === 0 ? (
              <p className="px-4 py-3 text-sm text-[--muted-foreground]">No properties.</p>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {propEntries.map(([key, val]) => (
                    <tr key={key} className="border-b border-[--border] last:border-0">
                      <td className="px-4 py-2.5 text-[--muted-foreground] font-mono text-xs w-40 shrink-0">
                        {key}
                      </td>
                      <td className="px-4 py-2.5 font-medium break-all">
                        {typeof val === "number" ? val.toLocaleString() : String(val)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {entity.relationships.length > 0 && (
            <>
              <h2 className="text-sm font-semibold text-[--muted-foreground] uppercase tracking-wide mb-3 mt-6">
                Relationships
              </h2>
              <div className="rounded-lg border border-[--border] overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[--border] bg-[--muted]">
                      <th className="text-left px-4 py-2 text-[--muted-foreground] font-medium text-xs">
                        Property
                      </th>
                      <th className="text-left px-4 py-2 text-[--muted-foreground] font-medium text-xs">
                        Target
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {entity.relationships.map((rel, i) => (
                      <tr key={i} className="border-b border-[--border] last:border-0 hover:bg-white/[0.03]">
                        <td className="px-4 py-2.5 font-mono text-xs text-[--muted-foreground]">
                          {rel.property}
                        </td>
                        <td className="px-4 py-2.5">
                          <Link
                            href={`/explorer/${encodeURIComponent(rel.targetId)}${
                              projectId ? `?projectId=${projectId}` : ""
                            }`}
                            className="text-[--primary] hover:underline text-sm"
                          >
                            {rel.targetName}
                          </Link>
                          <span className="text-[--muted-foreground] font-mono text-xs ml-2">
                            {rel.targetId}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <div>
          <h2 className="text-sm font-semibold text-[--muted-foreground] uppercase tracking-wide mb-3">
            Graph
          </h2>
          <div
            ref={containerRef}
            className="rounded-lg border border-[--border] bg-[#0d1117] overflow-hidden"
            style={{ height: 420 }}
          >
            {graph && FG ? (
              // @ts-ignore
              <FG
                graphData={graph}
                width={containerRef.current?.clientWidth ?? 500}
                height={420}
                backgroundColor="#0d1117"
                nodeColor={(n: { group: string }) => CLASS_COLORS[n.group] ?? "#8b949e"}
                nodeLabel={(n: { label: string; group: string }) =>
                  `<div style="background:#161b22;border:1px solid #30363d;padding:4px 8px;border-radius:4px;font-size:12px">
                    <b style="color:${CLASS_COLORS[n.group] ?? "#8b949e"}">${n.group}</b><br/>${n.label}
                  </div>`
                }
                nodeVal={(n: { id: string }) => (n.id === id ? 10 : 4)}
                linkLabel={(l: { label: string }) => l.label}
                linkColor={() => "#484f58"}
                linkDirectionalArrowLength={4}
                linkDirectionalArrowRelPos={1}
                onNodeClick={(n: { id: string }) => {
                  if (n.id !== id) {
                    window.location.href = `/explorer/${encodeURIComponent(n.id)}${
                      projectId ? `?projectId=${projectId}` : ""
                    }`;
                  }
                }}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-sm text-[--muted-foreground]">
                Loading graph…
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

