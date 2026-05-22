import Link from "next/link";
import type { CommandCenter, GoalBundle } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

function percent(value?: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "0%";
  return `${Math.round(value)}%`;
}

function confidenceLabel(value?: number | null): string {
  if (typeof value !== "number") return "unknown";
  if (value >= 0.8) return "high";
  if (value >= 0.55) return "medium";
  if (value >= 0.3) return "low";
  return "fragile";
}

export function GoalModePanel({
  slug,
  center,
  goal,
}: {
  slug: string;
  center: CommandCenter;
  goal?: GoalBundle | null;
}) {
  const goalSummary = center.goal;
  const retryBudget = goalSummary?.retryBudget;
  const success = goalSummary?.success;
  const dashboard = goalSummary?.dashboard;
  const tracks = goalSummary?.tracks;
  const criteria = goal?.state?.success?.criteria ?? [];

  if (!goalSummary && !goal) {
    return (
      <div style={{ padding: "12px 14px" }}>
        <div className="mono-muted" style={{ marginBottom: 12, fontSize: 10 }}>[GOAL MODE]</div>
        <div style={{ fontWeight: 600, color: "var(--fg)" }}>No durable goal contract yet.</div>
        <div className="mono-muted" style={{ marginTop: 6 }}>
          Configure `POST /projects/{slug}/goal` to turn autopilot into contract-backed goal mode.
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: "12px 14px", display: "grid", gap: 14 }}>
      <div>
        <div className="mono-muted" style={{ marginBottom: 12, fontSize: 10 }}>[GOAL MODE]</div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <div style={{ fontWeight: 700, color: "var(--fg)", lineHeight: 1.35 }}>
            {goalSummary?.objective ?? goal?.contract?.objective ?? "Goal contract"}
          </div>
          <StatusPill value={goalSummary?.phase ?? goal?.state?.phase ?? "unknown"} />
        </div>
        <div className="mono-muted" style={{ marginTop: 8 }}>
          {goalSummary?.currentBlocker || center.blockerSummary?.headline || "Autonomy is clear."}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 10 }}>
        <Metric label="Criteria" value={percent(success?.percent)} />
        <Metric
          label="Retry budget"
          value={
            retryBudget
              ? `${retryBudget.remaining}/${retryBudget.max}`
              : "n/a"
          }
        />
        <Metric label="Confidence" value={confidenceLabel(dashboard?.autonomyConfidence)} />
        <Metric
          label="Runs"
          value={`${dashboard?.successfulRuns ?? 0}/${dashboard?.failedRuns ?? 0}`}
          sub="success/fail"
        />
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        <TrackRow label="Research track" status={tracks?.research.status} blocker={tracks?.research.blocker} />
        <TrackRow label="Platform repair" status={tracks?.platformRepair.status} blocker={tracks?.platformRepair.blocker} />
      </div>

      {criteria.length ? (
        <div>
          <div className="rail-label" style={{ marginBottom: 6 }}>Success Gates</div>
          <div style={{ display: "grid", gap: 6 }}>
            {criteria.slice(0, 4).map((criterion) => (
              <div
                key={criterion.criterion}
                style={{
                  border: "1px solid var(--border)",
                  background: "rgba(255,255,255,0.02)",
                  padding: "8px 10px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <div style={{ fontWeight: 600, color: "var(--fg)" }}>{criterion.criterion}</div>
                  <StatusPill value={criterion.satisfied ? "ready" : "blocked"} />
                </div>
                <div className="mono-muted" style={{ marginTop: 4 }}>{criterion.reason}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {goal?.files?.goalMd ? (
        <Link href={`/projects/${slug}/planner`} style={{ fontSize: 11, color: "var(--muted)" }}>
          Goal files persisted in repo state. Open planner for task-level execution →
        </Link>
      ) : null}
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ border: "1px solid var(--border)", padding: "8px 10px", background: "rgba(255,255,255,0.02)" }}>
      <div className="rail-label">{label}</div>
      <div style={{ marginTop: 6, fontSize: 16, fontWeight: 700, color: "var(--fg)" }}>{value}</div>
      {sub ? <div className="mono-muted" style={{ marginTop: 4 }}>{sub}</div> : null}
    </div>
  );
}

function TrackRow({ label, status, blocker }: { label: string; status?: string; blocker?: string | null }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
      <div>
        <div style={{ fontWeight: 600, color: "var(--fg)" }}>{label}</div>
        {blocker ? <div className="mono-muted" style={{ marginTop: 4 }}>{blocker}</div> : null}
      </div>
      <StatusPill value={status ?? "unknown"} />
    </div>
  );
}
