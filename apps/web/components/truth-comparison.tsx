"use client";

import type { ReactNode } from "react";
import type { CommandCenter } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

/**
 * Side-by-side repo / runtime / audited truth view from
 * docs/future-spec-ui-and-control-plane.md#current-truth-view.
 *
 * Each column is sourced from a distinct authority so an operator can compare
 * what's durable (repo files), what's live (runtime sessions), and what's
 * certified (audited reality). Divergence is the signal that something has
 * drifted and needs reconciliation — the same data is also pumped into the
 * blocker categorizer, but this view exists so a human can confirm at a glance.
 */
export function TruthComparison({ center }: { center: CommandCenter }) {
  const repo = center.repoHealth ?? { hasLocalRepo: false, hasRailYaml: false, hasResearchPlan: false };
  const reality = center.projectReality;
  const audit = center.auditedTruth as Record<string, any> | undefined;
  const auditors = center.auditors ?? {};

  const driftSignals = reality
    ? [
        reality.duplicateTaskFileCount && `${reality.duplicateTaskFileCount} duplicate task file(s)`,
        reality.taskSessionMismatchCount && `${reality.taskSessionMismatchCount} task/session mismatch(es)`,
        reality.staleRuntimeSessionCount && `${reality.staleRuntimeSessionCount} stale runtime session(s)`,
        reality.staleAuditSessionCount && `${reality.staleAuditSessionCount} stale audit(s)`,
        reality.ontologyArtifactDriftCount && `${reality.ontologyArtifactDriftCount} ontology artifact drift`,
      ].filter(Boolean)
    : [];

  const auditorChips = Object.entries(auditors).map(([key, value]) => (
    <Row key={key} label={key} value={<StatusPill value={value?.status ?? "unknown"} />} />
  ));

  return (
    <div className="truth-comparison">
      <div className="rail-label" style={{ padding: "10px 14px 4px" }}>
        Current truth — repo / runtime / audited
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 0,
          borderTop: "1px solid var(--border)",
        }}
      >
        <Column title="Repo truth" sub="durable">
          <Row label="rail.yaml" value={<YesNo ok={repo.hasRailYaml} />} />
          <Row label="research_plan/" value={<YesNo ok={repo.hasResearchPlan} />} />
          <Row label="local repo" value={<YesNo ok={repo.hasLocalRepo} />} />
          <Row
            label="current plan"
            value={
              <span style={{ fontSize: 11, color: center.currentPlan?.content ? "var(--fg)" : "var(--muted)" }}>
                {center.currentPlan?.content ? "present" : "missing"}
              </span>
            }
          />
        </Column>

        <Column title="Runtime truth" sub="live">
          <Row label="active sessions" value={<Num value={center.activeSessions?.length ?? 0} />} />
          <Row label="pending approvals" value={<Num value={center.pendingApprovals?.length ?? 0} />} />
          <Row label="stale sessions" value={<Num value={reality?.staleRuntimeSessionCount ?? 0} />} />
          <Row
            label="drift detected"
            value={
              reality?.hasDrift ? (
                <StatusPill value="drifted" />
              ) : (
                <StatusPill value="clear" />
              )
            }
          />
          {driftSignals.length > 0 ? (
            <div style={{ padding: "4px 12px 8px", fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>
              {driftSignals.join(" · ")}
            </div>
          ) : null}
        </Column>

        <Column title="Audited truth" sub="certified">
          {auditorChips.length > 0 ? (
            auditorChips
          ) : (
            <div style={{ padding: "10px 12px", color: "var(--muted)", fontSize: 11 }}>
              No auditor runs yet.
            </div>
          )}
          <Row
            label="latest audit"
            value={
              <span style={{ fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>
                {audit?.session?.id ? String(audit.session.id).slice(-8) : "none"}
              </span>
            }
          />
          <Row
            label="audit blocker"
            value={
              <span style={{ fontSize: 11, color: audit?.currentBlocker ? "var(--error)" : "var(--muted)" }}>
                {audit?.currentBlocker ? String(audit.currentBlocker).slice(0, 60) : "clear"}
              </span>
            }
          />
        </Column>
      </div>
    </div>
  );
}

function Column({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  return (
    <div style={{ borderRight: "1px solid var(--border)" }}>
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", background: "var(--panel)" }}>
        <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 700, color: "var(--fg)" }}>
          {title}
        </div>
        <div style={{ fontSize: 9, color: "var(--muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{sub}</div>
      </div>
      <div>{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "6px 12px",
        borderBottom: "1px solid var(--border)",
        fontSize: 12,
      }}
    >
      <span style={{ color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 10, letterSpacing: "0.05em" }}>
        {label}
      </span>
      {value}
    </div>
  );
}

function YesNo({ ok }: { ok: boolean }) {
  return <StatusPill value={ok ? "present" : "missing"} />;
}

function Num({ value }: { value: number }) {
  return (
    <strong style={{ fontSize: 13, color: value > 0 ? "var(--fg)" : "var(--muted)" }}>{value}</strong>
  );
}
