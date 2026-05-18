"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Wrench } from "lucide-react";
import { reconcileCommandCenter } from "@/lib/api";

export function ReconcileProjectButton({ slug }: { slug: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await reconcileCommandCenter(slug);
      if (!result.hasChanges) {
        setMessage("No drift repairs were needed.");
      } else {
        const changed = [
          ...result.removedTaskFiles,
          ...result.updatedTaskIds,
          ...result.repairedSessionIds,
          ...result.repairedAuditSessionIds,
        ];
        setMessage(`Reconciled ${changed.length} item(s).`);
      }
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Reconcile failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <button
        className="command-button"
        type="button"
        disabled={busy}
        onClick={run}
        style={{ display: "inline-flex", alignItems: "center", gap: 7, justifyContent: "center" }}
      >
        <Wrench size={14} />
        {busy ? "Reconciling" : "Repair Drift"}
      </button>
      {message ? (
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
          {message}
        </span>
      ) : null}
    </div>
  );
}
