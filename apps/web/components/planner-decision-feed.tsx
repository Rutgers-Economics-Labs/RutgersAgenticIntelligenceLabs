"use client";

import { useState } from "react";
import type { PlannerDecision } from "@/lib/types";

export function PlannerDecisionFeed({ decisions }: { decisions: PlannerDecision[] }) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  function getRelativeTime(timestamp: number | null | undefined) {
    if (!timestamp) return "unknown";
    const diff = Math.floor(Date.now() / 1000 - timestamp);
    if (diff < 60) return "just now";
    const mins = Math.floor(diff / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return new Date(timestamp * 1000).toLocaleDateString();
  }

  if (decisions.length === 0) {
    return (
      <div style={{ padding: 16, color: "var(--muted)", fontSize: 12, textAlign: "center", border: "1px dashed var(--border)" }}>
        No recent planner decisions.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, maxHeight: 360, overflowY: "auto", paddingRight: 4 }}>
      {decisions.map((decision, index) => {
        const expanded = expandedIndex === index;
        return (
          <div key={`${decision.tool ?? "decision"}-${index}`} style={{ border: "1px solid var(--border)", background: "var(--bg)", padding: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--fg)" }}>
                  {decision.tool ?? "planner"}
                </div>
                {decision.rationale && (
                  <div style={{ marginTop: 6, fontSize: 12, color: "var(--fg)", lineHeight: 1.5 }}>
                    {decision.rationale}
                  </div>
                )}
                {decision.result_summary && (
                  <div style={{ marginTop: 6, fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
                    {decision.result_summary}
                  </div>
                )}
              </div>
              <div style={{ flexShrink: 0, fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>
                {getRelativeTime(decision.timestamp)}
              </div>
            </div>
            {decision.args && Object.keys(decision.args).length > 0 ? (
              <>
                <button
                  onClick={() => setExpandedIndex(expanded ? null : index)}
                  style={{
                    marginTop: 8,
                    padding: 0,
                    border: "none",
                    background: "none",
                    color: "var(--muted)",
                    cursor: "pointer",
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    textTransform: "uppercase",
                  }}
                >
                  {expanded ? "Hide args" : "Show args"}
                </button>
                {expanded && (
                  <pre
                    style={{
                      margin: "8px 0 0",
                      padding: 10,
                      background: "var(--panel)",
                      border: "1px solid var(--border)",
                      overflowX: "auto",
                      fontSize: 10,
                      color: "var(--fg)",
                    }}
                  >
                    {JSON.stringify(decision.args, null, 2)}
                  </pre>
                )}
              </>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
