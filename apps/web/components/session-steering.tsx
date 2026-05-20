"use client";

import { useState } from "react";
import { cancelRunnerSession, reconcileCommandCenter } from "@/lib/api";

const CANCELLABLE = new Set(["running", "awaiting_approval", "awaiting_input", "blocked"]);

/**
 * First-class steering actions for the session row.
 *
 * Replaces the chat-only steering loop called out in
 * docs/future-spec-ui-and-control-plane.md#steering-actions. Specifically:
 *   - "Cancel"  → POST /runners/{runner}/sessions/{id}/cancel (existing)
 *   - "Reconcile drift" → POST /projects/{slug}/command-center/reconcile
 *
 * The reconcile button is global by design: the existing reconciliation
 * service already sweeps stale, zombie, and audit-stale sessions in one pass,
 * and exposing it per-row would invite operators to think drift is
 * per-session when it usually isn't.
 */
export function SessionSteering({
  slug,
  sessionId,
  runner,
  status,
  staleness,
}: {
  slug: string;
  sessionId?: string;
  runner?: string;
  status: string;
  staleness?: "stale" | "zombie" | "active" | null;
}) {
  const [busy, setBusy] = useState<"" | "cancel" | "reconcile">("");
  const [msg, setMsg] = useState<string>("");

  const canCancel = !!sessionId && !!runner && CANCELLABLE.has(status);
  const showReconcile = staleness === "stale" || staleness === "zombie";

  async function handleCancel() {
    if (!sessionId || !runner) return;
    setBusy("cancel");
    setMsg("");
    try {
      await cancelRunnerSession(runner, sessionId);
      setMsg("cancel requested");
    } catch (e: any) {
      setMsg(`failed: ${e?.message ?? "unknown error"}`);
    } finally {
      setBusy("");
    }
  }

  async function handleReconcile() {
    setBusy("reconcile");
    setMsg("");
    try {
      const r = await reconcileCommandCenter(slug);
      setMsg(r.hasChanges ? "reconciled" : "no drift detected");
    } catch (e: any) {
      setMsg(`failed: ${e?.message ?? "unknown error"}`);
    } finally {
      setBusy("");
    }
  }

  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      {canCancel ? (
        <button
          type="button"
          onClick={handleCancel}
          disabled={busy === "cancel"}
          className="steering-btn"
          style={{ borderColor: "rgba(239,68,68,0.4)", color: "#991b1b" }}
        >
          {busy === "cancel" ? "…" : "Cancel"}
        </button>
      ) : null}
      {showReconcile ? (
        <button
          type="button"
          onClick={handleReconcile}
          disabled={busy === "reconcile"}
          className="steering-btn"
        >
          {busy === "reconcile" ? "…" : "Reconcile drift"}
        </button>
      ) : null}
      {msg ? (
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
          {msg}
        </span>
      ) : null}
    </div>
  );
}
