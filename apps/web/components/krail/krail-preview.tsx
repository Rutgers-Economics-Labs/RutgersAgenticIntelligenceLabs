"use client";

import { useState } from "react";
import type { KrailArea, KrailPreviewModel, KrailViewState, ProvenanceItem } from "@/lib/krail/types";
import styles from "./krail-preview.module.css";

const NAVIGATION: Array<{ id: KrailArea; label: string; hint: string }> = [
  { id: "explore", label: "Explore", hint: "Map the research space" },
  { id: "analyze", label: "Analyze", hint: "Test the reasoning" },
  { id: "evidence", label: "Evidence", hint: "Trace claims to sources" },
  { id: "workflows", label: "Workflows", hint: "Run repeatable work" },
  { id: "control-plane", label: "Control Plane", hint: "Operate the project" },
];

function StateIllustration({ state }: { state: Exclude<KrailViewState, "ready"> }) {
  const copy = {
    loading: { title: "Preparing the workspace", detail: "The project context is being assembled." },
    error: { title: "Preview data could not load", detail: "This mock state shows a recoverable adapter failure." },
    empty: { title: "Nothing has been added yet", detail: "Start with a question, source, or workflow to create project context." },
  }[state];

  return (
    <section className={styles.statePanel} aria-live="polite">
      <span className={`${styles.stateMark} ${state === "error" ? styles.stateMarkError : ""}`} aria-hidden="true">
        {state === "loading" ? "···" : state === "error" ? "!" : "○"}
      </span>
      <h2>{copy.title}</h2>
      <p>{copy.detail}</p>
      {state !== "loading" && <button type="button" className={styles.secondaryButton}>Try again</button>}
    </section>
  );
}

function StatusTag({ children }: { children: string }) {
  const tone = children === "Attention" ? styles.warningTag : styles.reviewTag;
  return <span className={`${styles.statusTag} ${tone}`}>{children}</span>;
}

function ProvenanceRow({ item }: { item: ProvenanceItem }) {
  return (
    <li className={styles.provenanceItem}>
      <div className={styles.provenanceHeading}>
        <strong>{item.title}</strong>
        <span className={item.status === "verified" ? styles.verified : styles.review}>{item.status}</span>
      </div>
      <span>{item.source} · {item.retrievedAt}</span>
      <p>{item.note}</p>
    </li>
  );
}

