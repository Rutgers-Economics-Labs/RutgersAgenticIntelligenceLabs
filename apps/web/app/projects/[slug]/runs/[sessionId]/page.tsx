import { MarkdownRenderer } from "@/components/markdown-renderer";
import { ProjectShell } from "@/components/project-shell";
import { StatusPill } from "@/components/status-pill";
import { fetchRunnerSessionDetail } from "@/lib/api";
import { RunnerLiveEvents } from "@/components/runner-live-events";
import Link from "next/link";

// ── Timeline row renderers ────────────────────────────────────────────

function fmtTime(ts: string | undefined): string {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  } catch {
    return ts.slice(11, 19) ?? "";
  }
}

function ToolCallRow({ event }: { event: any }) {
  const name = event.name || event.tool_name || event.raw?.name || "tool";
  const content = event.content || event.raw?.content || "";
  return (
    <div className="activity-tool">
      <span style={{ color: "var(--muted)", fontSize: 9, letterSpacing: "0.1em", textTransform: "uppercase" }}>cmd</span>
      <span style={{ color: "var(--fg)", fontWeight: 500 }}>{String(name)}</span>
      {content ? (
        <span style={{ color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 320 }}>
          {String(content).replace(/\n/g, " ").slice(0, 120)}
        </span>
      ) : null}
    </div>
  );
}

function FileChangeRow({ event }: { event: any }) {
  const path = event.path || event.raw?.path || event.content || "";
  return (
    <div className="activity-file-change">
      <span style={{ color: "var(--border-strong)", fontSize: 11 }}>±</span>
      <span style={{ color: "var(--fg)" }}>{String(path)}</span>
    </div>
  );
}

function AlertRow({ event, color }: { event: any; color: string }) {
  const content = event.summary || event.content || "";
  return (
    <div className="activity-alert" style={{ borderLeftColor: color }}>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em", color, marginBottom: 4 }}>
        {event.label}
      </div>
      {content ? <div style={{ color: "var(--fg)" }}>{String(content).slice(0, 300)}</div> : null}
    </div>
  );
}

function MessageRow({ event, role }: { event: any; role: "assistant" | "user" | "planner" }) {
  const content = event.summary || event.content || event.raw?.content || "";
  if (!content) return null;
  const isUser = role === "user";
  const isPlanner = role === "planner";
  return (
    <div
      className={isUser ? "activity-user-message" : "activity-message"}
      style={isPlanner ? { borderLeft: "2px solid var(--s-review)" } : {}}
    >
      <div style={{
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 10,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: isUser ? "var(--fg)" : isPlanner ? "var(--s-review)" : "var(--muted)",
        marginBottom: 6,
      }}>
        {isPlanner ? "planner relay" : role}
      </div>
      <MarkdownRenderer content={String(content)} />
    </div>
  );
}

function TimelineRow({ row }: { row: any }) {
  const t = fmtTime(row.timestamp);
  const type = row.eventType ?? "";

  let body: React.ReactNode;

  if (type === "assistant_message" || type === "progress") {
    body = <MessageRow event={row} role="assistant" />;
  } else if (type === "planner_relay") {
    body = <MessageRow event={row} role="planner" />;
  } else if (type === "user_message") {
    body = <MessageRow event={row} role="user" />;
  } else if (type === "tool_call") {
    body = <ToolCallRow event={row.raw ?? row} />;
  } else if (type === "tool_result") {
    body = (
      <div className="activity-tool" style={{ color: "var(--muted)" }}>
        <span style={{ fontSize: 9, letterSpacing: "0.1em", textTransform: "uppercase" }}>result</span>
        <span>{row.summary ? String(row.summary).slice(0, 100) : "—"}</span>
      </div>
    );
  } else if (type === "file_change_detected") {
    body = <FileChangeRow event={row.raw ?? row} />;
  } else if (type === "approval_requested") {
    body = <AlertRow event={row} color="var(--s-awaiting)" />;
  } else if (type === "question_asked") {
    body = <AlertRow event={row} color="var(--s-awaiting)" />;
  } else if (type === "verification_started" || type === "verification_completed") {
    body = (
      <div className="activity-tool">
        <span style={{ fontSize: 9, color: "var(--s-review)", textTransform: "uppercase", letterSpacing: "0.1em" }}>verify</span>
        <span style={{ color: "var(--fg)" }}>{row.label}</span>
        {row.summary ? <span style={{ color: "var(--muted)" }}>{String(row.summary).slice(0, 80)}</span> : null}
      </div>
    );
  } else if (type === "completed" || type === "failed" || type === "cancelled") {
    const color = type === "completed" ? "var(--s-running)" : type === "failed" ? "var(--s-failed)" : "var(--muted)";
    body = (
      <div className="activity-terminal" style={{ borderLeftColor: color }}>
        <span style={{ color, fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 600 }}>{type.toUpperCase()}</span>
        {row.summary ? <span style={{ color: "var(--muted)", marginLeft: 10 }}>{String(row.summary).slice(0, 120)}</span> : null}
      </div>
    );
  } else if (type === "session_started" || type === "workspace_setup_started" || type === "workspace_setup_completed") {
    body = (
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)" }}>
        {row.label}{row.summary ? ` — ${String(row.summary).slice(0, 80)}` : ""}
      </div>
    );
  } else {
    body = (
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)" }}>
        {row.label}{row.summary ? ` — ${String(row.summary).slice(0, 80)}` : ""}
      </div>
    );
  }

  if (!body) return null;

  return (
    <div className="activity-row">
      <div className="activity-ts">{t}</div>
      <div className="activity-content">{body}</div>
    </div>
  );
}

