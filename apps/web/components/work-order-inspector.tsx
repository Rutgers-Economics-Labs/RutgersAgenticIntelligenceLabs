"use client";

import { useEffect, useState } from "react";
import {
  fetchWorkOrder,
  fetchDispatchDecision,
  fetchSessionResult,
} from "@/lib/api";
import { WorkOrder, SessionResult, DispatchDecision } from "@/lib/contract-types";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { StatusPill } from "@/components/status-pill";

interface WorkOrderInspectorProps {
  sessionId: string;
  slug: string;
  onClose?: () => void;
  inline?: boolean;
}

type Tab = "work_order" | "dispatch" | "result";

export function WorkOrderInspector({
  sessionId,
  slug,
  onClose,
  inline = false,
}: WorkOrderInspectorProps) {
  const [activeTab, setActiveTab] = useState<Tab>("work_order");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [workOrder, setWorkOrder] = useState<WorkOrder | null>(null);
  const [dispatch, setDispatch] = useState<DispatchDecision | null>(null);
  const [result, setResult] = useState<SessionResult | null>(null);
  const [rawMode, setRawMode] = useState<boolean>(false);

  useEffect(() => {
    async function loadAllData() {
      setLoading(true);
      setError(null);
      try {
        const [woRes, dispRes, resRes] = await Promise.allSettled([
          fetchWorkOrder(sessionId, slug),
          fetchDispatchDecision(sessionId, slug),
          fetchSessionResult(sessionId, slug),
        ]);

        if (woRes.status === "fulfilled") {
          setWorkOrder(woRes.value);
        } else {
          console.warn("Failed to load work order:", woRes.reason);
        }

        if (dispRes.status === "fulfilled") {
          setDispatch(dispRes.value);
        } else {
          console.warn("Failed to load dispatch decision:", dispRes.reason);
        }

        if (resRes.status === "fulfilled") {
          setResult(resRes.value);
        } else {
          console.warn("Failed to load session result:", resRes.reason);
        }

        if (woRes.status === "rejected" && dispRes.status === "rejected" && resRes.status === "rejected") {
          setError("No observability data found for this session on disk.");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "An unexpected error occurred");
      } finally {
        setLoading(false);
      }
    }

    loadAllData();
  }, [sessionId, slug]);

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "work_order", label: "Work Order" },
    { id: "dispatch", label: "Dispatch Decision" },
    { id: "result", label: "Result" },
  ];

  const getActiveData = () => {
    if (activeTab === "work_order") return workOrder;
    if (activeTab === "dispatch") return dispatch;
    return result;
  };

  return (
    <div
      style={inline ? {
        background: "var(--panel)",
        border: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        width: "100%",
        minHeight: "450px",
      } : {
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: "550px",
        maxWidth: "100%",
        background: "var(--panel)",
        borderLeft: "1px solid var(--border)",
        boxShadow: "-4px 0 24px rgba(0, 0, 0, 0.15)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        animation: "slideIn 0.2s ease-out",
      }}
    >
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .inspector-badge {
          font-family: monospace;
          font-size: 10px;
          padding: 2px 6px;
          background: var(--bg);
          border: 1px solid var(--border);
          color: var(--fg);
        }
        .inspector-section {
          padding: 16px;
          border-bottom: 1px solid var(--border);
        }
        .inspector-table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 8px;
          font-size: 11px;
        }
        .inspector-table th, .inspector-table td {
          padding: 6px 8px;
          border: 1px solid var(--border);
          text-align: left;
        }
        .inspector-table th {
          background: var(--panel-alt);
          font-family: 'JetBrains Mono', monospace;
          color: var(--muted);
          font-weight: 500;
        }
      `}</style>

      {/* Header */}
      <div
        style={{
          padding: "16px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "var(--panel-alt)",
        }}
      >
        <div>
          <span className="rail-label" style={{ display: "block", marginBottom: 4 }}>Inspector</span>
          <h2 style={{ margin: 0, fontSize: 14, color: "var(--fg)", fontFamily: "'JetBrains Mono', monospace" }}>
            {sessionId.slice(0, 16)}...
          </h2>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            onClick={() => setRawMode((r) => !r)}
            style={{
              background: rawMode ? "var(--fg)" : "transparent",
              color: rawMode ? "var(--bg)" : "var(--muted)",
              border: "1px solid var(--border)",
              padding: "4px 8px",
              fontSize: 10,
              fontFamily: "'JetBrains Mono', monospace",
              cursor: "pointer",
            }}
          >
            {rawMode ? "RAW JSON" : "PREVIEW"}
          </button>
          {onClose && (
            <button
              onClick={onClose}
              style={{
                background: "transparent",
                border: "none",
                color: "var(--fg)",
                fontSize: 20,
                cursor: "pointer",
                padding: "4px 8px",
                lineHeight: 1,
              }}
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--border)",
          background: "var(--panel-raised)",
        }}
      >
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            style={{
              flex: 1,
              padding: "10px 12px",
              border: "none",
              borderRight: "1px solid var(--border)",
              background: activeTab === t.id ? "var(--panel)" : "transparent",
              color: activeTab === t.id ? "var(--fg)" : "var(--muted)",
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 10,
              fontWeight: activeTab === t.id ? 600 : 400,
              cursor: "pointer",
              borderBottom: activeTab === t.id ? "2px solid var(--border-strong)" : "none",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Body Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: 0 }}>
        {loading && (
          <div style={{ padding: 24, textAlign: "center", color: "var(--muted)", fontFamily: "monospace" }}>
            Loading session metadata from disk...
          </div>
        )}

        {error && !loading && (
          <div style={{ padding: 24, textAlign: "center", color: "var(--s-failed)" }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Observability Missing</div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>{error}</div>
          </div>
        )}

        {!loading && !error && (
          <>
            {rawMode ? (
              <pre
                style={{
                  margin: 16,
                  padding: 12,
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  color: "var(--fg)",
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 11,
                  overflowX: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {JSON.stringify(getActiveData(), null, 2)}
              </pre>
            ) : (
              <div>
                {/* ── WORK ORDER TAB ── */}
                {activeTab === "work_order" && (
                  <div>
                    {!workOrder ? (
                      <div style={{ padding: 24, color: "var(--muted)", textAlign: "center" }}>
                        No work order metadata recorded for this session.
                      </div>
                    ) : (
                      <>
                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 4 }}>Task Type</div>
                          <div style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 600 }}>{workOrder.task_type}</div>
                        </div>

                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 4 }}>Preferred Runner</div>
                          <div style={{ fontSize: 12 }}>{workOrder.runner_preferred || "None (Auto-routed)"}</div>
                        </div>

                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 6 }}>Required Capabilities</div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {workOrder.capabilities_required?.map((c) => (
                              <span key={c} className="inspector-badge">{c}</span>
                            )) || "None"}
                          </div>
                        </div>

                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 6 }}>Allowed Write Paths</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            {workOrder.allowed_paths?.map((p) => (
                              <div key={p} style={{ fontFamily: "monospace", fontSize: 11 }}>{p}</div>
                            )) || "None"}
                          </div>
                        </div>

                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 4 }}>Time & Cost Budget</div>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                            <div>
                              <span style={{ color: "var(--muted)", fontSize: 11 }}>Max Cost: </span>
                              <strong style={{ fontSize: 12 }}>{workOrder.cost_budget_usd ? `$${workOrder.cost_budget_usd}` : "Uncapped"}</strong>
                            </div>
                            <div>
                              <span style={{ color: "var(--muted)", fontSize: 11 }}>Max Time: </span>
                              <strong style={{ fontSize: 12 }}>{workOrder.wall_time_budget_minutes ? `${workOrder.wall_time_budget_minutes} min` : "Uncapped"}</strong>
                            </div>
                          </div>
                        </div>

                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 6 }}>Dependencies</div>
                          <div style={{ fontSize: 12 }}>
                            {workOrder.depends_on && workOrder.depends_on.length > 0 ? (
                              <ul style={{ margin: 0, paddingLeft: 18 }}>
                                {workOrder.depends_on.map((d) => (
                                  <li key={d} style={{ fontFamily: "monospace", marginBottom: 3 }}>{d}</li>
                                ))}
                              </ul>
                            ) : (
                              "None"
                            )}
                          </div>
                        </div>

                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 4 }}>Created By / At</div>
                          <div style={{ fontSize: 11, color: "var(--muted)" }}>
                            By: <span style={{ fontFamily: "monospace" }}>{workOrder.created_by}</span>
                            {workOrder.created_at && ` · ${new Date(workOrder.created_at).toLocaleString()}`}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* ── DISPATCH TAB ── */}
                {activeTab === "dispatch" && (
                  <div>
                    {!dispatch ? (
                      <div style={{ padding: 24, color: "var(--muted)", textAlign: "center" }}>
                        No capability router log found for this session's work order.
                      </div>
                    ) : (
                      <>
                        <div className="inspector-section" style={{ background: "var(--panel-alt)" }}>
                          <div className="rail-label" style={{ marginBottom: 4 }}>Selected Runner</div>
                          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--fg)", display: "flex", alignItems: "center", gap: 8 }}>
                            {dispatch.selected_runner || "Failed to dispatch"}
                            {dispatch.override && <span style={{ fontSize: 10, background: "var(--accent)", color: "white", padding: "2px 6px" }}>OVERRIDE</span>}
                          </div>
                          {dispatch.error && (
                            <div style={{ marginTop: 8, color: "var(--s-failed)", fontSize: 12, fontWeight: 500 }}>
                              Error: {dispatch.error}
                            </div>
                          )}
                        </div>

                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 6 }}>Scoreboard (Eligible Runners)</div>
                          {Object.keys(dispatch.eligible_scores || {}).length > 0 ? (
                            <table className="inspector-table">
                              <thead>
                                <tr>
                                  <th>Runner</th>
                                  <th>Matching Score</th>
                                </tr>
                              </thead>
                              <tbody>
                                {Object.entries(dispatch.eligible_scores || {})
                                  .sort((a, b) => b[1] - a[1])
                                  .map(([runner, score]) => (
                                    <tr key={runner} style={runner === dispatch.selected_runner ? { fontWeight: 600, background: "var(--panel-raised)" } : {}}>
                                      <td>{runner}</td>
                                      <td>{score.toFixed(2)}</td>
                                    </tr>
                                  ))}
                              </tbody>
                            </table>
                          ) : (
                            <div style={{ fontSize: 12, color: "var(--muted)" }}>No scoring statistics available.</div>
                          )}
                        </div>

                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 6 }}>Rejection Reasons (Ineligible Runners)</div>
                          {Object.keys(dispatch.rejection_reasons || {}).length > 0 ? (
                            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                              {Object.entries(dispatch.rejection_reasons || {}).map(([runner, reason]) => (
                                <div key={runner} style={{ fontSize: 12 }}>
                                  <strong style={{ fontFamily: "monospace", display: "block", marginBottom: 2 }}>{runner}</strong>
                                  <span style={{ color: "var(--muted)", fontSize: 11 }}>{reason}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div style={{ fontSize: 12, color: "var(--muted)" }}>No rejection logs recorded.</div>
                          )}
                        </div>

                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 4 }}>Timestamp</div>
                          <div style={{ fontSize: 11, color: "var(--muted)" }}>
                            {new Date(dispatch.timestamp).toLocaleString()}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* ── RESULT TAB ── */}
                {activeTab === "result" && (
                  <div>
                    {!result ? (
                      <div style={{ padding: 24, color: "var(--muted)", textAlign: "center" }}>
                        Session result not compiled yet. (Session may still be running or failed before finalization).
                      </div>
                    ) : (
                      <>
                        <div className="inspector-section" style={{ background: "var(--panel-alt)", borderBottom: "1px solid var(--border)" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                            <span className="rail-label">Status</span>
                            <StatusPill value={result.status} />
                          </div>
                          <div style={{ fontSize: 13, color: "var(--fg)", fontWeight: 500, lineHeight: 1.4 }}>{result.summary}</div>
                        </div>

                        {/* Blockers */}
                        {result.blockers && result.blockers.length > 0 && (
                          <div className="inspector-section" style={{ background: "rgba(220, 38, 38, 0.05)" }}>
                            <div className="rail-label" style={{ color: "var(--s-failed)", marginBottom: 8 }}>Blockers ({result.blockers.length})</div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                              {result.blockers.map((b, idx) => (
                                <div key={b.blocker_id || idx} style={{ borderLeft: "2px solid var(--s-failed)", paddingLeft: 10 }}>
                                  <div style={{ fontWeight: 600, fontSize: 12, color: "var(--fg)" }}>{b.summary}</div>
                                  <div style={{ fontSize: 11, color: "var(--muted)", margin: "4px 0" }}>Category: {b.category}</div>
                                  {b.detail && <div style={{ fontSize: 11, color: "var(--fg)" }}>{b.detail}</div>}
                                  {b.recommended_followup && (
                                    <div style={{ marginTop: 6, fontSize: 11, fontStyle: "italic", color: "var(--muted)" }}>
                                      Recommendation: {b.recommended_followup}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Claims */}
                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 8 }}>Claim Candidates ({result.claims?.length || 0})</div>
                          {result.claims && result.claims.length > 0 ? (
                            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                              {result.claims.map((c) => (
                                <div key={c.claim_id} style={{ border: "1px solid var(--border)", padding: 10, background: "var(--panel)" }}>
                                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                                    <span style={{ fontFamily: "monospace", fontSize: 10, fontWeight: 600 }}>{c.claim_id}</span>
                                    <span style={{ fontSize: 10 }} className="inspector-badge">{c.status}</span>
                                  </div>
                                  <div style={{ fontSize: 12, color: "var(--fg)", marginBottom: 6 }}>{c.text}</div>
                                  <div style={{ display: "flex", gap: 12, fontSize: 10, color: "var(--muted)" }}>
                                    {c.confidence !== undefined && c.confidence !== null && (
                                      <span>Confidence: <strong>{(c.confidence * 100).toFixed(0)}%</strong></span>
                                    )}
                                    {c.evidence_refs && c.evidence_refs.length > 0 && (
                                      <span>Evidence: {c.evidence_refs.join(", ")}</span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div style={{ fontSize: 12, color: "var(--muted)" }}>No claims surfaced during this session.</div>
                          )}
                        </div>

                        {/* Sources */}
                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 8 }}>Sources Materialized ({result.sources?.length || 0})</div>
                          {result.sources && result.sources.length > 0 ? (
                            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                              {result.sources.map((s) => (
                                <div key={s.source_id} style={{ fontSize: 12 }}>
                                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <strong style={{ color: "var(--fg)" }}>{s.name}</strong>
                                    <span style={{ fontSize: 10, color: "var(--muted)" }}>{s.admissibility}</span>
                                  </div>
                                  <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)" }}>
                                    ID: {s.source_id} {s.provider && `· Provider: ${s.provider}`}
                                  </div>
                                  {s.access_url && (
                                    <a
                                      href={s.access_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      style={{ display: "inline-block", fontSize: 11, color: "var(--s-review)", marginTop: 4, textDecoration: "underline" }}
                                    >
                                      {s.access_url}
                                    </a>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div style={{ fontSize: 12, color: "var(--muted)" }}>No sources registered.</div>
                          )}
                        </div>

                        {/* Datasets */}
                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 8 }}>Datasets Produced ({result.datasets?.length || 0})</div>
                          {result.datasets && result.datasets.length > 0 ? (
                            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                              {result.datasets.map((d) => (
                                <div key={d.dataset_id} style={{ fontSize: 12 }}>
                                  <div style={{ fontFamily: "monospace", fontWeight: 600 }}>{d.file_path}</div>
                                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                                    ID: {d.dataset_id} {d.row_count !== undefined && d.row_count !== null && `· Row Count: ${d.row_count}`}
                                  </div>
                                  {d.schema_summary && (
                                    <div style={{ background: "var(--bg)", padding: 6, marginTop: 4, fontSize: 10, fontFamily: "monospace" }}>
                                      {d.schema_summary}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div style={{ fontSize: 12, color: "var(--muted)" }}>No datasets recorded.</div>
                          )}
                        </div>

                        {/* Progress metrics */}
                        <div className="inspector-section">
                          <div className="rail-label" style={{ marginBottom: 6 }}>Domain Progress</div>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11 }}>
                            <div>Sources Ingested: <strong>{result.domain_progress?.new_sources || 0}</strong></div>
                            <div>Datasets Created: <strong>{result.domain_progress?.new_datasets || 0}</strong></div>
                            <div>Claims Surfaced: <strong>{result.domain_progress?.new_claim_candidates || 0}</strong></div>
                            <div>Claims Verified: <strong>{result.domain_progress?.new_verified_claims || 0}</strong></div>
                          </div>
                        </div>

                        {/* Cost & Duration */}
                        <div className="inspector-section" style={{ borderBottom: "none" }}>
                          <div className="rail-label" style={{ marginBottom: 4 }}>accounting</div>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 11, color: "var(--muted)" }}>
                            <div>Recorded Cost: <strong style={{ color: "var(--fg)" }}>{result.cost_recorded_usd !== null && result.cost_recorded_usd !== undefined ? `$${result.cost_recorded_usd.toFixed(4)}` : "—"}</strong></div>
                            <div>Duration: <strong style={{ color: "var(--fg)" }}>{result.duration_seconds !== null && result.duration_seconds !== undefined ? `${(result.duration_seconds / 60).toFixed(1)} min` : "—"}</strong></div>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
