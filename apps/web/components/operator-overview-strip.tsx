"use client";

import type { ReactNode } from "react";
import type { CommandCenter } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";
import { FetchDataHydrateButton } from "@/components/fetch-data-hydrate-button";

const AUDITOR_LABELS: Record<string, string> = {
  session: "Sessions",
  planner: "Planner",
  ontology: "Ontology",
  integrity: "Integrity",
  closeout: "Closeout",
};

export function OperatorOverviewStrip({
  slug,
  center,
  pipelineSlug,
  ontologyClassPreview,
}: {
  slug: string;
  center: CommandCenter;
  pipelineSlug?: string | null;
  ontologyClassPreview?: Array<{ name: string; count: number }>;
}) {
  const auditors = center.auditors ?? {};
  const hydrationState =
    auditors.ontology?.state === "not_applicable"
      ? "research-first"
      : auditors.ontology?.state ?? "unknown";

  return (
    <div className="operator-overview-root">
      <div className="operator-strip-row">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 24, flex: 1 }}>
          <OverviewCell label="Phase" value={derivePhase(center)} />
          <OverviewCell
            label="Active agents"
            value={
              center.activeSessions.length
                ? center.activeSessions
                    .map((s) => `${s.role ?? "agent"} (${s.status})`)
                    .join(", ")
                : "None"
            }
          />
          <OverviewCell
            label="Blocking gate"
            value={center.currentBlocker || center.blockerSummary?.headline || "Clear"}
          />
          <OverviewCell label="Ontology" value={hydrationState} />
          <OverviewCell label="Next" value={center.nextAction} muted />
        </div>
        <FetchDataHydrateButton slug={slug} pipelineSlug={pipelineSlug} />
      </div>

      <div className="operator-strip-panels">
        <Panel title="Auditors" slug={slug} section="integrity">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {Object.entries(auditors).map(([key, auditor]) => (
              <div key={key} className="auditor-chip">
                <MonoMuted>{AUDITOR_LABELS[key] ?? key}</MonoMuted>
                <div style={{ marginTop: 4 }}>
                  <StatusPill value={auditor.status} />
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Created outputs" slug={slug} section="artifacts">
          {center.recentArtifacts?.length ? (
            <ul className="operator-list">
              {center.recentArtifacts.slice(0, 5).map((artifact) => (
                <li key={artifact.path}>
                  <span style={{ fontWeight: 600 }}>{artifact.name}</span>
                  <MonoMuted> · {artifact.path}</MonoMuted>
                </li>
              ))}
            </ul>
          ) : (
            <MonoMuted>No artifacts yet.</MonoMuted>
          )}
        </Panel>

        <Panel title="Ontology snapshot" slug={slug} section="ontology">
          {ontologyClassPreview?.length ? (
            <div className="ontology-grid">
              {ontologyClassPreview.slice(0, 8).map((item) => (
                <div key={item.name} style={{ fontSize: 11 }}>
                  <span style={{ fontWeight: 600 }}>{item.name}</span>
                  <MonoMuted> {item.count}</MonoMuted>
                </div>
              ))}
            </div>
          ) : (
            <MonoMuted>
              Run fetch & hydrate to populate DuckDB, or open Ontology for the full explorer.
            </MonoMuted>
          )}
        </Panel>

        <Panel title="Agents working now" slug={slug} section="runs">
          {center.activeSessions.length ? (
            <ul className="operator-list">
              {center.activeSessions.map((session) => (
                <li key={session._id ?? session.id}>
                  <div style={{ fontWeight: 600 }}>
                    {(session.role ?? "agent").toUpperCase()} · {session.status}
                  </div>
                  <MonoMuted>{session.title || session.taskId || session._id}</MonoMuted>
                </li>
              ))}
            </ul>
          ) : (
            <MonoMuted>No live worker sessions. Start autopilot or launch a task.</MonoMuted>
          )}
        </Panel>
      </div>
    </div>
  );
}

function derivePhase(center: CommandCenter): string {
  if (center.activeSessions.length) return "executing";
  if (center.auditors?.closeout?.status === "ready") return "closeout-ready";
  if (center.auditors?.ontology?.status === "ready") return "ontology-ready";
  return center.project?.status ?? "active";
}

function OverviewCell({
  label,
  value,
  muted,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div>
      <div className="rail-label">{label}</div>
      <div
        style={{
          fontSize: 13,
          fontWeight: muted ? 500 : 700,
          color: muted ? "var(--muted)" : "var(--fg)",
          marginTop: 4,
          maxWidth: 280,
        }}
      >
        {value}
      </div>
    </div>
  );
}

function Panel({
  title,
  slug,
  section,
  children,
}: {
  title: string;
  slug: string;
  section: string;
  children: ReactNode;
}) {
  return (
    <div className="operator-panel">
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <span className="rail-label">{title}</span>
        <a href={`/projects/${slug}/${section}`} style={{ fontSize: 10, color: "var(--muted)" }}>
          Open →
        </a>
      </div>
      {children}
    </div>
  );
}

function MonoMuted({ children }: { children: ReactNode }) {
  return (
    <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
      {children}
    </span>
  );
}