// ── Right rail ────────────────────────────────────────────────────────

function RightRail({ session }: { session: any }) {
  return (
    <div style={{ fontSize: 12 }}>

      {/* Session meta */}
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)" }}>
        <div className="rail-label" style={{ marginBottom: 8 }}>Session</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--muted)" }}>Status</span>
            <StatusPill value={session.status} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--muted)" }}>Review</span>
            <StatusPill value={session.reviewStatus} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--muted)" }}>Role</span>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>{session.role ?? "—"}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--muted)" }}>Runner</span>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>{session.runner ?? "—"}</span>
          </div>
          {session.setupStatus && (
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--muted)" }}>Setup</span>
              <StatusPill value={session.setupStatus} />
            </div>
          )}
          {session.verificationStatus && (
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--muted)" }}>Verify</span>
              <StatusPill value={session.verificationStatus} />
            </div>
          )}
        </div>
      </div>

      {/* Workspace */}
      {(session.workspaceBranch || session.workspacePath) && (
        <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)" }}>
          <div className="rail-label" style={{ marginBottom: 8 }}>Workspace</div>
          {session.workspaceBranch && (
            <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--fg)", marginBottom: 4 }}>
              {session.workspaceBranch}
            </div>
          )}
          {session.workspacePath && (
            <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", wordBreak: "break-all" }}>
              {session.workspacePath}
            </div>
          )}
        </div>
      )}

      {/* Changed files */}
      {session.changedFiles && session.changedFiles.length > 0 && (
        <div style={{ borderBottom: "1px solid var(--border)" }}>
          <div style={{ padding: "10px 12px 6px", display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
            <span className="rail-label">Changed Files</span>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
              {session.changedFiles.length}
            </span>
          </div>
          {session.changedFiles.map((path: string) => (
            <div key={path} className="file-row">
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{path}</span>
            </div>
          ))}
        </div>
      )}

      {/* Review files rendered */}
      {session.reviewFiles?.summary?.content && (
        <div style={{ borderBottom: "1px solid var(--border)" }}>
          <div style={{ padding: "10px 12px 4px" }}>
            <span className="rail-label">Summary</span>
          </div>
          <div style={{ padding: "8px 12px 12px" }}>
            <MarkdownRenderer content={session.reviewFiles.summary.content} />
          </div>
        </div>
      )}

      {session.reviewFiles?.todos?.content && (
        <div style={{ borderBottom: "1px solid var(--border)" }}>
          <div style={{ padding: "10px 12px 4px" }}>
            <span className="rail-label">Todos</span>
          </div>
          <div style={{ padding: "8px 12px 12px" }}>
            <MarkdownRenderer content={session.reviewFiles.todos.content} />
          </div>
        </div>
      )}

      {session.reviewFiles?.verification?.content && (
        <div>
          <div style={{ padding: "10px 12px 4px" }}>
            <span className="rail-label">Verification</span>
          </div>
          <div style={{ padding: "8px 12px 12px" }}>
            <MarkdownRenderer content={session.reviewFiles.verification.content} />
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────

export default async function RunDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; sessionId: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { slug, sessionId } = await params;
  const { tab = "summary" } = await searchParams;
  const session = await fetchRunnerSessionDetail(slug, sessionId);
  const timeline: any[] = session.timeline ?? [];
  const tabs = ["summary", "live", "timeline", "files", "commands", "sources", "decisions"];

  function tabHref(name: string) {
    return `/projects/${slug}/runs/${sessionId}?tab=${name}`;
  }

  return (
    <ProjectShell
      slug={slug}
      title={session.title ?? `${session.role ?? "session"} · ${session.runner ?? ""}`}
      section="sessions"
      rightRail={<RightRail session={session} />}
    >
      {/* Current focus bar */}
      {session.currentFocus && (
        <div style={{
          padding: "10px 16px",
          borderBottom: "1px solid var(--border)",
          background: "var(--panel-alt)",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}>
          <span className="rail-label">Focus</span>
          <span style={{ fontSize: 13, color: "var(--fg)" }}>{session.currentFocus}</span>
        </div>
      )}

      <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
        {tabs.map((name) => (
          <Link
            key={name}
            href={tabHref(name) as any}
            style={{
              padding: "8px 12px",
              borderRight: "1px solid var(--border)",
              background: tab === name ? "var(--fg)" : "var(--panel)",
              color: tab === name ? "var(--bg)" : "var(--fg)",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {name}
          </Link>
        ))}
      </div>

      <div style={{ padding: "0 16px" }}>
        {tab === "summary" && (
          <div style={{ padding: "16px 0", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
            {[
              ["Status", session.status],
              ["Review", session.reviewStatus],
              ["Role", session.role],
              ["Runner", session.runner],
              ["Task", session.taskId],
              ["Workspace", session.workspaceBranch ?? session.workspacePath],
            ].map(([label, value]) => (
              <div key={String(label)} className="rail-panel" style={{ padding: 12 }}>
                <div className="rail-label">{label}</div>
                <div style={{ marginTop: 6, color: "var(--fg)", fontFamily: "JetBrains Mono, monospace", fontSize: 12, wordBreak: "break-word" }}>
                  {String(value ?? "—")}
                </div>
              </div>
            ))}
            {session.reviewFiles?.summary?.content && (
              <div className="rail-panel" style={{ padding: 12, gridColumn: "1 / -1" }}>
                <div className="rail-label" style={{ marginBottom: 8 }}>Summary</div>
                <MarkdownRenderer content={session.reviewFiles.summary.content} />
              </div>
            )}
          </div>
        )}

        {tab === "live" && (
          <RunnerLiveEvents
            runner={session.runner ?? "jules"}
            sessionId={sessionId}
          />
        )}

        {tab === "timeline" && (
          timeline.length === 0 ? (
            <div className="empty-state">No events recorded yet.</div>
          ) : (
            timeline.map((row: any) => <TimelineRow key={row.id ?? row.timestamp} row={row} />)
          )
        )}

        {tab === "files" && (
          <div style={{ padding: "12px 0" }}>
            {(session.changedFiles ?? []).length === 0 ? <div className="empty-state">No changed files recorded.</div> : (
              session.changedFiles?.map((path: string) => <div key={path} className="file-row">{path}</div>)
            )}
            {session.reviewFiles?.diff?.content && (
              <pre className="content-preview" style={{ maxWidth: "none", marginTop: 12 }}>{session.reviewFiles.diff.content}</pre>
            )}
          </div>
        )}

        {tab === "commands" && (
          <div style={{ padding: "12px 0" }}>
            {(session.recentCommands ?? []).length === 0 ? <div className="empty-state">No commands recorded.</div> : (
              session.recentCommands?.map((command: any, i: number) => (
                <pre key={i} className="content-preview" style={{ maxWidth: "none", marginBottom: 8 }}>{JSON.stringify(command, null, 2)}</pre>
              ))
            )}
            {session.stdoutTail && <pre className="content-preview" style={{ maxWidth: "none" }}>{session.stdoutTail}</pre>}
            {session.stderrTail && <pre className="content-preview" style={{ maxWidth: "none" }}>{session.stderrTail}</pre>}
          </div>
        )}

        {tab === "sources" && (
          <div style={{ padding: "12px 0" }}>
            <div className="empty-state">Source citations gathered during runs appear in topics, artifacts, or review summaries. Linkage is read-only in this v1 surface.</div>
            {session.reviewFiles?.summary?.content && <MarkdownRenderer content={session.reviewFiles.summary.content} />}
          </div>
        )}

        {tab === "decisions" && (
          <div style={{ padding: "12px 0", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
            {[
              ["Assumptions", session.decisions?.assumptions ?? []],
              ["Blockers", session.decisions?.blockers ?? []],
              ["Open Questions", session.decisions?.openQuestions ?? []],
            ].map(([label, items]) => (
              <div className="rail-panel" style={{ padding: 12 }} key={String(label)}>
                <div className="rail-label" style={{ marginBottom: 8 }}>{String(label)}</div>
                {(items as string[]).length ? <ul>{(items as string[]).map((item) => <li key={item}>{item}</li>)}</ul> : <div className="mono-muted">None recorded.</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </ProjectShell>
  );
}
