"use client";

import { useState } from "react";
import type { Project, ProjectHealthResponse, ProjectManifestResponse, Resource, SourcesResponse } from "@/lib/krail/api";
import styles from "./krail-live.module.css";

type Props = {
  projects: Resource<Project[]>;
  selectedProjectId?: string;
  health?: Resource<ProjectHealthResponse>;
  manifest?: Resource<ProjectManifestResponse>;
  sources?: Resource<SourcesResponse>;
};

function ResourceNotice<T>({ resource, label }: { resource: Resource<T>; label: string }) {
  if (resource.state === "ready") return null;
  const copy = resource.state === "loading" ? `${label} is loading.`
    : resource.state === "empty" || resource.state === "unavailable" ? resource.message
    : resource.state === "error" ? resource.error.message : `${label} is loading.`;
  return <section className={`${styles.notice} ${resource.state === "error" ? styles.noticeError : ""}`} aria-live="polite">
    <strong>{resource.state === "error" ? `${label} unavailable` : label}</strong>
    <p>{copy}</p>
    {resource.state === "error" && <small>Request ID: {resource.error.requestId ?? "not provided"}</small>}
  </section>;
}

function ProjectPicker({ projects, selectedProjectId }: Pick<Props, "projects" | "selectedProjectId">) {
  if (projects.state !== "ready") return <ResourceNotice resource={projects} label="Projects" />;
  if (projects.data.length === 0) return <section className={styles.notice} aria-live="polite"><strong>No projects registered</strong><p>Register a KRAIL project through the platform API to begin.</p></section>;
  return <form className={styles.picker} action="/krail-live">
    <label htmlFor="project">Active project</label>
    <select id="project" name="project" defaultValue={selectedProjectId} onChange={(event) => event.currentTarget.form?.requestSubmit()}>
      {projects.data.map((project) => <option value={project.projectId} key={project.projectId}>{project.displayName}</option>)}
    </select>
  </form>;
}

function HealthCard({ resource }: { resource: Resource<ProjectHealthResponse> }) {
  if (resource.state !== "ready") return <ResourceNotice resource={resource} label="Project health" />;
  const { health } = resource.data;
  return <section className={styles.card} aria-labelledby="health-title">
    <div className={styles.cardTop}><div><span className={styles.eyebrow}>Runtime check</span><h2 id="health-title">Project health</h2></div><span className={health.ok ? styles.good : styles.attention}>{health.ok ? "Healthy" : "Needs attention"}</span></div>
    <p className={styles.muted}>KRAIL {health.krailVersion}</p>
    <ul className={styles.checkList}>{health.checks.map((check) => <li key={check.name}><span aria-hidden="true">{check.ok ? "●" : "!"}</span><div><strong>{check.name}</strong><p>{check.detail}</p></div></li>)}</ul>
    {health.warnings.length > 0 && <div className={styles.warning}><strong>Warnings</strong><ul>{health.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
  </section>;
}

function ManifestCard({ resource, onProvenance }: { resource: Resource<ProjectManifestResponse>; onProvenance: () => void }) {
  if (resource.state !== "ready") return <ResourceNotice resource={resource} label="Manifest" />;
  const { manifest } = resource.data;
  return <section className={styles.card} aria-labelledby="manifest-title">
    <div className={styles.cardTop}><div><span className={styles.eyebrow}>KRAIL record</span><h2 id="manifest-title">{manifest.name}</h2></div><button className={styles.textButton} type="button" onClick={onProvenance}>View provenance</button></div>
    <dl className={styles.details}><div><dt>Slug</dt><dd>{manifest.slug}</dd></div><div><dt>Mode</dt><dd>{manifest.knowledgeMode}</dd></div><div><dt>Branch</dt><dd>{manifest.defaultBranch}</dd></div><div><dt>Schema</dt><dd>v{manifest.version}</dd></div></dl>
  </section>;
}

function KnowledgeSurface({ resource, onProvenance }: { resource: Resource<SourcesResponse>; onProvenance: () => void }) {
  if (resource.state !== "ready") return <ResourceNotice resource={resource} label="Source inventory" />;
  const { inventory } = resource.data;
  if (!inventory.sources.length) return <section className={styles.notice}><strong>No sources in this project</strong><p>The KRAIL source inventory is empty.</p></section>;
  return <section className={styles.card} aria-labelledby="sources-title"><div className={styles.cardTop}><div><span className={styles.eyebrow}>Evidence</span><h2 id="sources-title">Source inventory</h2></div><button className={styles.textButton} onClick={onProvenance} type="button">Provenance</button></div><ul className={styles.sourceList}>{inventory.sources.slice(0, 5).map((source) => <li key={source.id}><strong>{source.id}</strong><span>{source.kind}</span>{source.path && <code>{source.path}</code>}</li>)}</ul></section>;
}

export function KrailLive({ projects, selectedProjectId, health, manifest, sources }: Props) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const active = projects.state === "ready" ? projects.data.find((project) => project.projectId === selectedProjectId) : undefined;
  const projectSelected = Boolean(active && health && manifest && sources);
  return <div className={styles.shell}>
    <a className={styles.skip} href="#krail-live-main">Skip to workspace</a>
    <header className={styles.header}><div><span className={styles.eyebrow}>RAIL · Live API boundary</span><h1>KRAIL workspace</h1><p>Live platform data only. No local filesystem or legacy service reads.</p></div><ProjectPicker projects={projects} selectedProjectId={selectedProjectId} /></header>
    <main id="krail-live-main" className={styles.main}>
      {!projectSelected ? <section className={styles.empty}><h2>Choose a registered project</h2><p>Once the project registry responds, health and manifest records are loaded through the versioned API.</p></section> : <div className={styles.grid}><HealthCard resource={health} /><ManifestCard resource={manifest} onProvenance={() => setDrawerOpen(true)} /><KnowledgeSurface resource={sources} onProvenance={() => setDrawerOpen(true)} /></div>}
    </main>
    {drawerOpen && <div className={styles.backdrop} onMouseDown={() => setDrawerOpen(false)} role="presentation"><aside className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="provenance-title" onMouseDown={(event) => event.stopPropagation()}><div className={styles.cardTop}><div><span className={styles.eyebrow}>Traceability</span><h2 id="provenance-title">Provenance</h2></div><button className={styles.close} type="button" onClick={() => setDrawerOpen(false)} aria-label="Close provenance">×</button></div><p>Displayed records came from the versioned KRAIL platform API. Repository paths and source records remain canonical in the registered KRAIL project.</p>{manifest?.state === "ready" && <ul className={styles.pathList}>{Object.entries(manifest.data.manifest.paths).map(([name, path]) => <li key={name}><strong>{name}</strong><code>{path}</code></li>)}</ul>}<p className={styles.muted}>Run control and live event streaming are intentionally reserved for the later M4 SSE boundary.</p></aside></div>}
  </div>;
}
