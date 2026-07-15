"use client";

import { useMemo, useState } from "react";
import type { Project, Resource, SourcesResponse } from "@/lib/krail/api";
import type { QueryResult } from "@/lib/krail/analyze/query";
import styles from "./krail-analyze.module.css";

type Props = { projects: Resource<Project[]>; selectedProjectId?: string; sql: string; limit: number; query?: Resource<QueryResult>; sources?: Resource<SourcesResponse> };
type Provenance = { title: string; value: string; note?: string };

const EXAMPLES = [
  "SELECT *\nFROM sources\nLIMIT 25",
  "SELECT *\nFROM artifacts\nLIMIT 25",
];

function display(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Notice<T>({ resource, label }: { resource?: Resource<T>; label: string }) {
  if (!resource || resource.state === "ready") return null;
  const copy = resource.state === "error" ? resource.error.message : resource.state === "loading" ? `${label} is loading.` : resource.message;
  return <div className={`${styles.notice} ${resource.state === "error" ? styles.error : ""}`} role="status"><strong>{resource.state === "unavailable" ? `${label} unavailable` : label}</strong><span>{copy}</span>{resource.state === "error" && resource.error.requestId && <small>Request ID: {resource.error.requestId}</small>}</div>;
}

function ProjectPicker({ projects, selectedProjectId }: Pick<Props, "projects" | "selectedProjectId">) {
  if (projects.state !== "ready") return <Notice resource={projects} label="Projects" />;
  if (!projects.data.length) return <div className={styles.notice}><strong>No projects registered</strong><span>Register a KRAIL project to use Analyze.</span></div>;
  return <label className={styles.field}><span>Project</span><select name="project" defaultValue={selectedProjectId}>{projects.data.map((project) => <option key={project.projectId} value={project.projectId}>{project.displayName}</option>)}</select></label>;
}

function ResultTable({ result }: { result: QueryResult }) {
  if (!result.columns.length) return <div className={styles.notice}><strong>No tabular result</strong><span>The query completed, but the API returned no columns.</span></div>;
  return <div className={styles.tableWrap} tabIndex={0} aria-label="Query results table"><table><caption>{result.rowCount.toLocaleString()} rows returned{result.truncated ? "; result is truncated" : ""}</caption><thead><tr>{result.columns.map((column) => <th key={column.name} scope="col">{column.name}<small>{column.type ?? "value"}</small></th>)}</tr></thead><tbody>{result.rows.map((row, index) => <tr key={index}>{result.columns.map((column, columnIndex) => <td key={`${index}-${column.name}`}>{display(row[columnIndex])}</td>)}</tr>)}</tbody></table></div>;
}

function AccessibleChart({ result }: { result: QueryResult }) {
  const chart = useMemo(() => {
    const numericIndex = result.columns.findIndex((_, index) => result.rows.some((row) => typeof row[index] === "number" && Number.isFinite(row[index] as number)));
    if (numericIndex < 0 || !result.rows.length) return undefined;
    const labelIndex = result.columns.findIndex((_, index) => index !== numericIndex);
    const points = result.rows.slice(0, 24).map((row, index) => ({ label: labelIndex >= 0 ? display(row[labelIndex]) : String(index + 1), value: Number(row[numericIndex]) })).filter((point) => Number.isFinite(point.value));
    const max = Math.max(...points.map((point) => Math.abs(point.value)), 1);
    return { label: result.columns[numericIndex].name, points, max };
  }, [result]);
  if (!chart?.points.length) return <section className={styles.chartEmpty}><strong>Chart unavailable</strong><span>Run a query with at least one numeric column to render an accessible chart.</span></section>;
  const description = `${chart.label}: ${chart.points.map((point) => `${point.label} ${point.value}`).join(", ")}`;
  return <figure className={styles.chart}><figcaption><span className={styles.eyebrow}>Accessible chart</span><strong>{chart.label}</strong><small>First {chart.points.length} returned rows</small></figcaption><svg viewBox={`0 0 640 ${Math.max(180, chart.points.length * 28 + 44)}`} role="img" aria-labelledby="chart-title chart-description"><title id="chart-title">{chart.label} query result chart</title><desc id="chart-description">{description}</desc>{chart.points.map((point, index) => { const y = 26 + index * 28; const width = Math.max(1, Math.abs(point.value) / chart.max * 420); return <g key={`${point.label}-${index}`}><text x="0" y={y + 13}>{point.label}</text><rect x="205" y={y} width={width} height="18" rx="3" className={styles.bar} /><text x={215 + width} y={y + 13}>{point.value}</text></g>; })}</svg><table className={styles.srOnly}><caption>{chart.label} values</caption><tbody>{chart.points.map((point, index) => <tr key={index}><th scope="row">{point.label}</th><td>{point.value}</td></tr>)}</tbody></table></figure>;
}

function ProvenanceDrawer({ result, sources, onClose }: { result: QueryResult; sources?: Resource<SourcesResponse>; onClose: () => void }) {
  const querySources = result.sources;
  return <div className={styles.backdrop} role="presentation" onMouseDown={onClose}><aside className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="provenance-title" onMouseDown={(event) => event.stopPropagation()}><div className={styles.drawerTop}><div><span className={styles.eyebrow}>Reproducibility</span><h2 id="provenance-title">Query provenance</h2></div><button type="button" onClick={onClose} aria-label="Close provenance">×</button></div><dl className={styles.provenance}><div><dt>Inputs</dt><dd><code>{result.sql}</code></dd></div><div><dt>Endpoint</dt><dd>POST /api/v1/projects/&#123;id&#125;/query</dd></div><div><dt>Fetched</dt><dd>{new Date(result.fetchedAt).toLocaleString()}</dd></div><div><dt>Request ID</dt><dd>{result.requestId ?? "not provided"}</dd></div><div><dt>Rows</dt><dd>{result.rowCount.toLocaleString()}{result.truncated ? " (truncated)" : ""}</dd></div></dl><h3>Query-level sources</h3>{querySources.length ? <ul className={styles.sourceList}>{querySources.map((source) => <li key={source.id}><strong>{source.id}</strong><span>{source.url ?? source.path ?? source.kind ?? "KRAIL source"}</span></li>)}</ul> : <div className={styles.notice}><strong>Lineage not reported</strong><span>The query response did not identify source records. The project inventory below is context only, not an assertion that every source was used.</span></div>}<h3>Project source inventory</h3>{sources?.state === "ready" ? <ul className={styles.sourceList}>{sources.data.inventory.sources.map((source) => <li key={source.id}><strong>{source.id}</strong><span>{source.url ?? source.path ?? source.kind}</span></li>)}</ul> : <Notice resource={sources} label="Source inventory" />}</aside></div>;
}

export function KrailAnalyze({ projects, selectedProjectId, sql, limit, query, sources }: Props) {
  const [draft, setDraft] = useState(sql);
  const [provenance, setProvenance] = useState(false);
  const result = query?.state === "ready" ? query.data : undefined;
  return <main className={styles.page}><a className={styles.skip} href="#query-results">Skip to query results</a><header className={styles.header}><div><span className={styles.eyebrow}>RAIL · KRAIL API boundary</span><h1>Analyze</h1><p>Run bounded, read-only queries against the registered KRAIL project. Results are never read from the browser, local files, or legacy RAIL SQL.</p></div></header><form className={styles.workbench} action="/krail-analyze" method="get"><div className={styles.controls}><ProjectPicker projects={projects} selectedProjectId={selectedProjectId} /><label className={styles.field}><span>Maximum rows</span><input name="limit" type="number" min="1" max="1000" defaultValue={limit} /></label></div><label className={styles.sqlField}><span>Read-only SQL</span><textarea name="sql" value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={10000} placeholder="SELECT * FROM sources LIMIT 25" spellCheck="false" aria-describedby="query-help" /><small id="query-help">Submitted to the project-scoped KRAIL query API. The API enforces its own read-only policy and result bounds.</small></label><div className={styles.actions}><button type="submit" name="run" value="1">Run query</button><span>{draft.length.toLocaleString()} / 10,000 characters</span>{EXAMPLES.map((example, index) => <button className={styles.example} type="button" key={example} onClick={() => setDraft(example)}>Example {index + 1}</button>)}</div></form><section id="query-results" className={styles.results} aria-labelledby="results-title"><div className={styles.sectionTop}><div><span className={styles.eyebrow}>Source-backed output</span><h2 id="results-title">Query results</h2></div>{result && <button className={styles.provenanceButton} type="button" onClick={() => setProvenance(true)}>View provenance</button>}</div>{!query && <div className={styles.empty}><strong>Ready for a query</strong><span>Choose a registered project, enter read-only SQL, and run it through KRAIL.</span></div>}<Notice resource={query} label="Query" />{result && <><div className={styles.summary}><span><strong>{result.rowCount.toLocaleString()}</strong> rows</span><span><strong>{result.columns.length}</strong> columns</span><span><strong>{result.sourceIds.length}</strong> query sources</span><span>{result.truncated ? "Result capped" : "Complete response"}</span></div><ResultTable result={result} /><AccessibleChart result={result} /></>}</section>{provenance && result && <ProvenanceDrawer result={result} sources={sources} onClose={() => setProvenance(false)} />}</main>;
}
