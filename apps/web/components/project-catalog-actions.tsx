"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { activateCatalogProject } from "@/lib/api";

export function ProjectCatalogAction({
  slug,
  localExists,
  backendReady,
}: {
  slug: string;
  localExists: boolean;
  backendReady: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function activate() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await activateCatalogProject(slug, !localExists);
      const nextSlug = String((result.project as any)?.slug ?? result.catalogProject?.slug ?? slug);
      setMessage(result.status === "clone_required" ? "Clone required on this machine." : "Ready.");
      if (result.status !== "clone_required") {
        router.refresh();
        router.push(`/projects/${nextSlug}` as any);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not prepare project.");
    } finally {
      setBusy(false);
    }
  }

  if (backendReady && localExists) {
    return (
      <button className="command-button primary" type="button" onClick={() => router.push(`/projects/${slug}` as any)}>
        Open
      </button>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
      <button className="command-button primary" type="button" disabled={busy} onClick={activate}>
        {busy ? "Working" : localExists ? "Add Local" : "Clone"}
      </button>
      {message && (
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", maxWidth: 180, textAlign: "right" }}>
          {message}
        </span>
      )}
    </div>
  );
}
