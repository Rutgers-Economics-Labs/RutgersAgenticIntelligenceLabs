"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createProjectFromBrief } from "@/lib/api";

const PLACEHOLDER = `e.g. "Analyze the relationship between housing prices and unemployment across NJ counties over the last decade using Census and FRED data."`;

type Phase = "idle" | "creating" | "done" | "error";

export default function NewProjectPage() {
  const router = useRouter();
  const [brief, setBrief] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");

  async function handleCreate() {
    if (!brief.trim()) return;
    setPhase("creating");
    setError(null);
    setStatus("Generating project structure…");

    try {
      setStatus("Creating GitHub repo and scaffolding files…");
      const result = await createProjectFromBrief(brief.trim());
      const slug = result?.project?.slug;
      if (!slug) throw new Error("No project slug returned.");
      setStatus("Done. Launching project…");
      setPhase("done");
      router.push(`/projects/${slug}/agent?welcome=1`);
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  const busy = phase === "creating" || phase === "done";

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg)",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "40px 24px",
    }}>
      <div style={{ width: "100%", maxWidth: 640 }}>

        {/* Header */}
        <div style={{ marginBottom: 32 }}>
          <a href="/" style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 24, color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11, letterSpacing: "0.1em" }}>
            ← RAIL
          </a>
          <h1 style={{ margin: 0, fontFamily: "JetBrains Mono, monospace", fontSize: 20, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--fg)" }}>
            New Project
          </h1>
          <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--muted)", lineHeight: 1.6 }}>
            Describe what you want to research. RAIL will generate an ontology, data sources, and pipeline — then create a GitHub repo.
          </p>
        </div>

        {/* Brief input */}
        <div style={{ border: "1px solid var(--border)", background: "var(--panel)" }}>
          <div style={{ padding: "8px 14px 6px", borderBottom: "1px solid var(--border)" }}>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--muted)" }}>
              Research Brief
            </span>
          </div>
          <textarea
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder={PLACEHOLDER}
            disabled={busy}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleCreate();
            }}
            style={{
              display: "block",
              width: "100%",
              minHeight: 140,
              padding: "14px",
              background: "transparent",
              border: "none",
              outline: "none",
              resize: "vertical",
              fontFamily: "Inter, sans-serif",
              fontSize: 13,
              lineHeight: 1.6,
              color: "var(--fg)",
              boxSizing: "border-box",
              opacity: busy ? 0.5 : 1,
            }}
          />
          <div style={{
            padding: "10px 14px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
              {busy ? status : "⌘ + Enter to create"}
            </span>
            <button
              onClick={handleCreate}
              disabled={busy || !brief.trim()}
              style={{
                padding: "6px 16px",
                background: busy || !brief.trim() ? "var(--panel-alt)" : "var(--fg)",
                color: busy || !brief.trim() ? "var(--muted)" : "var(--bg)",
                border: "1px solid var(--border-strong)",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 11,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                cursor: busy || !brief.trim() ? "not-allowed" : "pointer",
              }}
            >
              {phase === "creating" ? "Creating…" : phase === "done" ? "Launching…" : "Create Project"}
            </button>
          </div>
        </div>

        {/* Error */}
        {phase === "error" && error && (
          <div style={{
            marginTop: 16,
            padding: "12px 14px",
            border: "1px solid var(--s-failed)",
            background: "var(--panel)",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11,
            color: "var(--s-failed)",
          }}>
            {error}
          </div>
        )}

        {/* Progress */}
        {phase === "creating" && (
          <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 6 }}>
            {[
              "Generating project structure",
              "Creating GitHub repo",
              "Scaffolding files",
              "Registering project",
            ].map((step, i) => (
              <div key={step} style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 11,
                color: "var(--muted)",
              }}>
                <span style={{ opacity: 0.4 + i * 0.15 }}>{"▸"}</span>
                {step}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
