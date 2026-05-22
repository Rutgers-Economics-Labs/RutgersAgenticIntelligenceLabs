"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";

export type GraphNode = {
  id: string;
  label: string;
  group?: string;
  count?: number;
  properties?: Record<string, unknown>;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
};

export type GraphLink = {
  source: string | GraphNode;
  target: string | GraphNode;
  label?: string;
};

type GraphMode = "instances" | "classes" | "database";

interface GraphVisualizerProps {
  nodes: GraphNode[];
  links: GraphLink[];
  mode?: GraphMode;
  height?: number;
  emptyMessage?: string;
}

const PALETTE = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#be185d"];

function colorForGroup(group: string | undefined, index: number): string {
  if (!group || group === "table") return "#64748b";
  let hash = 0;
  for (let i = 0; i < group.length; i++) hash = group.charCodeAt(i) + ((hash << 5) - hash);
  return PALETTE[Math.abs(hash + index) % PALETTE.length];
}

export function GraphVisualizer({
  nodes: initialNodes,
  links: initialLinks,
  mode = "instances",
  height = 520,
  emptyMessage = "No graph data available. Run hydration first.",
}: GraphVisualizerProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const displayNodes = useMemo(
    () =>
      initialNodes.map((n) => ({
        ...n,
        label:
          mode === "database" && typeof n.count === "number"
            ? `${n.label} (${n.count.toLocaleString()})`
            : mode === "classes" && typeof n.count === "number"
              ? `${n.label} (${n.count})`
              : n.label,
      })),
    [initialNodes, mode],
  );

  useEffect(() => {
    if (!svgRef.current || displayNodes.length === 0) return;

    const nodes: GraphNode[] = displayNodes.map((n) => ({ ...n }));
    const links: GraphLink[] = initialLinks.map((l) => ({ ...l }));

    const width = svgRef.current.clientWidth || 800;
    const chartHeight = height;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const g = svg.append("g");

    svg.call(
      d3
        .zoom<SVGSVGElement, unknown>()
        .extent([
          [0, 0],
          [width, chartHeight],
        ])
        .scaleExtent([0.1, 8])
        .on("zoom", (event) => {
          g.attr("transform", event.transform);
        }),
    );

    const linkDistance = mode === "database" ? 130 : mode === "classes" ? 110 : 90;
    const charge = mode === "database" ? -400 : mode === "classes" ? -280 : -180;
    const nodeRadius = mode === "instances" ? 8 : 12;

    const simulation = d3
      .forceSimulation(nodes as d3.SimulationNodeDatum[])
      .force(
        "link",
        d3
          .forceLink(links)
          .id((d: unknown) => (d as GraphNode).id)
          .distance(linkDistance),
      )
      .force("charge", d3.forceManyBody().strength(charge))
      .force("center", d3.forceCenter(width / 2, chartHeight / 2))
      .force("collision", d3.forceCollide().radius(nodeRadius + 16));

    const link = g
      .append("g")
      .attr("stroke", "var(--border)")
      .attr("stroke-opacity", 0.6)
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke-width", 1.5);

    const node = g
      .append("g")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .style("cursor", "pointer")
      .on("click", (_event, d) => {
        setSelectedNode(d);
      })
      .call(
        d3
          .drag<any, any>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }),
      );

    node
      .append("circle")
      .attr("r", nodeRadius)
      .attr("fill", (d, i) => colorForGroup(d.group, i))
      .attr("stroke", "var(--panel)")
      .attr("stroke-width", 2);

    node
      .append("text")
      .text((d) => (d.label.length > 24 ? `${d.label.slice(0, 21)}…` : d.label))
      .attr("x", 12)
      .attr("y", 4)
      .style("font-size", "9px")
      .style("font-family", "JetBrains Mono, monospace")
      .style("fill", "var(--fg)")
      .style("pointer-events", "none");

    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);

      node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [displayNodes, initialLinks, mode, height]);

  return (
    <div style={{ display: "flex", gap: 12, height }}>
      <div
        style={{
          flex: 1,
          background: "var(--panel)",
          borderRadius: 4,
          border: "1px solid var(--border)",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <svg ref={svgRef} style={{ width: "100%", height: "100%", display: "block" }} />
        {displayNodes.length === 0 ? (
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--muted)",
              fontSize: 11,
              fontFamily: "JetBrains Mono, monospace",
              padding: 24,
              textAlign: "center",
            }}
          >
            {emptyMessage}
          </div>
        ) : (
          <div
            style={{
              position: "absolute",
              top: 8,
              left: 8,
              fontSize: 9,
              fontFamily: "JetBrains Mono, monospace",
              color: "var(--muted)",
              background: "var(--bg)",
              border: "1px solid var(--border)",
              padding: "4px 8px",
              borderRadius: 4,
            }}
          >
            {displayNodes.length} nodes · {initialLinks.length} edges · drag · scroll to zoom
          </div>
        )}
      </div>

      {selectedNode && (
        <aside
          style={{
            width: 240,
            flexShrink: 0,
            background: "var(--panel)",
            border: "1px solid var(--border)",
            borderRadius: 4,
            padding: 12,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            overflowY: "auto",
            maxHeight: height,
          }}
        >
          <div style={{ color: "var(--muted)", marginBottom: 8, textTransform: "uppercase", fontSize: 9 }}>
            Selected node
          </div>
          <div style={{ color: "var(--s-running)", fontWeight: "bold", marginBottom: 12, wordBreak: "break-all" }}>
            {selectedNode.label || selectedNode.id}
          </div>
          <div style={{ marginBottom: 8 }}>
            <span style={{ color: "var(--muted)" }}>Type:</span> {selectedNode.group ?? "—"}
          </div>
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: 8 }}>
            <div style={{ color: "var(--muted)", marginBottom: 4 }}>Properties</div>
            {Object.entries(selectedNode.properties || {}).map(([k, v]) => (
              <div key={k} style={{ marginBottom: 4 }}>
                <div style={{ opacity: 0.7 }}>{k}</div>
                <div style={{ color: "var(--fg)" }}>{String(v)}</div>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setSelectedNode(null)}
            style={{
              marginTop: 12,
              width: "100%",
              padding: 4,
              background: "var(--bg)",
              border: "1px solid var(--border)",
              color: "var(--muted)",
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </aside>
      )}
    </div>
  );
}
