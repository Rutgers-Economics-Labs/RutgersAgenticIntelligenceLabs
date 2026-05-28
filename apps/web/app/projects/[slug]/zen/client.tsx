"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchZenMode } from "@/lib/api";
import type { ZenResponse } from "@/lib/types";
import {
  CheckCircle,
  AlertCircle,
  Clock,
  Pause,
  Search,
  Menu,
  ChevronRight,
  Database,
  FileText,
  Activity
} from "lucide-react";
import { clsx } from "clsx";
import { StatusPill } from "@/components/status-pill";

type ZenClientProps = {
  slug: string;
  initialData: ZenResponse | null;
  initialError: string | null;
};

export default function ZenClient({ slug, initialData, initialError }: ZenClientProps) {
  const [data, setData] = useState<ZenResponse | null>(initialData);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("evidence");
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState<string | null>(initialError);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetchZenMode(slug);
        setData(res);
        setError(null);
      } catch (err) {
        const message = err instanceof Error && err.message ? err.message : String(err);
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    if (!initialData) {
      void load();
    }
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [slug, initialData]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--bg)]">
        <div className="rail-label animate-pulse">Entering Zen Mode...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[var(--bg)] space-y-4">
        <div className="text-red-500 font-bold rail-label">Project load failed</div>
        {error && (
          <pre
            style={{
              maxWidth: 720,
              margin: 0,
              padding: 12,
              overflowX: "auto",
              background: "var(--panel)",
              border: "1px solid var(--border)",
              fontSize: 12,
              whiteSpace: "pre-wrap",
              color: "var(--muted)",
            }}
          >
            {error}
          </pre>
        )}
        <Link href={`/projects/${slug}`} className="text-xs underline rail-label opacity-60">
          Return to Overview
        </Link>
      </div>
    );
  }

  const { project, objective, activeRun, latestTruth, nextDecision, plan, attention, artifacts } = data;

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg)] text-[var(--fg)]">
      <div className="flex-1 flex flex-col min-w-0 relative">
        <header
          style={{
            height: 40,
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 16px",
            borderBottom: "1px solid var(--border)",
            background: "var(--panel)",
          }}
        >
          <div className="flex items-center gap-4">
            <Link href="/" style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <img
                src="/rel-logo.jpeg"
                alt="REL"
                style={{ width: 24, height: 24, objectFit: "contain", background: "#fff", border: "1px solid var(--border)" }}
              />
              <span className="rail-label" style={{ fontSize: 11 }}>RAIL</span>
            </Link>
            <span style={{ color: "var(--border)" }}>·</span>
            <span className="rail-label" style={{ fontSize: 10, color: "var(--muted)" }}>{slug}</span>
            <span style={{ color: "var(--border)" }}>·</span>
            <div className="flex items-center gap-2">
              <span className="rail-label text-[9px] opacity-60">Phase</span>
              <span className="text-[11px] font-bold uppercase tracking-wider">{project.phase}</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="rail-label text-[9px] opacity-60">Health</span>
              <StatusPill value={project.health} />
            </div>
            <span style={{ color: "var(--border)" }}>·</span>
            <Link
              href={`/projects/${slug}`}
              style={{
                border: "1px solid var(--border-strong)",
                padding: "3px 10px",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--fg)",
              }}
            >
              Exit Zen
            </Link>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto pb-40 scroll-smooth">
          <div className="max-w-2xl mx-auto px-6 py-24 space-y-24">
            {error && (
              <section className="space-y-4">
                <div className="rail-label text-[var(--accent)] font-bold tracking-[0.2em]">Transport Warning</div>
                <div className="rail-panel p-4" style={{ borderLeft: "3px solid var(--accent)", borderRadius: 0 }}>
                  <div className="text-sm opacity-80">
                    Zen Mode is showing the last good repo-backed snapshot while the live refresh request is failing.
                  </div>
                  <pre
                    style={{
                      margin: "12px 0 0",
                      padding: 12,
                      overflowX: "auto",
                      background: "var(--panel-alt)",
                      border: "1px solid var(--border)",
                      fontSize: 11,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {error}
                  </pre>
                </div>
              </section>
            )}

            <section className="space-y-6">
              <div className="rail-label opacity-40 text-[10px] tracking-[0.2em]">Objective</div>
              <h1
                className="text-4xl font-semibold leading-tight tracking-tight text-[var(--fg)]"
                style={{ fontFamily: "Lora, Georgia, serif" }}
              >
                {objective}
              </h1>
            </section>

            {nextDecision && (
              <section className="space-y-6">
                <div className="rail-label text-[var(--accent)] font-bold tracking-[0.2em]">Attention Required</div>
                <div className="p-8 rail-panel shadow-lg space-y-6" style={{ borderLeft: "3px solid var(--accent)", borderRadius: 0 }}>
                  <div className="flex items-start gap-6">
                    <div className="p-3 bg-[var(--accent)] text-white">
                      <AlertCircle size={24} />
                    </div>
                    <div className="space-y-2">
                      <div className="font-bold text-xl leading-snug">{nextDecision.prompt}</div>
                      <div className="text-sm opacity-70">A project decision is pending your review.</div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 pt-2">
                    {nextDecision.actions.map((action: any, idx: number) => (
                      <button
                        key={idx}
                        className={clsx(
                          "px-6 py-2.5 font-mono text-[10px] font-bold uppercase tracking-widest transition-all",
                          action.value === "approve" ? "bg-[var(--fg)] text-[var(--bg)]" : "bg-[var(--panel-alt)] border border-[var(--border)]"
                        )}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                </div>
              </section>
            )}

            <section className="space-y-8">
              <div className="rail-label opacity-40 text-[10px] tracking-[0.2em]">Active Agent</div>
              {activeRun ? (
                <div className="rail-panel shadow-sm space-y-0" style={{ borderRadius: 0 }}>
                  <div className="p-6 flex items-center justify-between border-b border-[var(--border)]">
                    <div className="flex items-center gap-5">
                      <div className="w-10 h-10 border border-[var(--border)] bg-[var(--panel-alt)] flex items-center justify-center text-[var(--fg)]">
                        <Activity size={20} />
                      </div>
                      <div>
                        <div className="font-bold text-base leading-none">{activeRun.label}</div>
                        <div className="text-[10px] opacity-40 font-mono uppercase tracking-widest mt-2">{activeRun.role} • {activeRun.runner}</div>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <StatusPill value={activeRun.status} />
                      <div className="flex items-center gap-1.5 text-[9px] font-mono opacity-50 uppercase tracking-tighter">
                        <Clock size={10} />
                        {Math.floor(activeRun.elapsedSeconds / 60)}:{(activeRun.elapsedSeconds % 60).toString().padStart(2, "0")} elapsed
                      </div>
                    </div>
                  </div>

                  <div className="p-6 bg-[var(--panel-alt)] font-mono text-[11px] leading-relaxed opacity-80 overflow-hidden">
                    <span className="opacity-30 mr-2 uppercase tracking-tighter">Output Trace:</span>
                    {activeRun.lastEvent || "Agent is thinking..."}
                  </div>

                  <div className="p-4 flex items-center gap-3 border-t border-[var(--border)]">
                    <button className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider px-5 py-2 bg-[var(--panel)] border border-[var(--border)] hover:bg-[var(--panel-alt)]">
                      <Pause size={12} /> Pause
                    </button>
                    <Link
                      href={`/projects/${slug}/runs/${encodeURIComponent(activeRun.id)}`}
                      className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider px-5 py-2 bg-[var(--panel)] border border-[var(--border)] hover:bg-[var(--panel-alt)]"
                    >
                      Inspect
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="p-16 border border-dashed border-[var(--border)] flex flex-col items-center justify-center text-center space-y-4 opacity-40">
                  <div className="opacity-20"><CheckCircle size={40} /></div>
                  <div className="rail-label text-[10px]">Awaiting Agent Activation</div>
                </div>
              )}
            </section>

            <section className="space-y-10">
              <div className="rail-label opacity-40 text-[10px] tracking-[0.2em]">Latest Findings</div>
              <div className="border-t border-[var(--border)]">
                {latestTruth.length > 0 ? latestTruth.map((truth, idx) => (
                  <div key={idx} className="activity-row" style={{ gridTemplateColumns: "100px 1fr", padding: "20px 0" }}>
                    <div className="activity-ts flex flex-col items-start gap-2 pr-4">
                      <StatusPill value={truth.verified ? "verified" : "candidate"} />
                      <div className="text-[9px] opacity-40 font-mono font-bold tracking-tighter">{Math.round(truth.confidence * 100)}% CONFIDENCE</div>
                    </div>
                    <div className="activity-content space-y-4">
                      <div className="text-lg leading-relaxed text-[var(--fg)]" style={{ fontFamily: "Lora, Georgia, serif" }}>
                        {truth.claim}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {truth.evidenceRefs.map((ref, ridx) => (
                          <div key={ridx} className="text-[9px] font-mono bg-[var(--panel-alt)] border border-[var(--border)] px-2.5 py-1 opacity-60 hover:opacity-100 cursor-pointer transition-opacity">
                            {ref.split("/").pop()}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )) : (
                  <div className="py-20 text-center text-[10px] opacity-40 font-mono uppercase tracking-[0.2em]">
                    No research claims finalized.
                  </div>
                )}
              </div>
            </section>

            {attention.length > 0 && (
              <section className="space-y-6">
                <div className="rail-label opacity-40 text-[10px] tracking-[0.2em]">System State</div>
                <div className="space-y-0 border-t border-[var(--border)]">
                  {attention.map((item, idx) => (
                    <div key={idx} className="activity-row" style={{ gridTemplateColumns: "120px 1fr", padding: "18px 0" }}>
                      <div className="activity-ts">
                        <StatusPill value={item.severity} />
                      </div>
                      <div className="activity-content">
                        <div className="font-semibold mb-2">{item.title}</div>
                        <div className="text-sm opacity-70 leading-relaxed">{item.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        </main>

        <button
          className="md:hidden fixed bottom-6 right-6 z-20 p-3 bg-[var(--fg)] text-[var(--bg)] shadow-xl"
          onClick={() => setDrawerOpen(true)}
        >
          <Menu size={20} />
        </button>
      </div>

      <aside
        className={clsx(
          "w-96 max-w-[85vw] flex-shrink-0 border-l border-[var(--border)] bg-[var(--panel)] flex flex-col shadow-2xl md:shadow-none fixed md:static inset-y-0 right-0 z-30 transition-transform duration-300",
          drawerOpen ? "translate-x-0" : "translate-x-full md:translate-x-0"
        )}
      >
        <div className="h-14 flex items-center justify-between px-6 border-b border-[var(--border)]">
          <div className="rail-label">Inspection Rail</div>
          <button className="md:hidden text-[var(--muted)] hover:text-[var(--fg)]" onClick={() => setDrawerOpen(false)}>×</button>
        </div>

        <div className="flex border-b border-[var(--border)] bg-[var(--panel-alt)]">
          {[
            { key: "evidence", label: "Evidence", icon: Search },
            { key: "plan", label: "Plan", icon: ChevronRight },
            { key: "artifacts", label: "Artifacts", icon: FileText },
            { key: "data", label: "Data", icon: Database },
          ].map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={clsx(
                  "flex-1 flex flex-col items-center gap-1 py-3 text-[10px] font-mono uppercase tracking-wider border-r border-[var(--border)] transition-colors",
                  activeTab === tab.key ? "bg-[var(--panel)] text-[var(--fg)] font-bold" : "opacity-50 hover:opacity-80"
                )}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeTab === "evidence" && (
            <>
              <div className="space-y-3">
                <div className="rail-label opacity-50 text-[9px]">Top Claims</div>
                {latestTruth.length > 0 ? latestTruth.map((t, idx) => (
                  <div key={idx} className="p-4 border border-[var(--border)] bg-[var(--panel-alt)] space-y-3">
                    <div className="flex items-center justify-between">
                      <StatusPill value={t.verified ? "verified" : "candidate"} />
                      <div className="text-[9px] font-mono opacity-40">{Math.round(t.confidence * 100)}%</div>
                    </div>
                    <div className="text-sm leading-relaxed">{t.claim}</div>
                  </div>
                )) : (
                  <div className="empty-state">No evidence cards yet.</div>
                )}
              </div>
            </>
          )}

          {activeTab === "plan" && (
            <div className="space-y-4">
              <div>
                <div className="rail-label opacity-50 text-[9px] mb-3">Now</div>
                {plan.now.length > 0 ? plan.now.map((task, idx) => (
                  <div key={idx} className="p-3 border-b border-[var(--border)] text-sm leading-relaxed">{task}</div>
                )) : <div className="empty-state">No active tasks.</div>}
              </div>

              {plan.next.length > 0 && (
                <div>
                  <div className="rail-label opacity-50 text-[9px] mb-3">Next</div>
                  {plan.next.map((task, idx) => (
                    <div key={idx} className="p-3 border-b border-[var(--border)] text-sm leading-relaxed opacity-70">{task}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === "artifacts" && (
            <div className="space-y-3">
              {artifacts.length > 0 ? artifacts.map((artifact, idx) => (
                <div key={idx} className="p-4 border border-[var(--border)] bg-[var(--panel-alt)] space-y-2">
                  <div className="flex items-center justify-between gap-4">
                    <div className="font-medium text-sm leading-snug">{artifact.name}</div>
                    <StatusPill value={artifact.verified ? "verified" : artifact.freshness} />
                  </div>
                  <div className="text-[10px] font-mono opacity-40 break-all">{artifact.path}</div>
                </div>
              )) : (
                <div className="empty-state">No artifacts yet.</div>
              )}
            </div>
          )}

          {activeTab === "data" && (
            <div className="space-y-4">
              <div className="p-4 border border-[var(--border)] bg-[var(--panel-alt)] space-y-2">
                <div className="rail-label opacity-50 text-[9px]">Project Snapshot</div>
                <div className="text-sm leading-relaxed">Zen Mode is now seeded from the repo-backed control-plane snapshot, so this view still renders even when the live planner path is unstable.</div>
              </div>
              <Link href={`/projects/${slug}/dashboard`} className="overview-inline-link">
                Open Dashboard →
              </Link>
              <Link href={`/projects/${slug}/integrity`} className="overview-inline-link">
                Open Integrity →
              </Link>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
