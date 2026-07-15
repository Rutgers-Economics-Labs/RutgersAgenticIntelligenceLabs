"use client";

import { useEffect, useMemo, useState } from "react";
import type { ApprovalInventoryResponse, FindResponse, GraphResponse, IntegrityResponse, Project, Resource, SourceImpactResponse, SourcesResponse, WorkflowInventoryResponse } from "@/lib/krail/api";
import styles from "./krail-explore.module.css";

type Search = { project?: string; q?: string; type?: string; topic?: string; entity?: string; status?: string; freshness?: string; workflow?: string };
type Props = { projects: Resource<Project[]>; selectedProjectId?: string; search: Search; find?: Resource<FindResponse>; graph?: Resource<GraphResponse>; sources?: Resource<SourcesResponse>; integrity?: Resource<IntegrityResponse>; affected?: Resource<SourceImpactResponse>; impactIsPartial?: boolean; impactSourceCount?: number; workflows?: Resource<WorkflowInventoryResponse>; approvals?: Resource<ApprovalInventoryResponse> };
type RecordRef = { id: string; path?: string | null; label: string; kind: string; metadata?: Record<string, unknown> };

function Notice<T>({ resource, label }: { resource?: Resource<T>; label: string }) {
  if (!resource || resource.state === "ready") return null;
  const error = resource.state === "error";
  const message = resource.state === "error" ? resource.error.message : resource.state === "loading" ? `${label} is loading.` : resource.message;
  return <div className={`${styles.notice} ${error ? styles.error : ""}`} role={error ? "alert" : "status"}><strong>{error ? `${label} unavailable` : label}</strong><span>{message}</span>{error && <small>Request ID: {resource.error.requestId ?? "not provided"}</small>}</div>;
}

function Provenance({ record, onClose }: { record: RecordRef; onClose: () => void }) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  return <div className={styles.backdrop} onMouseDown={onClose}><aside className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="provenance-title" onMouseDown={(event) => event.stopPropagation()}><div className={styles.drawerTop}><div><span className={styles.eyebrow}>Live platform data</span><h2 id="provenance-title">{record.label}</h2></div><button type="button" onClick={onClose} aria-label="Close provenance">×</button></div><dl><div><dt>KRAIL ID</dt><dd>{record.id}</dd></div><div><dt>Kind</dt><dd>{record.kind}</dd></div>{record.path && <div><dt>Project path</dt><dd>{record.path}</dd></div>}</dl>{record.metadata && Object.keys(record.metadata).length > 0 && <pre>{JSON.stringify(record.metadata, null, 2)}</pre>}</aside></div>;
}

function Graph({ resource, open }: { resource?: Resource<GraphResponse>; open: (record: RecordRef) => void }) {
  if (!resource || resource.state !== "ready") return <Notice resource={resource} label="Relationship graph" />;
  const { graph } = resource.data;
  if (!graph.nodes.length && !graph.documents.length) return <Notice resource={{ state: "empty", message: "This project has no graph records for the active filters." }} label="Relationship graph" />;
  const recordsById = new Map(graph.nodes.map((node) => [node.id, { ...node, metadata: { ...node.metadata } }]));
  graph.documents.forEach((document) => {
    const existing = recordsById.get(document.id);
    recordsById.set(document.id, existing
      ? { ...existing, metadata: { ...existing.metadata, path: document.path, topics: document.topics, entities: document.entities } }
      : { id: document.id, label: document.title, kind: document.kind, metadata: { path: document.path, topics: document.topics, entities: document.entities } });
  });
  const nodes = Array.from(recordsById.values()).slice(0, 12);
  const positions = nodes.map((node, index) => ({ ...node, x: 70 + (index % 4) * 190, y: 52 + Math.floor(index / 4) * 95 }));
  const byId = new Map(positions.map((node) => [node.id, node]));
  return <section className={styles.graphPanel} aria-labelledby="graph-title"><div className={styles.sectionTop}><div><span className={styles.eyebrow}>Connected records</span><h2 id="graph-title">Entity, document & source graph</h2></div><span className={styles.count}>{recordsById.size} records · {graph.edges.length} links</span></div>
    <svg className={styles.graph} viewBox="0 0 800 360" role="img" aria-label="Relationship graph of KRAIL records">
      {graph.edges.map((edge) => { const from = byId.get(edge.source); const to = byId.get(edge.target); return from && to ? <line key={edge.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={styles.edge}><title>{edge.relation}</title></line> : null; })}
      {positions.map((node) => <g key={node.id} className={styles.node} tabIndex={0} role="button" aria-label={`Open provenance for ${node.label}`} onClick={() => open({ id: node.id, label: node.label, kind: node.kind, path: typeof node.metadata.path === "string" ? node.metadata.path : undefined, metadata: node.metadata })} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open({ id: node.id, label: node.label, kind: node.kind, path: typeof node.metadata.path === "string" ? node.metadata.path : undefined, metadata: node.metadata }); } }}><circle cx={node.x} cy={node.y} r="25"/><text x={node.x} y={node.y + 44} textAnchor="middle">{node.label.slice(0, 22)}</text></g>)}
    </svg>
    <details className={styles.graphList}><summary>Accessible relationship list</summary><ul>{graph.edges.map((edge) => <li key={edge.id}>{edge.source} <strong>{edge.relation}</strong> {edge.target}</li>)}</ul></details>
    {graph.warnings.length > 0 && <p className={styles.warning}>{graph.warnings.join(" · ")}</p>}
  </section>;
}

