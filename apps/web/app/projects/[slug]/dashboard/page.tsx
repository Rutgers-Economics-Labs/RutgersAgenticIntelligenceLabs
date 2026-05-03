"use client";

import { useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { VizPanel } from "@/components/viz-panel";
import { generateDashboard } from "@/lib/api";
import type { DashboardPanel } from "@/lib/types";

export default function DashboardPage() {
  const { slug } = useParams() as { slug: string };
  const [panels, setPanels] = useState<DashboardPanel[] | null>(null);
  const [projectName, setProjectName] = useState<string>("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  // Separate full-width and half-width panels
  const fullPanels = panels?.filter((p) => p.width === "full") ?? [];
  const halfPanels = panels?.filter((p) => p.width !== "full") ?? [];

  return (
    <ProjectShell slug={slug} title="Dashboard" section="dashboard">
      {/* ── Header strip ─────────────────────────────────────────────── */}
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
        <div>
          <span className="rail-label">AI Dashboard</span>
          {projectName && (
            <span
              style={{
                marginLeft: 12,
                fontSize: 13,
                fontWeight: 600,
                color: "var(--fg)",
              }}
            >
              {projectName}
            </span>
          )}
          {panels && (
            <span
              style={{
                marginLeft: 10,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                color: "var(--muted)",
              }}
            >
              {panels.length} panels · live DuckDB data
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {panels && (
            <button
              onClick={handleGenerate}
              disabled={generating}
              style={{
                border: "1px solid var(--border)",
                background: "var(--panel-alt)",
                color: "var(--fg)",
                padding: "4px 12px",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                cursor: generating ? "wait" : "pointer",
                opacity: generating ? 0.5 : 1,
              }}
            >
              Regenerate
            </button>
          )}
          {!panels && (
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
              }}
            >
              {generating ? "Generating…" : "Generate Dashboard"}
            </button>
          )}
        </div>
      </div>

      {/* ── States ───────────────────────────────────────────────────── */}

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

      {!panels && !generating && !error && (
        <EmptyState onGenerate={handleGenerate} />
      )}

      {generating && !panels && <GeneratingState />}

      {/* ── Dashboard grid ───────────────────────────────────────────── */}
      {panels && (
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Full-width panels */}
          {fullPanels.map((panel) => (
            <VizPanel
              key={panel.id}
              html={panel.html}
              title={panel.title}
              description={panel.description}
              height={panel.height ?? 300}
            />
          ))}

          {/* Half-width panels grid */}
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
              This dashboard was generated by AI from the project's research brief and live DuckDB data.
              Each panel runs a SQL query against the hydrated knowledge graph in real time.
              Charts may not appear if the database is not loaded — run a hydration job first.
            </p>
          </SectionCard>
        </div>
      )}
    </ProjectShell>
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
          fontSize: 10,
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          color: "var(--muted)",
          animation: "pulse 1.5s ease-in-out infinite",
        }}
      >
        Reading brief · Analyzing schema · Generating visualizations…
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 8,
          opacity: 0.25,
          marginTop: 16,
        }}
      >
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            style={{
              height: i % 3 === 0 ? 140 : 80,
              gridColumn: i % 3 === 0 ? "span 3" : "span 1",
              background: "var(--border)",
            }}
          />
        ))}
      </div>
      <style>{`@keyframes pulse { 0%,100% { opacity: .4 } 50% { opacity: 1 } }`}</style>
    </div>
  );
}
