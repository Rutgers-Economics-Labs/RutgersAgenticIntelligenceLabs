"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ProjectShell } from "@/components/project-shell";
import { StatusPill } from "@/components/status-pill";
import { fetchRunnerSessions, fetchPlannerBoard } from "@/lib/api";
import type { RunnerSession } from "@/lib/types";

function elapsed(ts: number | undefined): string {
  if (!ts) return "—";
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

const ACTIVE = new Set(["awaiting_approval", "awaiting_input", "running", "blocked"]);

export function RunsClient() {
  const { slug } = useParams<{ slug: string }>();
  const searchParams = useSearchParams();
  const statusFilter = searchParams.get("status");
  const roleFilter = searchParams.get("role");
  const runnerFilter = searchParams.get("runner");
  const reviewFilter = searchParams.get("review");

  const [sessions, setSessions] = useState<RunnerSession[]>([]);
  const [taskMap, setTaskMap] = useState<Record<string, string>>({});
  const [, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [sessData, boardData] = await Promise.allSettled([
        fetchRunnerSessions(slug),
        fetchPlannerBoard(slug),
      ]);
      if (cancelled) return;
      if (sessData.status === "fulfilled") setSessions(sessData.value.sessions);
      if (boardData.status === "fulfilled") {
        const m: Record<string, string> = {};
        for (const t of boardData.value.tasks ?? []) m[t._id] = t.title;
        setTaskMap(m);
      }
    }

    load();
    const id = setInterval(load, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, [slug]);

  // tick every second so elapsed times on running sessions stay live
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const ordered = [...sessions]
    .sort((a, b) => (ACTIVE.has(a.status) ? 0 : 1) - (ACTIVE.has(b.status) ? 0 : 1))
    .filter((s) => {
      if (statusFilter && s.status !== statusFilter) return false;
      if (roleFilter && s.role !== roleFilter) return false;
      if (runnerFilter && s.runner !== runnerFilter) return false;
      if (reviewFilter && s.review?.reviewStatus !== reviewFilter) return false;
      return true;
    });

  const statuses = Array.from(new Set(sessions.map((s) => s.status).filter(Boolean)));
  const roles = Array.from(new Set(sessions.map((s) => s.role).filter(Boolean)));

  return (
    <ProjectShell slug={slug} title="Sessions" section="sessions">
      <div style={{ display: "flex", gap: 6, padding: "8px 12px", borderBottom: "1px solid var(--border)", flexWrap: "wrap" }}>
        <Link href={`/projects/${slug}/runs`} className="choice-button">All</Link>
        {statuses.map((s) => (
          <Link key={s} href={`/projects/${slug}/runs?status=${encodeURIComponent(s as string)}`} className="choice-button">{s}</Link>
        ))}
        {roles.map((r) => (
          <Link key={r} href={`/projects/${slug}/runs?role=${encodeURIComponent(r as string)}`} className="choice-button">{r}</Link>
        ))}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: "JetBrains Mono, monospace" }}>
          <thead>
            <tr style={{ background: "var(--panel-alt)" }}>
              {["Role", "Runner", "Status", "Review", "Branch", "Task", "Elapsed", ""].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: "8px 12px",
                    textAlign: "left",
                    borderBottom: "1px solid var(--border)",
                    color: "var(--muted)",
                    fontSize: 10,
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    fontWeight: 500,
                    whiteSpace: "nowrap",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ordered.length === 0 ? (
              <tr>
                <td
                  colSpan={8}
                  style={{ padding: "40px 12px", textAlign: "center", color: "var(--muted)", borderBottom: "1px solid var(--border)" }}
                >
                  No agent sessions recorded yet.
                </td>
              </tr>
            ) : (
              ordered.map((session, index) => {
                const active = ACTIVE.has(session.status);
                const sid = session._id ?? session.id;
                return (
                  <tr key={sid ?? index} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "10px 12px", fontWeight: 500, color: "var(--fg)" }}>
                      {sid ? (
                        <Link href={`/projects/${slug}/runs/${sid}`} style={{ color: "var(--fg)" }}>
                          {session.role ?? "agent"}
                        </Link>
                      ) : (
                        <span>{session.role ?? "agent"}</span>
                      )}
                    </td>
                    <td style={{ padding: "10px 12px", color: "var(--muted)", fontSize: 11 }}>
                      {session.runner ?? "—"}
                    </td>
                    <td style={{ padding: "10px 12px" }}>
                      <StatusPill value={session.status} />
                    </td>
                    <td style={{ padding: "10px 12px" }}>
                      <StatusPill value={session.review?.reviewStatus} />
                    </td>
                    <td style={{ padding: "10px 12px", color: "var(--muted)", fontSize: 11 }}>
                      {session.review?.workspaceBranch ?? "—"}
                    </td>
                    <td style={{ padding: "10px 12px", fontSize: 11, maxWidth: 220 }}>
                      <span
                        title={session.taskId ?? undefined}
                        style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block", color: "var(--fg)" }}
                      >
                        {session.taskId
                          ? (taskMap[session.taskId] ?? String(session.taskId).slice(-8))
                          : "—"}
                      </span>
                    </td>
                    <td
                      style={{
                        padding: "10px 12px",
                        fontSize: 11,
                        whiteSpace: "nowrap",
                        color: active ? "#22c55e" : "var(--muted)",
                      }}
                    >
                      {elapsed(session.startedAt)}
                    </td>
                    <td style={{ padding: "10px 12px" }}>
                      {sid && (
                        <Link
                          href={`/projects/${slug}/runs/${sid}`}
                          style={{
                            fontSize: 10,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            color: "var(--muted)",
                            borderBottom: "1px solid var(--border)",
                            paddingBottom: 1,
                          }}
                        >
                          View →
                        </Link>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </ProjectShell>
  );
}
