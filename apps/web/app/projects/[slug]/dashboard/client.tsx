"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { PageIntro } from "@/components/page-intro";
import { VizPanel } from "@/components/viz-panel";
import { generateDashboard } from "@/lib/api";
import type { DashboardPanel, DashboardResponse, PlannerHome } from "@/lib/types";

type DashboardClientProps = {
  slug: string;
  initialPlannerHome: PlannerHome | null;
  initialDashboard: DashboardResponse | null;
  initialErrors: string[];
};

export default function DashboardClient({
  slug,
  initialPlannerHome,
  initialDashboard,
  initialErrors,
}: DashboardClientProps) {
  const [panels, setPanels] = useState<DashboardPanel[] | null>(initialDashboard?.panels ?? null);
  const [projectName, setProjectName] = useState<string>(
    initialDashboard?.projectName || initialPlannerHome?.project?.name || "",
  );
  const [plannerHome] = useState<PlannerHome | null>(initialPlannerHome);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(initialErrors[0] ?? null);

  const controlPlane = plannerHome?.controlPlane;
  const snapshot = controlPlane?.snapshot;
  const repoHealth = plannerHome?.repoHealth;
  const fallbackReady = Boolean(plannerHome);
  const queueSummary = controlPlane?.taskCounts?.byStatus ?? {};

  const fullPanels = useMemo(() => panels?.filter((p) => p.width === "full") ?? [], [panels]);
  const halfPanels = useMemo(() => panels?.filter((p) => p.width !== "full") ?? [], [panels]);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setError(null);
    try {
      const result = await generateDashboard(slug);
      setPanels(result.panels);
      setProjectName(result.projectName);
    } catch (err) {
      setError(String(err));
    } finally {
      setGenerating(false);
    }
  }, [slug]);

  return (
    <ProjectShell slug={slug} title="Dashboard" section="dashboard">
      <PageIntro
        title={panels ? "Read the project through live charts and tables." : "Generate a project dashboard from the live DuckDB."}
        detail={panels
          ? `${projectName || "This project"} currently has ${panels.length} panel${panels.length === 1 ? "" : "s"} generated from hydrated data. Regenerate when the ontology or tables change.`
          : "This page is for exploring the project visually once data is hydrated. If the project has no panels yet, generate them from the current dataset."}
        actions={[
          { label: "Open Ontology", href: `/projects/${slug}/ontology` },
          { label: "Open Sources", href: `/projects/${slug}/sources` },
        ]}
      />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          borderBottom: "1px solid var(--border)",
          background: "var(--panel)",
          gap: 16,
        }}
      >
        <div className="mono-muted" style={{ fontSize: 11 }}>
          {panels
            ? `${panels.length} panels · live DuckDB data`
            : fallbackReady
              ? `snapshot ${snapshot?.loaded ? "loaded" : "unavailable"} · ${controlPlane?.phase ?? "phase unknown"}`
              : "No panels generated yet"}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            onClick={handleGenerate}
            disabled={generating}
            style={{
              border: "1px solid var(--border-strong)",
              background: generating ? "var(--panel-alt)" : "var(--fg)",
              color: generating ? "var(--fg)" : "var(--bg)",
              padding: "5px 16px",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              cursor: generating ? "wait" : "pointer",
              opacity: generating ? 0.8 : 1,
            }}
          >
            {generating ? "Generating…" : panels ? "Refresh Panels" : "Generate Dashboard"}
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            margin: 16,
            padding: "10px 14px",
            borderLeft: "3px solid var(--s-failed)",
            background: "var(--panel-alt)",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11,
            color: "var(--s-failed)",
          }}
        >
          {error}
        </div>
      )}

      {!panels && fallbackReady && (
        <div style={{ padding: 16, display: "grid", gap: 16 }}>
          <SectionCard eyebrow="Dashboard Status" title={projectName || plannerHome?.project?.name || slug}>
            <div style={{ display: "grid", gap: 12 }}>
              <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.7 }}>
                No curated panels are available yet, but the repo-backed control plane is still available. Use the project snapshot below to decide whether to hydrate, repair, or generate panels now.
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
                <StatusBox label="Phase" value={controlPlane?.phase ?? "unknown"} />
                <StatusBox label="Next Action" value={controlPlane?.nextAction ?? "Generate dashboard panels"} />
                <StatusBox label="Current Blocker" value={controlPlane?.currentBlocker ?? "none"} />
                <StatusBox label="Snapshot" value={snapshot?.loaded ? "loaded" : "missing"} />
              </div>
            </div>
          </SectionCard>

          <SectionCard eyebrow="Queue Snapshot" title="Planner summary from repo-backed control plane">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10 }}>
              <StatusBox label="Ready" value={String(queueSummary.ready ?? 0)} />
              <StatusBox label="Running" value={String(queueSummary.running ?? 0)} />
              <StatusBox label="Review" value={String(queueSummary.review ?? 0)} />
              <StatusBox label="Awaiting Approval" value={String(queueSummary.awaiting_approval ?? 0)} />
            </div>
            <div style={{ marginTop: 14, display: "flex", gap: 12, flexWrap: "wrap" }}>
              <Link href={`/projects/${slug}/planner`} className="overview-inline-link">
                Open Planner →
              </Link>
              <Link href={`/projects/${slug}/integrity`} className="overview-inline-link">
                Open Integrity →
              </Link>
              <Link href={`/projects/${slug}/ontology`} className="overview-inline-link">
                Open Ontology →
              </Link>
            </div>
          </SectionCard>

          <SectionCard eyebrow="Repo Health" title="What the repo snapshot says is available">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
              <StatusBox label="Local Repo" value={repoHealth?.hasLocalRepo ? "present" : "missing"} />
              <StatusBox label="rail.yaml" value={repoHealth?.hasRailYaml ? "present" : "missing"} />
              <StatusBox label="research_plan" value={repoHealth?.hasResearchPlan ? "present" : "missing"} />
            </div>
          </SectionCard>
        </div>
      )}

      {!panels && !generating && !error && !fallbackReady && (
        <EmptyState onGenerate={handleGenerate} />
      )}

      {generating && !panels && <GeneratingState />}

      {panels && (
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>
          {fullPanels.map((panel) => (
            <VizPanel
              key={panel.id}
              html={panel.html}
              title={panel.title}
              description={panel.description}
              height={panel.height ?? 300}
            />
          ))}

          {halfPanels.length > 0 && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))",
                gap: 16,
              }}
            >
              {halfPanels.map((panel) => (
                <VizPanel
                  key={panel.id}
                  html={panel.html}
                  title={panel.title}
                  description={panel.description}
                  height={panel.height ?? 260}
                />
              ))}
            </div>
          )}

          <SectionCard eyebrow="About this dashboard">
            <p
              style={{
                fontSize: 12,
                color: "var(--muted)",
                lineHeight: 1.7,
                margin: 0,
              }}
            >
              These panels are generated from the project brief and live DuckDB data. If a chart is blank, hydrate the project or regenerate the panels after the source tables change.
            </p>
          </SectionCard>
        </div>
      )}
    </ProjectShell>
  );
}

