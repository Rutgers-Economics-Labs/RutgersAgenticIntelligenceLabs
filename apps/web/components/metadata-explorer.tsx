"use client";

import React, { useState, useEffect } from "react";
import { fetchRepoPath } from "@/lib/api";

interface MetadataExplorerProps {
  slug: string;
}

export function MetadataExplorer({ slug }: MetadataExplorerProps) {
  const [currentPath, setCurrentPath] = useState<string>("");
  const [entries, setEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [metadata, setMetadata] = useState<any>(null);

  useEffect(() => {
    loadPath(currentPath);
  }, [currentPath, slug]);

  async function loadPath(path: string) {
    setLoading(true);
    try {
      const data = await fetchRepoPath(slug, path);
      if (data.kind === "directory") {
        setEntries(data.entries || []);
        setMetadata(null);
      } else {
        setMetadata(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  const breadcrumbs = currentPath.split("/").filter(Boolean);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px", fontFamily: "JetBrains Mono, monospace", fontSize: "11px" }}>
      <div style={{ display: "flex", gap: "6px", alignItems: "center", background: "var(--panel)", padding: "6px 12px", border: "1px solid var(--border)", borderRadius: "4px" }}>
        <span 
          onClick={() => setCurrentPath("")} 
          style={{ cursor: "pointer", color: "var(--s-running)" }}
        >
          root
        </span>
        {breadcrumbs.map((b, i) => (
          <React.Fragment key={i}>
            <span style={{ color: "var(--muted)" }}>/</span>
            <span 
              onClick={() => setCurrentPath(breadcrumbs.slice(0, i + 1).join("/"))} 
              style={{ cursor: "pointer", color: "var(--s-running)" }}
            >
              {b}
            </span>
          </React.Fragment>
        ))}
      </div>

      <div style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: "4px", minHeight: "200px" }}>
        {loading ? (
          <div style={{ padding: "20px", textAlign: "center", color: "var(--muted)" }}>Loading...</div>
        ) : metadata ? (
          <div style={{ padding: "12px" }}>
            <div style={{ marginBottom: "12px", paddingBottom: "8px", borderBottom: "1px solid var(--border)", color: "var(--s-done)", fontWeight: "bold" }}>
              FILE: {metadata.path}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "100px 1fr", gap: "8px" }}>
              <div style={{ color: "var(--muted)" }}>Size:</div>
              <div>{(metadata.sizeBytes / 1024).toFixed(2)} KB</div>
              <div style={{ color: "var(--muted)" }}>Extension:</div>
              <div>{metadata.extension}</div>
              <div style={{ color: "var(--muted)" }}>Kind:</div>
              <div>{metadata.syntaxKind}</div>
            </div>
            <button 
              onClick={() => {
                const parts = currentPath.split("/");
                parts.pop();
                setCurrentPath(parts.join("/"));
              }}
              style={{ marginTop: "16px", padding: "4px 8px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", cursor: "pointer" }}
            >
              Back to Folder
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {entries.length === 0 && <div style={{ padding: "20px", textAlign: "center", color: "var(--muted)" }}>Folder is empty.</div>}
            {entries.map((entry) => (
              <div 
                key={entry.path}
                onClick={() => setCurrentPath(entry.path)}
                style={{ 
                  padding: "8px 12px", 
                  borderBottom: "1px solid var(--border)", 
                  display: "flex", 
                  alignItems: "center", 
                  gap: "8px", 
                  cursor: "pointer",
                  background: entry.kind === "directory" ? "transparent" : "transparent"
                }}
              >
                <span style={{ color: entry.kind === "directory" ? "var(--s-running)" : "var(--muted)" }}>
                  {entry.kind === "directory" ? "📁" : "📄"}
                </span>
                <span style={{ color: entry.kind === "directory" ? "var(--fg)" : "var(--fg)" }}>
                  {entry.name}
                </span>
                {entry.extension && (
                  <span style={{ marginLeft: "auto", color: "var(--muted)", fontSize: "9px" }}>
                    .{entry.extension}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
