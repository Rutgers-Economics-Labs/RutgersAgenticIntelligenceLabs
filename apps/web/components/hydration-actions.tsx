"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { rerunHydration } from "@/lib/api";

export function HydrationRerunButton({
  slug,
  pipelineSlug,
  compact = false,
}: {
  slug: string;
  pipelineSlug?: string | null;
  compact?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await rerunHydration(slug, pipelineSlug);
      setMessage(`Queued ${result.pipelineSlug} (${result.jobId.slice(0, 8)})`);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Hydration could not be queued.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: compact ? "column" : "row", alignItems: compact ? "stretch" : "center", gap: 8 }}>
      <button className="command-button primary" type="button" disabled={busy} onClick={run} style={{ display: "inline-flex", alignItems: "center", gap: 7, justifyContent: "center" }}>
        <RefreshCw size={14} />
        {busy ? "Queuing" : "Rerun Hydration"}
      </button>
      {message && (
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
          {message}
        </span>
      )}
    </div>
  );
}