export function KrailExplore({ projects, selectedProjectId, search, find, graph, sources, integrity, affected, impactIsPartial, impactSourceCount, workflows, approvals }: Props) {
  const [provenance, setProvenance] = useState<RecordRef | null>(null);
  const kinds = useMemo(() => find?.state === "ready" ? Array.from(new Set(find.data.result.items.map((item) => item.kind))) : [], [find]);
  if (projects.state !== "ready") return <main className={styles.page}><Notice resource={projects} label="Projects" /></main>;
  if (!projects.data.length) return <main className={styles.page}><Notice resource={{ state: "empty", message: "Register a KRAIL project through the platform API to start exploring." }} label="No projects registered" /></main>;
  const sourceCount = sources?.state === "ready" ? sources.data.inventory.sources.length : 0;
  return <main className={styles.page}><header className={styles.header}><div><span className={styles.eyebrow}>KRAIL / Explore</span><h1>Evidence workspace</h1><p>Live, read-only records from the integrated KRAIL platform API.</p></div><span className={styles.live}>● Live platform data</span></header>
    <form className={styles.controls} action="/krail-explore"><label>Project<select name="project" defaultValue={selectedProjectId}>{projects.data.map((project) => <option key={project.projectId} value={project.projectId}>{project.displayName}</option>)}</select></label><label className={styles.query}>Find across KRAIL<input name="q" defaultValue={search.q ?? ""} placeholder="Search entities, sources, documents…" /></label><label>Kind<select name="type" defaultValue={search.type ?? ""}><option value="">All kinds</option>{kinds.map((kind) => <option key={kind}>{kind}</option>)}</select></label><label>Topic<input name="topic" defaultValue={search.topic ?? ""} placeholder="Optional" /></label><button type="submit">Explore</button></form>
    <section className={styles.summary}><div><span>Sources</span><strong>{integrity?.state === "ready" ? integrity.data.integrity.sources : sourceCount}</strong></div><div><span>Claims</span><strong>{integrity?.state === "ready" ? integrity.data.integrity.claims : "—"}</strong></div><div><span>Artifacts</span><strong>{integrity?.state === "ready" ? integrity.data.integrity.artifacts : "—"}</strong></div><div><span>Integrity</span><strong>{integrity?.state === "ready" ? integrity.data.integrity.status : "Unavailable"}</strong></div></section>
    <div className={styles.workspace}><section className={styles.results}><div className={styles.sectionTop}><div><span className={styles.eyebrow}>Unified find</span><h2>Results</h2></div>{find?.state === "ready" && <span className={styles.count}>{find.data.result.total} matches</span>}</div><Notice resource={find} label="Find" />{find?.state === "ready" && (find.data.result.items.length ? <ul className={styles.resultList}>{find.data.result.items.map((item) => <li key={item.id}><button type="button" onClick={() => setProvenance({ id: item.id, label: item.title, kind: item.kind, path: item.path, metadata: item.metadata })}><span className={styles.kind}>{item.kind}</span><strong>{item.title}</strong><em>{item.score !== null && item.score !== undefined ? item.score.toFixed(2) : "—"}</em><p>{item.snippet ?? item.path ?? "No excerpt supplied by KRAIL."}</p>{item.path && <small>{item.path}</small>}</button></li>)}</ul> : <Notice resource={{ state: "empty", message: "No KRAIL records match the active search and filters." }} label="Find" />)}</section>
      <Graph resource={graph} open={setProvenance} />
    </div>
    <section className={styles.evidence}><div className={styles.sectionTop}><div><span className={styles.eyebrow}>Evidence</span><h2>Source inventory & impact</h2></div><span className={styles.count}>{sourceCount} sources</span></div><Notice resource={sources} label="Source inventory" />{sources?.state === "ready" && <div className={styles.sourceGrid}>{sources.data.inventory.sources.map((source) => <article key={source.id}><button type="button" onClick={() => setProvenance({ id: source.id, label: source.url ?? source.path ?? source.id, kind: source.kind, path: source.path, metadata: source.metadata })}><span className={styles.kind}>{source.kind}</span><strong>{source.url ?? source.path ?? source.id}</strong><small>{source.documents.length} linked documents</small></button></article>)}</div>}{impactIsPartial && <div className={styles.partialImpact} role="status"><strong>Partial source impact</strong><span>Impact is calculated from the first {impactSourceCount} source IDs in deterministic order; this project has more sources than the API accepts in one request.</span></div>}<Notice resource={affected} label="Source impact" />{affected?.state === "ready" && <p className={styles.impact}>Affected document paths: {affected.data.impact.documents.length ? affected.data.impact.documents.join(", ") : "none reported"}.</p>}</section>
    <section className={styles.capabilities}><h2>Read-only capabilities</h2><Notice resource={workflows} label="Workflow inventory" /><Notice resource={approvals} label="Approval inventory" />{workflows?.state === "ready" && approvals?.state === "ready" && <p>{workflows.data.inventory.workflows.length} workflows and {approvals.data.inventory.approvals.length} approvals are visible. Launch, run events, and approval decisions are intentionally outside this workspace.</p>}</section>{provenance && <Provenance record={provenance} onClose={() => setProvenance(null)} />}</main>;
}
