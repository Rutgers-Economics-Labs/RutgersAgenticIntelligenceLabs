import Link from "next/link";
import { ProjectShell } from "@/components/project-shell";
import { StatusPill } from "@/components/status-pill";
import { fetchPlannerHome, fetchProjectApprovals, fetchRunnerSessions } from "@/lib/api";

function ReviewRightRail({ home }: { home: any }) {
  const rows = [
    { label: "task_board.md",  value: home.planner.files?.taskBoard },
    { label: "approvals.md",   value: home.planner.files?.approvals },
    { label: "sessions root",  value: home.planner.workspaceReview?.sessionsRoot },
  ];
  return (
    <div>
      <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)" }}>
        <span className="rail-label">Repo Contract</span>
      </div>
      {rows.map(({ label, value }) => (
        <div key={label} style={{
          padding: "8px 14px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
        }}>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)" }}>{label}</span>
          <StatusPill value={value ? "present" : "missing"} />
        </div>
      ))}
    </div>
  );
}

export default async function ReviewPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [home, approvalsPayload, runs] = await Promise.all([
    fetchPlannerHome(slug),
    fetchProjectApprovals(slug),
    fetchRunnerSessions(slug),
  ]);
  const approvals = approvalsPayload.approvals ?? [];
  const reviewableSessions = (runs.sessions ?? []).filter(
    (s: any) => s.review?.reviewStatus || s.review?.diffPath
  );

  return (
    <ProjectShell
      slug={slug}
      title="Review"
      section="review"
      rightRail={<ReviewRightRail home={home} />}
    >
      {/* Approvals section */}
      <div style={{ borderBottom: "1px solid var(--border)" }}>
        <div style={{
          padding: "8px 14px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}>
          <span className="rail-label">Approvals</span>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
            {approvals.filter((a: any) => a.status === "pending").length} pending
          </span>
        </div>
        {approvals.length === 0 ? (
          <div style={{ padding: "24px 14px", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
            No approvals queued.
          </div>
        ) : (
          approvals.map((a: any, i: number) => (
            <div key={i} style={{
              padding: "10px 14px",
              borderBottom: "1px solid var(--border)",
              borderLeft: a.status === "pending" ? "2px solid var(--s-awaiting)" : "2px solid transparent",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 500, color: "var(--fg)" }}>
                  {String(a.approvalType ?? "approval")}
                </div>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                  {String(a.requestedByRole ?? "planner")}
                  {a.taskId ? ` · task ${String(a.taskId).slice(-6)}` : ""}
                </div>
              </div>
              <StatusPill value={String(a.status ?? "pending")} />
            </div>
          ))
        )}
      </div>

      {/* Session review queue */}
      <div>
        <div style={{
          padding: "8px 14px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}>
          <span className="rail-label">Session Review Queue</span>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
            {reviewableSessions.length}
          </span>
        </div>
        {reviewableSessions.length === 0 ? (
          <div style={{ padding: "24px 14px", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
            No sessions in review. Worker sessions with diffs will appear here.
          </div>
        ) : (
          reviewableSessions.map((session: any, i: number) => (
            <Link
              key={session._id ?? i}
              href={`/projects/${slug}/runs/${session._id}`}
              style={{ display: "block" }}
            >
              <div style={{
                padding: "10px 14px",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "space-between",
                gap: 12,
                transition: "background 100ms",
              }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "var(--fg)", marginBottom: 2 }}>
                    {session.role ?? "agent"}
                  </div>
                  <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
                    {session.runner ?? "runner unknown"}
                    {session.review?.workspaceBranch ? ` · ${session.review.workspaceBranch}` : ""}
                  </div>
                  <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 2 }}>
                    {[
                      ["summary", session.review?.summaryPath],
                      ["diff", session.review?.diffPath],
                      ["todos", session.review?.todosPath],
                      ["verify", session.review?.verificationPath],
                    ].filter(([, v]) => v).map(([label, val]) => (
                      <span key={label} style={{
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 10,
                        color: "var(--muted)",
                      }}>
                        {label}: {String(val)}
                      </span>
                    ))}
                  </div>
                </div>
                <StatusPill value={session.review?.reviewStatus ?? session.status} />
              </div>
            </Link>
          ))
        )}
      </div>
    </ProjectShell>
  );
}
