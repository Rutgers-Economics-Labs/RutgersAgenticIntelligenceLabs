"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { BlockerCategory, CommandCenter } from "@/lib/types";
import { FetchDataHydrateButton } from "@/components/fetch-data-hydrate-button";

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
  const phaseDisplay = compactPhase(goalPhase ?? derivePhase(center));
  const confidenceDisplay = compactConfidence(goalConfidence);
  const workerDisplay = compactWorker(center.activeSessions[0]);
  const ontologyDisplay = compactOntology(hydrationState, classPreviewItem(slug, ontologyClassPreview, hydrationState).detail);
  const nextActionDisplay = compactNextAction(center.nextAction);
  const blockerHeadline = compactBlocker(
    goalBlocker || center.currentBlocker || center.blockerSummary?.headline || "No active blocker.",
  );
  const focusItems = [
    center.pendingApprovals.length
      ? {
          title: `${center.pendingApprovals.length} approval${center.pendingApprovals.length === 1 ? "" : "s"} waiting`,
          detail: "Review these before the planner can dispatch more work.",
          href: `/projects/${slug}/review`,
        }
      : null,
    center.recommendedRepairTask
      ? {
          title: center.recommendedRepairTask.title,
          detail: center.recommendedRepairTask.reason ?? "Repair work is queued before research should continue.",
          href: `/projects/${slug}/integrity`,
        }
      : null,
    classPreviewItem(slug, ontologyClassPreview, hydrationState),
    center.activeSessions.length
      ? {
          title: `${center.activeSessions.length} live worker session${center.activeSessions.length === 1 ? "" : "s"}`,
          detail: "Open Runs to inspect live execution and post-run review state.",
          href: `/projects/${slug}/runs`,
        }
      : {
          title: "No workers are running",
          detail: "Use Planner or Launch when the queue is ready to resume execution.",
          href: `/projects/${slug}/planner`,
        },
  ].filter(Boolean) as Array<{ title: string; detail: string; href: string }>;

  const signalItems = [
    {
      label: "Plan summary",
      value: center.currentPlan.summary || center.nextAction || "No durable summary yet.",
    },
    {
      label: "Task queue",
      value: `${center.taskCounts.byStatus.running ?? 0} running · ${center.taskCounts.byStatus.awaiting_approval ?? 0} waiting · ${center.taskCounts.byStatus.ready ?? 0} ready`,
    },
    {
      label: "Evidence",
      value: `${center.recentArtifacts.length} recent artifacts · ${center.sourceSummary.count} tracked sources`,
    },
  ];

  return (
    <div className="operator-overview-root">
      {center.missionBrief ? (
        <div className="operator-brief-panel">
          <div className="operator-brief-header">
            <div className="rail-label">Planner Brief</div>
            {(center.missionBrief.sourceRole || center.missionBrief.sourceStatus) ? (
              <div className="mono-muted">
                from latest {center.missionBrief.sourceRole ?? "agent"} session
                {center.missionBrief.sourceStatus ? ` · ${center.missionBrief.sourceStatus.replaceAll("_", " ")}` : ""}
              </div>
            ) : null}
          </div>
          <div className="operator-brief-grid">
            <div className="operator-brief-block">
              <div className="rail-label">What is here now</div>
              <p className="operator-brief-copy">{center.missionBrief.current}</p>
            </div>
            <div className="operator-brief-block">
              <div className="rail-label">What should happen next</div>
              <p className="operator-brief-copy">{center.missionBrief.next}</p>
            </div>
          </div>
        </div>
      ) : null}
      <div className="operator-strip-row">
        <div className="operator-summary-grid">
          <OverviewCell label="Phase" value={phaseDisplay} />
          <OverviewCell
            label="Confidence"
            value={confidenceDisplay}
          />
          <OverviewCell
            label="Active worker"
            value={workerDisplay}
          />
          <OverviewCell label="Ontology" value={ontologyDisplay} />
          <div className="operator-blocker-card">
            <div className="rail-label">Blocking gate</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6, maxWidth: 480 }}>
              <BlockerCategoryChip
                category={center.blockerSummary?.category ?? "clear"}
                label={center.blockerSummary?.categoryLabel ?? "Clear"}
                fixHref={center.blockerSummary?.fixHref}
              />
              <div className="operator-blocker-copy">{blockerHeadline}</div>
              {center.blockerSummary?.fixHref && center.blockerSummary.category !== "clear" ? (
                <Link href={center.blockerSummary.fixHref as any} className="operator-blocker-link">
                  Resolve in {center.blockerSummary.fixSection} →
                </Link>
              ) : null}
            </div>
          </div>
          <OverviewCell label="Next action" value={nextActionDisplay} muted />
        </div>
        <FetchDataHydrateButton slug={slug} pipelineSlug={pipelineSlug} />
      </div>

      <div className="operator-strip-panels">
        <Panel title="What Needs Action" slug={slug} section="review">
          <ul className="operator-focus-list">
            {focusItems.slice(0, 3).map((item) => (
              <li key={item.title} className="operator-focus-item">
                <div style={{ fontWeight: 700, color: "var(--fg)", lineHeight: 1.35 }}>{item.title}</div>
                <MonoMuted>{item.detail}</MonoMuted>
                <Link href={item.href as any} className="overview-inline-link">
                  Open →
                </Link>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Project Signal" slug={slug} section="integrity">
          <ul className="operator-focus-list">
            {signalItems.map((item) => (
              <li key={item.label} className="operator-focus-item">
                <div className="rail-label">{item.label}</div>
                <div style={{ fontWeight: 700, color: "var(--fg)", lineHeight: 1.35 }}>{item.value}</div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}

function compactPhase(value: string): string {
  const phase = value.replaceAll("_", " ").toLowerCase();
  if (phase.includes("source discovery")) return "Discover";
  if (phase.includes("execut")) return "Running";
  if (phase.includes("closeout")) return "Closeout";
  if (phase.includes("review")) return "Review";
  if (phase.includes("closed")) return "Closed";
  return titleCaseWords(phase);
}

function compactConfidence(value?: number | null): string {
  if (typeof value !== "number") return "Unscored";
  if (value >= 0.8) return "High";
  if (value >= 0.55) return "Medium";
  if (value >= 0.3) return "Low";
  return "Fragile";
}

function compactWorker(session?: { role?: string; status?: string } | null): string {
  if (!session) return "Idle";
  const role = session.role ? titleCaseWords(session.role.replaceAll("_", " ")) : "Agent";
  const status = session.status ? compactPhase(session.status) : "Live";
  return `${role} · ${status}`;
}

function compactOntology(state: string, detail?: string): string {
  if (state === "stale_on_this_device" || state === "not_hydrated") return "Needs hydration";
  if (state === "research-first" || state === "not_applicable") return "Not needed";
  if (state === "ready" || state === "hydrated") return "Ready";
  if (detail?.toLowerCase().includes("class data")) return "Ready";
  return titleCaseWords(state.replaceAll("_", " "));
}

function compactNextAction(value: string): string {
  const text = value.replace(/\s+/g, " ").trim();
  if (!text) return "Open planner";
  if (/review pending approvals/i.test(text)) return "Review approvals";
  if (/hydrate/i.test(text)) return "Hydrate data";
  return text.length > 42 ? `${text.slice(0, 39)}...` : text;
}

function compactBlocker(value: string): string {
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > 120 ? `${text.slice(0, 117)}...` : text;
}

function titleCaseWords(value: string): string {
  return value
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function classPreviewItem(
  slug: string,
  ontologyClassPreview: Array<{ name: string; count: number }> | undefined,
  hydrationState: string,
): { title: string; detail: string; href: string } {
  if (ontologyClassPreview?.length) {
    const primary = ontologyClassPreview
      .slice(0, 3)
      .map((item) => `${item.name} ${item.count}`)
      .join(" · ");
    return {
      title: "Ontology has local class data",
      detail: primary,
      href: `/projects/${slug}/ontology`,
    };
  }
  return {
    title: hydrationState === "stale_on_this_device" ? "Ontology needs local hydration" : "Ontology is still sparse",
    detail: "Hydrate locally or open Ontology for the explorer and class coverage details.",
    href: `/projects/${slug}/ontology`,
  };
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
    <div className="operator-stat-card">
      <div className="rail-label">{label}</div>
      <div className={`operator-stat-value${muted ? " muted" : ""}`} style={{ maxWidth: 280 }}>
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
