"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Wrench } from "lucide-react";
import { reconcileCommandCenter } from "@/lib/api";

function summarizeReconcileResult(result: Awaited<ReturnType<typeof reconcileCommandCenter>>): string {
  const repairBuckets = [
    result.removedTaskFiles.length,
    result.updatedTaskIds.length,
    result.updatedApprovalIds?.length ?? 0,
    result.repairedSecretPolicyRoles?.length ?? 0,
    result.repairedRoleConfigPaths?.length ?? 0,
    result.repairedRunningAgentStatusSessionIds?.length ?? 0,
    result.repairedRunningAgentRoleSessionIds?.length ?? 0,
    result.repairedRunningAgentRunnerSessionIds?.length ?? 0,
    result.repairedSessionIds.length,
    result.repairedAuditSessionIds.length,
    result.repairedOntologyArtifact?.repaired ? 1 : 0,
  ];
  const repairedItemCount = repairBuckets.reduce((sum, count) => sum + count, 0);
  const repairedClassCount = repairBuckets.filter((count) => count > 0).length;
  return `Reconciled ${repairedItemCount} item(s) across ${repairedClassCount} drift class(es).`;
}

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
        setMessage(summarizeReconcileResult(result));
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
