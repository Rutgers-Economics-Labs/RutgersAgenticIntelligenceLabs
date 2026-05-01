"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const API_ROOT = process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1";

type PaletteItem = {
  id: string;
  category: string;
  label: string;
  sub?: string;
  href: string;
};

function navItems(slug: string): PaletteItem[] {
  return [
    { id: "overview", category: "Navigate", label: "Overview", sub: "Mission Control", href: `/projects/${slug}` },
    { id: "agent", category: "Navigate", label: "Agent & Plan", sub: "Chat + task board", href: `/projects/${slug}/agent` },
    { id: "launch", category: "Navigate", label: "Launch", sub: "Start research", href: `/projects/${slug}/launch` },
    { id: "runs", category: "Navigate", label: "Runs", sub: "Agent sessions", href: `/projects/${slug}/runs` },
    { id: "review", category: "Navigate", label: "Review", sub: "Output review", href: `/projects/${slug}/review` },
    { id: "skills", category: "Navigate", label: "Skills", sub: "Playbooks", href: `/projects/${slug}/skills` },
    { id: "sources", category: "Navigate", label: "Sources", sub: "Data sources", href: `/projects/${slug}/sources` },
    { id: "artifacts", category: "Navigate", label: "Artifacts", sub: "Outputs", href: `/projects/${slug}/artifacts` },
    { id: "integrity", category: "Navigate", label: "Integrity", sub: "Assumptions, evidence, lineage", href: `/projects/${slug}/integrity` },
    { id: "repo", category: "Navigate", label: "Repo", sub: "File browser", href: `/projects/${slug}/repo` },
    { id: "ontology", category: "Navigate", label: "Ontology", sub: "Data model", href: `/projects/${slug}/ontology` },
    { id: "settings", category: "Navigate", label: "Settings", sub: "Git, secrets, runners", href: `/projects/${slug}/settings` },
  ];
}

function fuzzyMatch(query: string, text: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  let qi = 0;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) qi++;
  }
  return qi === q.length;
}

export function CommandPalette({ slug }: { slug: string }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [tasks, setTasks] = useState<PaletteItem[]>([]);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    setTimeout(() => inputRef.current?.focus(), 30);

    fetch(`${API_ROOT}/projects/${slug}/planner/board`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data?.tasks) return;
        const items: PaletteItem[] = data.tasks.map((t: any) => ({
          id: t._id ?? t.title,
          category: "Task",
          label: t.title,
          sub: `${t.status ?? "—"} · ${t.agentRole ?? ""}`,
          href: `/projects/${slug}/agent`,
        }));
        setTasks(items);
      })
      .catch(() => {});
  }, [open, slug]);

  const allItems = [...navItems(slug), ...tasks];
  const filtered = allItems.filter(
    (item) =>
      fuzzyMatch(query, item.label) ||
      fuzzyMatch(query, item.sub ?? "") ||
      fuzzyMatch(query, item.category)
  );

  function select(item: PaletteItem) {
    setOpen(false);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    router.push(item.href as any);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter" && filtered[cursor]) {
      select(filtered[cursor]);
    }
  }

  // Group results by category
  const categories = Array.from(new Set(filtered.map((i) => i.category)));

  if (!open) return null;

  return (
    <div
      onClick={() => setOpen(false)}
      style={{
        position: "fixed", inset: 0, zIndex: 300,
        background: "rgba(0,0,0,0.5)",
        display: "flex", alignItems: "flex-start", justifyContent: "center",
        paddingTop: "14vh",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 580, maxWidth: "92vw",
          background: "var(--panel)",
          border: "1px solid var(--border-strong)",
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          display: "flex", flexDirection: "column",
          maxHeight: "62vh",
        }}
      >
        {/* Search input */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "10px 14px",
          borderBottom: "1px solid var(--border)",
        }}>
          <span style={{
            fontFamily: "JetBrains Mono, monospace", fontSize: 11,
            color: "var(--muted)", flexShrink: 0,
          }}>
            ⌘K
          </span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setCursor(0); }}
            onKeyDown={handleKeyDown}
            placeholder="Search pages, tasks..."
            style={{
              flex: 1, background: "none", border: "none", outline: "none",
              fontFamily: "JetBrains Mono, monospace", fontSize: 13,
              color: "var(--fg)",
            }}
          />
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", flexShrink: 0 }}>
            ESC
          </span>
        </div>

        {/* Results */}
        <div ref={listRef} style={{ overflowY: "auto", flex: 1 }}>
          {filtered.length === 0 ? (
            <div style={{
              padding: "28px 14px", textAlign: "center",
              fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)",
            }}>
              No results
            </div>
          ) : (
            categories.map((cat) => (
              <div key={cat}>
                <div style={{
                  padding: "6px 14px 4px",
                  fontFamily: "JetBrains Mono, monospace", fontSize: 9,
                  letterSpacing: "0.14em", textTransform: "uppercase",
                  color: "var(--muted)",
                  borderBottom: "1px solid var(--border)",
                  background: "var(--bg)",
                }}>
                  {cat}
                </div>
                {filtered
                  .filter((i) => i.category === cat)
                  .map((item) => {
                    const idx = filtered.indexOf(item);
                    const active = cursor === idx;
                    return (
                      <div
                        key={item.id}
                        onClick={() => select(item)}
                        onMouseEnter={() => setCursor(idx)}
                        style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "9px 14px",
                          background: active ? "var(--panel-alt)" : "transparent",
                          cursor: "pointer",
                          borderBottom: "1px solid var(--border)",
                        }}
                      >
                        <div>
                          <div style={{
                            fontSize: 13, color: "var(--fg)",
                            fontWeight: active ? 600 : 400,
                          }}>
                            {item.label}
                          </div>
                          {item.sub && (
                            <div style={{
                              fontFamily: "JetBrains Mono, monospace", fontSize: 10,
                              color: "var(--muted)", marginTop: 2,
                            }}>
                              {item.sub}
                            </div>
                          )}
                        </div>
                        {active && (
                          <span style={{
                            fontFamily: "JetBrains Mono, monospace", fontSize: 11,
                            color: "var(--muted)",
                          }}>
                            ↵
                          </span>
                        )}
                      </div>
                    );
                  })}
              </div>
            ))
          )}
        </div>

        {/* Footer hint */}
        <div style={{
          padding: "6px 14px",
          borderTop: "1px solid var(--border)",
          display: "flex", gap: 16,
        }}>
          {[["↑↓", "navigate"], ["↵", "open"], ["Esc", "close"]].map(([key, label]) => (
            <span key={key} style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)", display: "flex", gap: 5, alignItems: "center" }}>
              <span style={{ background: "var(--panel-alt)", border: "1px solid var(--border)", padding: "1px 5px", fontSize: 9 }}>{key}</span>
              {label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
