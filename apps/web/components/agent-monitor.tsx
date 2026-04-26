"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchActiveAgents } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  queued:           "var(--muted)",
  running:          "#22c55e",
  awaiting_input:   "#f59e0b",
  awaiting_approval:"#f59e0b",
  paused:           "#6b7280",
};

const ROLE_ICON: Record<string, string> = {
  planner:  "P",
  research: "R",
  code:     "C",
  jules:    "J",
  gemini:   "G",
};

interface Agent {
  sessionId: string;
  role: string;
  runner: string;
  status: string;
  title: string;
  startedAt?: number;
  taskId?: string;
}

export function AgentMonitor({ slug }: { slug: string }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const { agents: data } = await fetchActiveAgents(slug);
        if (!cancelled) {
          setAgents(data);
          setError(false);
        }
      } catch {
        if (!cancelled) setError(true);
      }
    }

    poll();
    const id = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [slug]);

  if (error || agents.length === 0) {
    return (
      <div style={{ padding: "8px 12px 4px" }}>
        <div className="rail-label" style={{ marginBottom: 4 }}>
          Agents{agents.length > 0 ? ` (${agents.length})` : ""}
        </div>
        <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", padding: "2px 0" }}>
          {error ? "—" : "no active agents"}
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: "8px 12px 4px" }}>
      <div className="rail-label" style={{ marginBottom: 4 }}>
        Agents ({agents.length})
      </div>
      {agents.map((a) => {
        const dot = STATUS_COLOR[a.status] ?? "var(--muted)";
        const icon = ROLE_ICON[a.role] ?? "?";
        const href = a.sessionId
          ? `/projects/${slug}/runs/${encodeURIComponent(a.sessionId)}`
          : undefined;

        const row = (
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 0" }}>
            <span style={{
              width: 16, height: 16,
              borderRadius: 3,
              background: "var(--border)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 8, fontWeight: 700,
              color: "var(--fg)", flexShrink: 0,
            }}>{icon}</span>
            <span style={{ flex: 1, minWidth: 0, fontSize: 10, fontFamily: "JetBrains Mono, monospace", color: "var(--fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {a.title || a.role}
            </span>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: dot, flexShrink: 0 }} title={a.status} />
          </div>
        );

        return href ? (
          <Link key={a.sessionId} href={href} style={{ display: "block", textDecoration: "none" }}>
            {row}
          </Link>
        ) : (
          <div key={a.sessionId ?? a.role}>{row}</div>
        );
      })}
    </div>
  );
}
