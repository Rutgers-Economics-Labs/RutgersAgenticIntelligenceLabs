"use client";

import React, { useState, useEffect } from "react";
import { fetchOntologyInstances } from "@/lib/api";

interface EntityExplorerProps {
  projectId: string;
  classes: { name: string; count: number }[];
}

export function EntityExplorer({ projectId, classes }: EntityExplorerProps) {
  const [selectedClass, setSelectedClass] = useState<string>(classes[0]?.name || "");
  const [instances, setInstances] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    if (!selectedClass) return;
    loadInstances(selectedClass, 1);
  }, [selectedClass, projectId]);

  async function loadInstances(className: string, p: number) {
    setLoading(true);
    try {
      const data = await fetchOntologyInstances(projectId, className, { page: p, limit: 10 });
      setInstances(data.items || []);
      setTotal(data.total || 0);
      setPage(p);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div style={{ display: "flex", gap: "8px", overflowX: "auto", padding: "4px 0" }}>
        {classes.map((cls) => (
          <button
            key={cls.name}
            onClick={() => setSelectedClass(cls.name)}
            style={{
              padding: "4px 10px",
              background: selectedClass === cls.name ? "var(--fg)" : "var(--panel)",
              color: selectedClass === cls.name ? "var(--bg)" : "var(--fg)",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              fontSize: "11px",
              fontFamily: "JetBrains Mono, monospace",
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            {cls.name} ({cls.count})
          </button>
        ))}
      </div>

      <div style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: "4px" }}>
        {loading ? (
          <div style={{ padding: "20px", textAlign: "center", color: "var(--muted)", fontSize: "11px" }}>Loading instances...</div>
        ) : instances.length === 0 ? (
          <div style={{ padding: "20px", textAlign: "center", color: "var(--muted)", fontSize: "11px" }}>No instances found.</div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", fontFamily: "JetBrains Mono, monospace" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}>
                <th style={{ padding: "8px", textAlign: "left", width: "30%" }}>ID</th>
                <th style={{ padding: "8px", textAlign: "left" }}>Properties</th>
              </tr>
            </thead>
            <tbody>
              {instances.map((inst, i) => (
                <tr key={i} style={{ borderBottom: i === instances.length - 1 ? "none" : "1px solid var(--border)" }}>
                  <td style={{ padding: "8px", verticalAlign: "top", color: "var(--s-running)" }}>{inst.id}</td>
                  <td style={{ padding: "8px" }}>
                    {Object.entries(inst.properties || {}).map(([k, v]) => (
                      <div key={k} style={{ marginBottom: "2px" }}>
                        <span style={{ color: "var(--muted)" }}>{k}:</span>{" "}
                        <span style={{ color: "var(--fg)" }}>{String(v)}</span>
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {total > 10 && (
        <div style={{ display: "flex", justifyContent: "center", gap: "10px", alignItems: "center" }}>
          <button 
            disabled={page === 1} 
            onClick={() => loadInstances(selectedClass, page - 1)}
            style={{ padding: "4px 8px", background: "var(--panel)", border: "1px solid var(--border)", fontSize: "10px", cursor: page === 1 ? "default" : "pointer" }}
          >
            Prev
          </button>
          <span style={{ fontSize: "10px", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace" }}>
            Page {page} of {Math.ceil(total / 10)}
          </span>
          <button 
            disabled={page * 10 >= total} 
            onClick={() => loadInstances(selectedClass, page + 1)}
            style={{ padding: "4px 8px", background: "var(--panel)", border: "1px solid var(--border)", fontSize: "10px", cursor: page * 10 >= total ? "default" : "pointer" }}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
