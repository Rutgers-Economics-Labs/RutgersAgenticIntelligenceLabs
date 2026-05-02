"use client";

import React, { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

export type GraphNode = {
  id: string;
  label: string;
  group?: string;
  properties?: Record<string, any>;
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

interface GraphVisualizerProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

export function GraphVisualizer({ nodes: initialNodes, links: initialLinks }: GraphVisualizerProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  useEffect(() => {
    if (!svgRef.current || initialNodes.length === 0) return;

    // Clone data to avoid mutations affecting props
    const nodes: GraphNode[] = initialNodes.map(n => ({ ...n }));
    const links: GraphLink[] = initialLinks.map(l => ({ ...l }));

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 400;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const g = svg.append("g");

    // Zoom support
    svg.call(d3.zoom<SVGSVGElement, unknown>()
      .extent([[0, 0], [width, height]])
      .scaleExtent([0.1, 8])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      }));

    const simulation = d3
      .forceSimulation(nodes as any)
      .force("link", d3.forceLink(links).id((d: any) => d.id).distance(100))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(40));

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
      .on("click", (event, d) => {
        setSelectedNode(d);
      })
      .call(
        d3.drag<any, any>()
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
          })
      );

    node.append("circle")
      .attr("r", 8)
      .attr("fill", (d) => d.group === "Observation" ? "#3b82f6" : "#10b981")
      .attr("stroke", "var(--panel)")
      .attr("stroke-width", 2);

    node.append("text")
      .text((d) => d.label.length > 20 ? d.label.slice(0, 17) + "..." : d.label)
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

    return () => simulation.stop();
  }, [initialNodes, initialLinks]);

  return (
    <div style={{ display: "flex", gap: "12px" }}>
      <div style={{ flex: 1, height: "400px", background: "var(--panel)", borderRadius: "4px", border: "1px solid var(--border)", position: "relative", overflow: "hidden" }}>
        <svg ref={svgRef} style={{ width: "100%", height: "100%" }} />
        {initialNodes.length === 0 && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)", fontSize: "11px", fontFamily: "JetBrains Mono, monospace" }}>
            No graph data available.
          </div>
        )}
      </div>
      
      {selectedNode && (
        <div style={{ width: "240px", background: "var(--panel)", border: "1px solid var(--border)", borderRadius: "4px", padding: "12px", fontFamily: "JetBrains Mono, monospace", fontSize: "10px", overflowY: "auto", maxHeight: "400px" }}>
          <div style={{ color: "var(--muted)", marginBottom: "8px", textTransform: "uppercase", fontSize: "9px" }}>Selected Node</div>
          <div style={{ color: "var(--s-running)", fontWeight: "bold", marginBottom: "12px", wordBreak: "break-all" }}>{selectedNode.id}</div>
          <div style={{ marginBottom: "8px" }}>
            <span style={{ color: "var(--muted)" }}>Type:</span> {selectedNode.group}
          </div>
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: "8px" }}>
            <div style={{ color: "var(--muted)", marginBottom: "4px" }}>Properties:</div>
            {Object.entries(selectedNode.properties || {}).map(([k, v]) => (
              <div key={k} style={{ marginBottom: "4px" }}>
                <div style={{ opacity: 0.7 }}>{k}</div>
                <div style={{ color: "var(--fg)" }}>{String(v)}</div>
              </div>
            ))}
          </div>
          <button 
            onClick={() => setSelectedNode(null)}
            style={{ marginTop: "12px", width: "100%", padding: "4px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--muted)", cursor: "pointer" }}
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
}
