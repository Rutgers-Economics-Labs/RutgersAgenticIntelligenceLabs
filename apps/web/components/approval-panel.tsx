"use client";

import { useEffect, useState, useTransition } from "react";
import { resolveApproval } from "@/lib/api";
import { StatusPill } from "@/components/status-pill";

function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="empty-state">
      <div style={{ fontWeight: 600, color: "var(--fg)", marginBottom: 4 }}>{title}</div>
      {detail && <div style={{ color: "var(--muted)" }}>{detail}</div>}
    </div>
  );
}

export function ApprovalPanel({
  approvals,
  slug,
}: {
  approvals: Array<Record<string, unknown>>;
  slug: string;
}) {
  const [items, setItems] = useState(approvals);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setItems(approvals);
  }, [approvals]);

  async function act(approvalId: string, status: "granted" | "rejected") {
    setError(null);
    startTransition(async () => {
      try {
        const updated = await resolveApproval(slug, approvalId, status);
        setItems((prev) =>
          prev.map((a) =>
            String(a._id) === approvalId ? { ...a, status: updated.status ?? status } : a
          )
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to resolve approval");
      }
    });
  }

  if (!items.length) {
    return <EmptyState title="No approvals pending" detail="Write-capable agent work will appear here before execution." />;
  }

  return (
    <div>
      {error && (
        <div style={{ padding: "6px 14px", color: "var(--s-failed)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
          {error}
        </div>
      )}
      {items.map((approval, index) => {
        const id = String(approval._id ?? index);
        const status = String(approval.status ?? "pending");
        const isPending = status === "pending";
        return (
          <div key={id} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <div style={{ fontWeight: 600, color: "var(--fg)", fontSize: 12 }}>
                  {String(approval.approvalType ?? "approval")}
                </div>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                  {String(approval.requestedByRole ?? "planner")}
                  {approval.taskId ? ` · ${String(approval.taskId)}` : ""}
                </div>
              </div>
              <StatusPill value={status} />
            </div>
            {isPending && (
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  onClick={() => act(id, "granted")}
                  disabled={pending}
                  style={{
                    flex: 1,
                    padding: "4px 0",
                    background: pending ? "var(--panel-alt)" : "var(--fg)",
                    color: pending ? "var(--muted)" : "var(--bg)",
                    border: "1px solid var(--border-strong)",
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    cursor: pending ? "not-allowed" : "pointer",
                  }}
                >
                  Approve
                </button>
                <button
                  onClick={() => act(id, "rejected")}
                  disabled={pending}
                  style={{
                    padding: "4px 8px",
                    background: "none",
                    color: "var(--muted)",
                    border: "1px solid var(--border)",
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    cursor: pending ? "not-allowed" : "pointer",
                  }}
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
