import React, { useState, useEffect } from "react";
import { fetchPlannerDecisions } from "@/lib/api";

interface PlannerDecisionFeedProps {
  slug: string;
}

export function PlannerDecisionFeed({ slug }: PlannerDecisionFeedProps) {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const data = await fetchPlannerDecisions(slug);
        if (active) {
          setDecisions(data);
          setLoading(false);
        }
      } catch (err) {
        console.error("Failed to fetch planner decisions:", err);
      }
    }

    load();
    const interval = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [slug]);

  function getRelativeTime(timestamp: number) {
    const diff = Math.floor(Date.now() / 1000 - timestamp);
    if (diff < 60) return "just now";
    const mins = Math.floor(diff / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return new Date(timestamp * 1000).toLocaleDateString();
  }

  if (loading && decisions.length === 0) {
    return (
      <div style={{ padding: "16px", color: "var(--fg-muted)", fontSize: "14px", textAlign: "center" }}>
        Loading decisions...
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px", maxHeight: "400px", overflowY: "auto", paddingRight: "4px" }}>
      {decisions.length === 0 ? (
        <div style={{ padding: "16px", color: "var(--fg-muted)", fontSize: "14px", textAlign: "center", border: "1px dashed var(--border)", borderRadius: "8px" }}>
          No recent planner decisions.
        </div>
      ) : (
        decisions.map((dec, idx) => {
          const isExpanded = expandedIndex === idx;
          return (
            <div
              key={idx}
              style={{
                background: "var(--panel)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "12px",
                fontSize: "13px",
                transition: "all 0.2s ease-in-out",
                boxShadow: "0 2px 4px rgba(0, 0, 0, 0.1)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "6px" }}>
                <span
                  style={{
                    fontFamily: "monospace",
                    background: "rgba(255, 255, 255, 0.08)",
                    padding: "2px 6px",
                    borderRadius: "4px",
                    color: "var(--fg-accent, #60a5fa)",
                    fontWeight: "bold",
                  }}
                >
                  {dec.tool}
                </span>
                <span style={{ fontSize: "11px", color: "var(--fg-muted)" }}>
                  {getRelativeTime(dec.timestamp)}
                </span>
              </div>

              {dec.rationale && (
                <div style={{ color: "var(--fg)", marginBottom: "8px", fontStyle: "italic", borderLeft: "2px solid var(--border)", paddingLeft: "8px", margin: "4px 0 8px 0" }}>
                  {dec.rationale}
                </div>
              )}

              {dec.result_summary && (
                <div style={{ color: "var(--fg-muted)", fontSize: "12px" }}>
                  <strong>Result:</strong> {dec.result_summary}
                </div>
              )}

              <button
                onClick={() => setExpandedIndex(isExpanded ? null : idx)}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--fg-accent, #60a5fa)",
                  cursor: "pointer",
                  fontSize: "11px",
                  padding: "4px 0 0 0",
                  display: "block",
                  textDecoration: "underline",
                }}
              >
                {isExpanded ? "Hide Details" : "Show Details"}
              </button>

              {isExpanded && (
                <div
                  style={{
                    marginTop: "8px",
                    padding: "8px",
                    background: "rgba(0, 0, 0, 0.2)",
                    borderRadius: "4px",
                    fontFamily: "monospace",
                    fontSize: "11px",
                    overflowX: "auto",
                    whiteSpace: "pre-wrap",
                    border: "1px solid var(--border)",
                  }}
                >
                  <strong>Arguments:</strong>
                  <pre style={{ margin: "4px 0", color: "var(--fg)" }}>
                    {JSON.stringify(dec.args, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
