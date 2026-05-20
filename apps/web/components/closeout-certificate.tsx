"use client";

import type { CommandCenter } from "@/lib/types";

/**
 * Visible verdict for "are we done?".
 *
 * Renders the closeout-certificate state derived in command_center_service:
 *   - issued: closeout auditor ready AND lifecycle phase == "closed"
 *   - pending: closeout auditor blocked, with first blocker as headline
 *   - would_issue_if: upstream auditor still blocked, certificate is partial
 *
 * The certificate is the spec's answer to "no manual closeout repair needed"
 * (docs/future-spec-autonomous-platform-roadmap.md#e-closeout-is-not-yet-self-healing).
 */
export function CloseoutCertificate({ center }: { center: CommandCenter }) {
  const cert = center.closeoutCertificate;
  const phase = center.lifecyclePhase ?? "—";
  if (!cert) return null;

  const styles = {
    issued:        { bg: "rgba(16, 185, 129, 0.12)", border: "rgba(16, 185, 129, 0.55)", fg: "#065f46", icon: "●" },
    pending:       { bg: "rgba(239, 68, 68, 0.10)",  border: "rgba(239, 68, 68, 0.5)",   fg: "#991b1b", icon: "○" },
    would_issue_if:{ bg: "rgba(59, 130, 246, 0.10)", border: "rgba(59, 130, 246, 0.5)",  fg: "#1e3a8a", icon: "◐" },
  } as const;
  const palette = styles[cert.status];

  const statusLabel =
    cert.status === "issued" ? "Certificate issued" :
    cert.status === "pending" ? "Certificate pending" :
    "Would issue if";

  return (
    <div
      style={{
        margin: "0 16px 0",
        padding: "10px 14px",
        background: palette.bg,
        border: `1px solid ${palette.border}`,
        borderRadius: 6,
        display: "grid",
        gridTemplateColumns: "auto 1fr auto",
        gap: 14,
        alignItems: "center",
      }}
    >
      <span style={{ fontSize: 22, color: palette.fg, lineHeight: 1 }}>{palette.icon}</span>
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: palette.fg,
          }}
        >
          Closeout · {statusLabel}
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg)", marginTop: 4 }}>
          {cert.headline}
        </div>
        {cert.blockers.length > 0 ? (
          <ul style={{ margin: "6px 0 0", padding: "0 0 0 18px", color: "var(--muted)", fontSize: 12 }}>
            {cert.blockers.slice(0, 4).map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        ) : null}
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="rail-label">Phase</div>
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 12,
            fontWeight: 700,
            color: "var(--fg)",
            marginTop: 4,
          }}
        >
          {phase}
        </div>
      </div>
    </div>
  );
}
