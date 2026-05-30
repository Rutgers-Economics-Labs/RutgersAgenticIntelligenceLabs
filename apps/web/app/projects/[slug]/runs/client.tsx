"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { PageIntro } from "@/components/page-intro";
import { StatusPill } from "@/components/status-pill";
import { fetchRunnerSessions, fetchPlannerHome } from "@/lib/api";
import type { PlannerHome, RunnerSession } from "@/lib/types";
import { SessionSteering } from "@/components/session-steering";

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

function realityDetails(home: PlannerHome | null) {
  return home?.controlPlane?.projectReality?.details ?? null;
}

type RunsClientProps = {
  slug: string;
  initialSessions: RunnerSession[];
  initialHome: PlannerHome | null;
};

function seedTaskMap(home: PlannerHome | null): Record<string, string> {
  const next: Record<string, string> = {};
  for (const task of home?.planner.tasks ?? []) {
    next[task._id] = task.title;
  }
  return next;
}

export function RunsClient({ slug, initialSessions, initialHome }: RunsClientProps) {
  const searchParams = useSearchParams();
  const statusFilter = searchParams.get("status");
  const roleFilter = searchParams.get("role");
  const runnerFilter = searchParams.get("runner");
  const reviewFilter = searchParams.get("review");

  const [sessions, setSessions] = useState<RunnerSession[]>(initialSessions);
  const [taskMap, setTaskMap] = useState<Record<string, string>>(seedTaskMap(initialHome));
  const [staleIds, setStaleIds] = useState<Set<string>>(
    new Set([...(realityDetails(initialHome)?.staleRuntimeSessionIds ?? [])]),
  );
  const [zombieIds, setZombieIds] = useState<Set<string>>(
    new Set([...(realityDetails(initialHome)?.zombieSessionIds ?? [])]),
  );
  const [, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [sessData, homeData] = await Promise.allSettled([
        fetchRunnerSessions(slug),
        fetchPlannerHome(slug),
      ]);
      if (cancelled) return;
      if (sessData.status === "fulfilled") setSessions(sessData.value.sessions);
      if (homeData.status === "fulfilled") {
        const m: Record<string, string> = {};
        for (const t of homeData.value.planner.tasks ?? []) m[t._id] = t.title;
        setTaskMap(m);
        const details = realityDetails(homeData.value);
        setStaleIds(new Set([
          ...(details?.staleRuntimeSessionIds ?? []),
        ]));
        setZombieIds(new Set([
          ...(details?.zombieSessionIds ?? []),
        ]));
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
      <PageIntro
        title="See every agent run, what happened, and where it ended."
        detail="Use Sessions for run history and detailed workspace review. If you need to change the queue, use Planner. If you need to approve held work, use Review."
        actions={[
          { label: "Open Planner", href: `/projects/${slug}/planner` },
          { label: "Open Review", href: `/projects/${slug}/review` },
        ]}
      />
      <SectionCard eyebrow="Session Ledger" title="Every agent run in one place">
        <div className="overview-copy" style={{ marginTop: 0 }}>
          Use Sessions when you want the run history itself: which agent ran, which runner handled it, what review state it ended in, and where to open the detailed workspace review.
        </div>
      </SectionCard>
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
              {["Role", "Runner", "Status", "Health", "Review", "Branch", "Task", "Elapsed", "Steering", ""].map((h) => (
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
                  colSpan={10}
                  style={{ padding: "40px 12px", textAlign: "center", color: "var(--muted)", borderBottom: "1px solid var(--border)" }}
                >
                  No agent sessions recorded yet.
                </td>
              </tr>
            ) : (
              ordered.map((session, index) => {
                const active = ACTIVE.has(session.status);
                const sid = session._id ?? session.id;
                const sidStr = sid ? String(sid) : null;
                const isZombie = sidStr ? zombieIds.has(sidStr) : false;
                const isStale = !isZombie && sidStr ? staleIds.has(sidStr) : false;
                const healthState: "stale" | "zombie" | "active" | null = isZombie
                  ? "zombie"
                  : isStale
                    ? "stale"
                    : active
                      ? "active"
                      : null;
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
                      {healthState ? <StatusPill value={healthState} /> : <span style={{ color: "var(--muted)" }}>—</span>}
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
                      <SessionSteering
                        slug={slug}
                        sessionId={sidStr ?? undefined}
                        runner={session.runner ?? undefined}
                        status={session.status}
                        staleness={healthState}
                      />
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
