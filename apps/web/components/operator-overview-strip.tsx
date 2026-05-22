"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { BlockerCategory, CommandCenter } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";
import { FetchDataHydrateButton } from "@/components/fetch-data-hydrate-button";

const AUDITOR_LABELS: Record<string, string> = {
  session: "Sessions",
  planner: "Planner",
  ontology: "Ontology",
  integrity: "Integrity",
  critic: "Critic",
  closeout: "Closeout",
};

const CATEGORY_COLORS: Record<BlockerCategory, { fg: string; bg: string; border: string }> = {
  approval_required: { fg: "#92400e", bg: "rgba(251, 191, 36, 0.18)", border: "rgba(251, 191, 36, 0.55)" },
  stale_session:     { fg: "#991b1b", bg: "rgba(239, 68, 68, 0.14)",  border: "rgba(239, 68, 68, 0.55)"  },
  planner_drift:     { fg: "#991b1b", bg: "rgba(239, 68, 68, 0.14)",  border: "rgba(239, 68, 68, 0.55)"  },
  hydration_failure: { fg: "#9a3412", bg: "rgba(249, 115, 22, 0.16)", border: "rgba(249, 115, 22, 0.55)" },
  ontology_health:   { fg: "#9a3412", bg: "rgba(249, 115, 22, 0.12)", border: "rgba(249, 115, 22, 0.45)" },
  integrity_gap:     { fg: "#7c2d12", bg: "rgba(217, 119, 6, 0.15)",  border: "rgba(217, 119, 6, 0.5)"   },
  source_gap:        { fg: "#7c2d12", bg: "rgba(217, 119, 6, 0.15)",  border: "rgba(217, 119, 6, 0.5)"   },
  closeout_pending:  { fg: "#1e3a8a", bg: "rgba(59, 130, 246, 0.14)", border: "rgba(59, 130, 246, 0.45)" },
  clear:             { fg: "#065f46", bg: "rgba(16, 185, 129, 0.14)", border: "rgba(16, 185, 129, 0.45)" },
};

function BlockerCategoryChip({
  category,
  label,
  fixHref,
}: {
  category: BlockerCategory;
  label: string;
  fixHref?: string | null;
}) {
  const colors = CATEGORY_COLORS[category] ?? CATEGORY_COLORS.clear;
  const chip = (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 8px",
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 10,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        color: colors.fg,
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        borderRadius: 999,
      }}
    >
      {label}
    </span>
  );
  if (!fixHref || category === "clear") return chip;
  return (
    <Link href={fixHref as any} style={{ textDecoration: "none" }}>
      {chip}
    </Link>
  );
}

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
  const goalPhase = center.goal?.phase;
  const goalConfidence = center.goal?.dashboard?.autonomyConfidence;
  const goalBlocker = center.goal?.currentBlocker;

  return (
    <div className="operator-overview-root">
      <div className="operator-strip-row">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 24, flex: 1 }}>
          <OverviewCell label="Phase" value={goalPhase ?? derivePhase(center)} />
          <OverviewCell
            label="Confidence"
            value={typeof goalConfidence === "number" ? `${Math.round(goalConfidence * 100)}%` : "unknown"}
          />
          <OverviewCell
            label="Active worker"
            value={
              center.activeSessions.length
                ? `${center.activeSessions[0]?.role ?? "agent"} (${center.activeSessions[0]?.status ?? "unknown"})`
                : "none"
            }
          />
          <div>
            <div className="rail-label">Blocking gate</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4, maxWidth: 320 }}>
              <BlockerCategoryChip
                category={center.blockerSummary?.category ?? "clear"}
                label={center.blockerSummary?.categoryLabel ?? "Clear"}
                fixHref={center.blockerSummary?.fixHref}
              />
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--fg)",
                  lineHeight: 1.3,
                }}
              >
                {goalBlocker || center.currentBlocker || center.blockerSummary?.headline || "No active blocker."}
              </div>
              {center.blockerSummary?.fixHref && center.blockerSummary.category !== "clear" ? (
                <Link
                  href={center.blockerSummary.fixHref as any}
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    letterSpacing: "0.06em",
                    color: "var(--muted)",
                  }}
                >
                  Resolve in {center.blockerSummary.fixSection} →
                </Link>
              ) : null}
            </div>
          </div>
          <OverviewCell label="Ontology" value={hydrationState} />
          <OverviewCell label="Next action" value={center.nextAction} muted />
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
  if (center.goal?.phase) return center.goal.phase;
  // Prefer the canonical lifecycle phase from build_command_center, which uses
  // the shared infer_lifecycle_phase helper. Fall back to a UI-derived
  // approximation only when the server didn't send one (older API build).
  if (center.lifecyclePhase) return center.lifecyclePhase;
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
