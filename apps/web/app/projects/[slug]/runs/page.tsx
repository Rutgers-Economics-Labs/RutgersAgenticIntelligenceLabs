import Link from "next/link";
import { ProjectShell } from "@/components/project-shell";
import { StatusPill } from "@/components/status-pill";
import { fetchRunnerSessions } from "@/lib/api";

export default async function RunsPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ status?: string; role?: string; runner?: string; review?: string }>;
}) {
  const { slug } = await params;
  const filters = await searchParams;
  const { sessions } = await fetchRunnerSessions(slug);
  const ordered = [...sessions].sort((a: any, b: any) => {
    const rank = (s: any) => ["awaiting_approval", "awaiting_input", "running", "blocked"].includes(s.status) ? 0 : 1;
    return rank(a) - rank(b);
  }).filter((session: any) => {
    if (filters.status && session.status !== filters.status) return false;
    if (filters.role && session.role !== filters.role) return false;
    if (filters.runner && session.runner !== filters.runner) return false;
    if (filters.review && session.review?.reviewStatus !== filters.review) return false;
    return true;
  });
  const statuses = Array.from(new Set(sessions.map((s: any) => s.status).filter(Boolean)));
  const roles = Array.from(new Set(sessions.map((s: any) => s.role).filter(Boolean)));

  return (
    <ProjectShell slug={slug} title="Sessions" section="sessions">
      <div style={{ display: "flex", gap: 6, padding: "8px 12px", borderBottom: "1px solid var(--border)", flexWrap: "wrap" }}>
        <Link href={`/projects/${slug}/runs`} className="choice-button">All</Link>
        {statuses.map((status) => <Link key={status} href={`/projects/${slug}/runs?status=${encodeURIComponent(status)}`} className="choice-button">{status}</Link>)}
        {roles.map((role) => <Link key={role} href={`/projects/${slug}/runs?role=${encodeURIComponent(role)}`} className="choice-button">{role}</Link>)}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 12,
          fontFamily: "JetBrains Mono, monospace",
        }}>
          <thead>
            <tr style={{ background: "var(--panel-alt)" }}>
              {["Role", "Runner", "Status", "Review", "Branch", "Task", ""].map((h) => (
                <th key={h} style={{
                  padding: "8px 12px",
                  textAlign: "left",
                  borderBottom: "1px solid var(--border)",
                  color: "var(--muted)",
                  fontSize: 10,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  fontWeight: 500,
                  whiteSpace: "nowrap",
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ordered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{
                  padding: "40px 12px",
                  textAlign: "center",
                  color: "var(--muted)",
                  borderBottom: "1px solid var(--border)",
                }}>
                  No agent sessions recorded yet.
                </td>
              </tr>
            ) : (
              ordered.map((session: any, index: number) => (
                <tr
                  key={session._id ?? index}
                  style={{ borderBottom: "1px solid var(--border)" }}
                >
                  <td style={{ padding: "10px 12px", fontWeight: 500, color: "var(--fg)" }}>
                    <Link
                      href={`/projects/${slug}/runs/${session._id}`}
                      style={{ color: "var(--fg)" }}
                    >
                      {session.role ?? "agent"}
                    </Link>
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
                  <td style={{ padding: "10px 12px", color: "var(--muted)", fontSize: 11, maxWidth: 200 }}>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>
                      {session.taskId ? String(session.taskId).slice(-8) : "—"}
                    </span>
                  </td>
                  <td style={{ padding: "10px 12px" }}>
                    <Link
                      href={`/projects/${slug}/runs/${session._id}`}
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
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </ProjectShell>
  );
}