function StatusBox({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        background: "var(--panel)",
        padding: "10px 12px",
      }}
    >
      <div className="rail-label" style={{ marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontWeight: 700, fontSize: 12, lineHeight: 1.5 }}>{value}</div>
    </div>
  );
}

function EmptyState({ onGenerate }: { onGenerate: () => void }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 20,
        padding: "80px 24px",
        textAlign: "center",
      }}
    >
      <div
        style={{
          width: 48,
          height: 48,
          border: "1px solid var(--border)",
          background: "var(--panel-alt)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 22,
        }}
      >
        ▦
      </div>
      <div>
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--fg)",
            marginBottom: 8,
          }}
        >
          No Dashboard Yet
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", maxWidth: 380, lineHeight: 1.7 }}>
          The AI will read your research brief and DuckDB schema, then generate
          interactive panels backed by live data.
        </div>
      </div>
      <button
        onClick={onGenerate}
        style={{
          border: "1px solid var(--border-strong)",
          background: "var(--fg)",
          color: "var(--bg)",
          padding: "6px 16px",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          cursor: "pointer",
        }}
      >
        Generate Dashboard
      </button>
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "var(--muted)",
          letterSpacing: "0.08em",
        }}
      >
        Requires a completed hydration run · Uses the active LLM model
      </div>
    </div>
  );
}

function GeneratingState() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        padding: "80px 24px",
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 11,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--muted)",
        }}
      >
        Generating dashboard panels…
      </div>
      <div style={{ fontSize: 12, color: "var(--muted)", maxWidth: 420, lineHeight: 1.7 }}>
        The dashboard generator is reading the brief and live schema to build stakeholder-facing panels. This can take a little while on larger projects.
      </div>
    </div>
  );
}
