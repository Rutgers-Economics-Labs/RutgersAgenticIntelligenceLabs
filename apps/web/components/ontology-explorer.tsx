"use client";

import { useMemo, useState } from "react";
import { GraphVisualizer, type GraphLink, type GraphNode } from "@/components/graph-visualizer";
import { EntityExplorer } from "@/components/entity-explorer";

type OntologyClass = { name: string; count: number };

type TabId = "schema" | "instances" | "database" | "browse";

type OntologyExplorerProps = {
  projectId: string;
  classes: OntologyClass[];
  classGraph: { nodes: GraphNode[]; links: GraphLink[]; error?: string };
  instanceGraph: { nodes: GraphNode[]; links: GraphLink[]; error?: string };
  databaseGraph: { nodes: GraphNode[]; links: GraphLink[]; error?: string };
};

const TABS: { id: TabId; label: string; hint: string }[] = [
  {
    id: "schema",
    label: "Entities & relationships",
    hint: "OWL classes and object properties from the ontology schema.",
  },
  {
    id: "instances",
    label: "Instance graph",
    hint: "Sample of hydrated entities linked by relationships (pan/zoom, click a node for details).",
  },
  {
    id: "database",
    label: "Database",
    hint: "DuckDB tables and inferred joins from shared columns.",
  },
  {
    id: "browse",
    label: "Browse",
    hint: "Search and inspect instances by class.",
  },
];

function mergeSchemaAndInstances(
  classGraph: OntologyExplorerProps["classGraph"],
  instanceGraph: OntologyExplorerProps["instanceGraph"],
): { nodes: GraphNode[]; links: GraphLink[] } {
  const nodes: GraphNode[] = [...classGraph.nodes];
  const links: GraphLink[] = [...classGraph.links];
  const classIds = new Set(classGraph.nodes.map((n) => n.id));

  for (const n of instanceGraph.nodes) {
    if (!nodes.some((x) => x.id === n.id)) nodes.push({ ...n, group: n.group ?? "instance" });
  }
  for (const l of instanceGraph.links) {
    const key = `${l.source}->${l.target}:${l.label ?? ""}`;
    if (!links.some((x) => `${x.source}->${x.target}:${x.label ?? ""}` === key)) {
      links.push(l);
    }
  }
  for (const n of instanceGraph.nodes) {
    const g = n.group;
    if (g && classIds.has(g)) {
      links.push({ source: g, target: n.id, label: "has instance" });
    }
  }
  return { nodes, links };
}

export function OntologyExplorer({
  projectId,
  classes,
  classGraph,
  instanceGraph,
  databaseGraph,
}: OntologyExplorerProps) {
  const [tab, setTab] = useState<TabId>("schema");

  const combined = useMemo(
    () => mergeSchemaAndInstances(classGraph, instanceGraph),
    [classGraph, instanceGraph],
  );

  const populatedCount = classes.filter((c) => c.count > 0).length;
  const totalInstances = classes.reduce((sum, c) => sum + (c.count ?? 0), 0);

  const active = TABS.find((t) => t.id === tab)!;
  const graphError =
    tab === "schema"
      ? classGraph.error
      : tab === "instances"
        ? instanceGraph.error
        : tab === "database"
          ? databaseGraph.error
          : undefined;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div
        style={{
          padding: "14px 16px",
          background: "var(--panel)",
          border: "1px solid var(--border)",
          borderRadius: 4,
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
          <span>
            <span style={{ color: "var(--muted)" }}>classes </span>
            {classes.length}
          </span>
          <span>
            <span style={{ color: "var(--muted)" }}>populated </span>
            {populatedCount}
          </span>
          <span>
            <span style={{ color: "var(--muted)" }}>instances </span>
            {totalInstances.toLocaleString()}
          </span>
        </div>
        <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--muted)", maxWidth: 720, lineHeight: 1.5 }}>
          Two graph views: the knowledge schema (classes + relationships) and the physical DuckDB layout. Use Browse
          for tables of instances. Repo files live under Evidence → Artifacts.
        </p>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            style={{
              padding: "8px 14px",
              fontSize: 11,
              fontFamily: "JetBrains Mono, monospace",
              fontWeight: tab === t.id ? 600 : 400,
              background: tab === t.id ? "var(--fg)" : "var(--panel)",
              color: tab === t.id ? "var(--bg)" : "var(--fg)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <p style={{ margin: 0, fontSize: 11, color: "var(--muted)" }}>{active.hint}</p>
      {graphError && (
        <div
          style={{
            padding: 12,
            fontSize: 11,
            fontFamily: "JetBrains Mono, monospace",
            color: "var(--s-awaiting)",
            borderLeft: "2px solid var(--s-awaiting)",
          }}
        >
          {graphError}
        </div>
      )}

      {tab === "schema" && (
        <GraphVisualizer
          nodes={combined.nodes}
          links={combined.links}
          mode="classes"
          height={560}
          emptyMessage="No ontology classes yet. Run hydration to load the knowledge graph."
        />
      )}

      {tab === "instances" && (
        <GraphVisualizer
          nodes={instanceGraph.nodes}
          links={instanceGraph.links}
          mode="instances"
          height={560}
          emptyMessage="No instance links found. Hydrate data or increase the sample limit."
        />
      )}

      {tab === "database" && (
        <GraphVisualizer
          nodes={databaseGraph.nodes}
          links={databaseGraph.links}
          mode="database"
          height={560}
          emptyMessage="No DuckDB artifact found. Run hydration to create onto.duckdb."
        />
      )}

      {tab === "browse" && <EntityExplorer projectId={projectId} classes={classes} />}
    </div>
  );
}