export function KrailPreview({ model }: { model: KrailPreviewModel }) {
  const [area, setArea] = useState<KrailArea>("explore");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [viewState, setViewState] = useState<KrailViewState>("ready");
  const panel = model.panels[area];

  return (
    <div className={styles.pageShell}>
      <a className={styles.skipLink} href="#krail-main">Skip to workspace</a>
      <aside className={styles.sidebar} aria-label="KRAIL workspace navigation">
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">K</span>
          <div><span className={styles.kicker}>RAIL · Preview</span><strong>KRAIL</strong></div>
        </div>

        <div className={styles.projectSummary}>
          <span className={styles.kicker}>Active project</span>
          <strong>{model.project.name}</strong>
          <span>{model.project.slug}</span>
        </div>

        <nav className={styles.navigation} aria-label="Research areas">
          {NAVIGATION.map((item, index) => (
            <button
              key={item.id}
              type="button"
              className={area === item.id ? `${styles.navItem} ${styles.navItemActive}` : styles.navItem}
              aria-current={area === item.id ? "page" : undefined}
              onClick={() => setArea(item.id)}
            >
              <span className={styles.navNumber}>0{index + 1}</span>
              <span><strong>{item.label}</strong><small>{item.hint}</small></span>
            </button>
          ))}
        </nav>

        <div className={styles.sidebarFooter}>
          <span className={styles.liveDot} aria-hidden="true" />
          Mock boundary active
        </div>
      </aside>

      <div className={styles.workspace}>
        <header className={styles.header}>
          <div>
            <span className={styles.kicker}>Research operating system</span>
            <h1>{model.project.name}</h1>
          </div>
          <div className={styles.headerActions}>
            <label className={styles.stateSelectLabel}>
              <span className="sr-only">Preview state</span>
              <select value={viewState} onChange={(event) => setViewState(event.target.value as KrailViewState)}>
                <option value="ready">Ready state</option>
                <option value="loading">Loading state</option>
                <option value="error">Error state</option>
                <option value="empty">Empty state</option>
              </select>
            </label>
            <button
              type="button"
              className={styles.provenanceButton}
              aria-expanded={drawerOpen}
              aria-controls="krail-provenance"
              onClick={() => setDrawerOpen(true)}
            >
              Provenance <span>{model.provenance.length}</span>
            </button>
          </div>
        </header>

        <main id="krail-main" className={styles.main}>
          {viewState !== "ready" ? <StateIllustration state={viewState} /> : <>
            <section className={styles.healthCard} aria-labelledby="health-heading">
              <div className={styles.healthHeading}>
                <div><span className={styles.kicker}>Project health</span><h2 id="health-heading">{model.health.status === "healthy" ? "Research is in good standing" : "Project needs attention"}</h2></div>
                <div className={styles.score} aria-label={`Health score ${model.health.score} out of 100`}><strong>{model.health.score}</strong><span>/ 100</span></div>
              </div>
              <p>{model.health.summary}</p>
              <div className={styles.metricGrid}>
                {model.health.metrics.map((metric) => <div className={styles.metric} key={metric.label}>
                  <span>{metric.label}</span><strong>{metric.value}</strong><small className={metric.tone === "warning" ? styles.metricWarning : undefined}>{metric.detail}</small>
                </div>)}
              </div>
              <span className={styles.updated}>{model.health.updatedAt}</span>
            </section>

            <section className={styles.contentGrid} aria-labelledby="area-heading">
              <article className={styles.areaCard}>
                <span className={styles.kicker}>{panel.eyebrow}</span>
                <h2 id="area-heading">{panel.title}</h2>
                <p>{panel.description}</p>
                <dl className={styles.detailList}>
                  {panel.rows.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}{row.status && <StatusTag>{row.status}</StatusTag>}</dd></div>)}
                </dl>
                <button type="button" className={styles.primaryButton}>{panel.primaryLabel}<span aria-hidden="true">→</span></button>
              </article>

              <article className={styles.activityCard} aria-labelledby="activity-heading">
                <div className={styles.cardTitleRow}><div><span className={styles.kicker}>Project feed</span><h2 id="activity-heading">Recent research activity</h2></div><button type="button" className={styles.textButton}>View all</button></div>
                <ol className={styles.activityList}>
                  {model.activity.map((event) => <li key={event.id}>
                    <time>{event.timestamp}</time><div><strong>{event.title}</strong><p>{event.description}</p><span>{event.area.replace("-", " ")}</span></div>
                  </li>)}
                </ol>
              </article>
            </section>
          </>}
        </main>
      </div>

      {drawerOpen && <div className={styles.drawerLayer} role="presentation" onMouseDown={() => setDrawerOpen(false)}>
        <aside id="krail-provenance" className={styles.drawer} role="dialog" aria-modal="true" aria-label="Provenance ledger" onMouseDown={(event) => event.stopPropagation()}>
          <div className={styles.drawerHeader}><div><span className={styles.kicker}>Evidence ledger</span><h2>Provenance</h2></div><button type="button" className={styles.closeButton} onClick={() => setDrawerOpen(false)} aria-label="Close provenance drawer">×</button></div>
          <p className={styles.drawerIntro}>Every result in this preview resolves to a source record. The data below is intentionally supplied by the mock adapter.</p>
          <ul className={styles.provenanceList}>{model.provenance.map((item) => <ProvenanceRow item={item} key={item.id} />)}</ul>
        </aside>
      </div>}
    </div>
  );
}
