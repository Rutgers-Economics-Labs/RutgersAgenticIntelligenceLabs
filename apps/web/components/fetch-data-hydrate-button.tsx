"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Database, Loader2 } from "lucide-react";
import { fetchHydrationJob, runProjectDataPipeline } from "@/lib/api";

type Props = {
  slug: string;
  pipelineSlug?: string | null;
  variant?: "primary" | "compact";
};

export function FetchDataHydrateButton({ slug, pipelineSlug, variant = "primary" }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  useEffect(() => {
    if (!jobId) return;
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const job = await fetchHydrationJob(jobId);
        const status = String(job.status || "unknown");
        setJobStatus(status);
        if (status === "completed" || status === "failed" || status === "cancelled") {
          stopPolling();
          setBusy(false);
          router.refresh();
          if (status === "completed") {
            setMessage("Hydration finished. Ontology and DuckDB are updated.");
          } else {
            setMessage(`Pipeline ended: ${status}${job.error ? ` — ${job.error}` : ""}`);
          }
        }
      } catch {
        /* keep polling while job record propagates */
      }
    }, 2500);
    return () => stopPolling();
  }, [jobId, router, stopPolling]);

  async function run() {
    setBusy(true);
    setMessage(null);
    setJobStatus(null);
    setJobId(null);
    try {
      const result = await runProjectDataPipeline(slug, pipelineSlug, true);
      const id = result.hydration?.jobId;
      if (!id) {
        throw new Error("Pipeline did not return a job id.");
      }
      setJobId(id);
      setJobStatus("queued");
      setMessage(result.message);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not start the data pipeline.");
      setBusy(false);
    }
  }

  const label =
    busy && jobStatus
      ? jobStatus === "queued"
        ? "Fetching data…"
        : jobStatus === "running"
          ? "Hydrating ontology…"
          : `Pipeline: ${jobStatus}`
      : "Fetch data & hydrate";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: variant === "compact" ? "column" : "row",
        alignItems: variant === "compact" ? "stretch" : "center",
        gap: 8,
      }}
    >
      <button
        className={variant === "primary" ? "command-button primary" : "command-button"}
        type="button"
        disabled={busy}
        onClick={run}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          justifyContent: "center",
          width: variant === "compact" ? "100%" : undefined,
        }}
      >
        {busy ? (
          <Loader2 size={14} style={{ animation: "rail-spin 1s linear infinite" }} />
        ) : (
          <Database size={14} />
        )}
        {label}
      </button>
      {message && (
        <span
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            color: "var(--muted)",
            lineHeight: 1.4,
          }}
          title={jobId ?? undefined}
        >
          {message}
          {jobId ? ` · job ${jobId.slice(0, 8)}` : ""}
        </span>
      )}
    </div>
  );
}
