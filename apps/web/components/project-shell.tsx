"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";

const NAV = [
  { label: "Overview",  suffix: "",         key: "overview"  },
  { label: "Launch",    suffix: "/launch",  key: "launch"    },
  { label: "Planner",   suffix: "/planner", key: "planner"   },
  { label: "Runs",      suffix: "/runs",    key: "sessions"  },
  { label: "Review",    suffix: "/review",  key: "review"    },
  { label: "Skills",    suffix: "/skills",  key: "skills"    },
  { label: "Sources",   suffix: "/sources", key: "sources"   },
  { label: "Artifacts", suffix: "/artifacts", key: "artifacts" },
  { label: "Repo",      suffix: "/repo",    key: "repo"      },
  { label: "Ontology",  suffix: "/ontology",key: "ontology"  },
];

const REPO_SHORTCUTS = [
  { label: "current_plan.md",  path: "research_plan/current_plan.md" },
  { label: "task_board.md",    path: "research_plan/task_board.md"   },
  { label: "tasks/",           path: "research_plan/tasks"           },
  { label: "agents/",          path: "agents"                        },
  { label: ".ontology/",       path: ".ontology"                     },
];

function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    setDark(document.documentElement.dataset.theme === "dark");
  }, []);
  function toggle() {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("rail-theme", next); } catch {}
    setDark(!dark);
  }
  return (
    <button
      onClick={toggle}
      className="nav-link w-full border-none text-left"
      style={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace", letterSpacing: "0.12em", textTransform: "uppercase" }}
    >
      {dark ? "Light mode" : "Dark mode"}
    </button>
  );
}

export function ProjectShell({
  slug,
  title,
  section,
  children,
  rightRail,
}: {
  slug: string;
  title: string;
  section: string;
  children: ReactNode;
  rightRail?: ReactNode;
}) {
  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "var(--bg)" }}>

      {/* ── Left sidebar ─────────────────────────────────────────── */}
      <aside style={{
        width: 220,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        borderRight: "1px solid var(--border)",
        background: "var(--panel)",
        overflow: "hidden",
      }}>

        {/* Brand */}
        <div style={{ padding: "12px 12px 10px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <img
              src="/rel-logo.jpeg"
              alt="Rutgers Economics Labs"
              style={{
                width: 34,
                height: 34,
                objectFit: "contain",
                background: "#fff",
                border: "1px solid var(--border)",
              }}
            />
            <div style={{ minWidth: 0 }}>
              <div className="rail-label" style={{ fontSize: 9 }}>Rutgers Economics Labs</div>
              <div style={{
                marginTop: 4,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 15,
                fontWeight: 700,
                letterSpacing: "-0.01em",
                color: "var(--fg)",
              }}>
                RAIL
              </div>
            </div>
          </div>
        </div>

        {/* Project */}
        <div style={{ padding: "10px 12px 8px", borderBottom: "1px solid var(--border)" }}>
          <div className="rail-label">Project</div>
          <div style={{
            marginTop: 5,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 12,
            fontWeight: 600,
            color: "var(--fg)",
            letterSpacing: "-0.01em",
          }}>
            {slug}
          </div>
        </div>

        {/* Nav */}
        <div style={{ borderBottom: "1px solid var(--border)" }}>
          <div style={{ padding: "8px 12px 4px" }}>
            <span className="rail-label">Surfaces</span>
          </div>
          {NAV.map((tab) => {
            const active = section === tab.key;
            return (
              <Link
                key={tab.key}
                href={`/projects/${slug}${tab.suffix}`}
                className={`nav-link${active ? " active" : ""}`}
              >
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, letterSpacing: "0.06em" }}>
                  {tab.label}
                </span>
                {active && (
                  <span style={{ fontSize: 9, opacity: 0.6 }}>●</span>
                )}
              </Link>
            );
          })}
        </div>

        {/* Repo shortcuts */}
        <div style={{ borderBottom: "1px solid var(--border)" }}>
          <div style={{ padding: "8px 12px 4px" }}>
            <span className="rail-label">Repo</span>
          </div>
          {REPO_SHORTCUTS.map((s) => (
            <Link
              key={s.path}
              href={`/projects/${slug}/repo?path=${encodeURIComponent(s.path)}`}
              className="nav-link"
            >
              <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
                {s.label}
              </span>
            </Link>
          ))}
        </div>

        {/* Bottom controls */}
        <div style={{ marginTop: "auto", borderTop: "1px solid var(--border)" }}>
          <ThemeToggle />
        </div>
      </aside>

      {/* ── Main area ────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflow: "hidden" }}>

        {/* Top bar */}
        <header style={{
          height: 40,
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 16px",
          borderBottom: "1px solid var(--border)",
          background: "var(--panel)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span className="rail-label">{section}</span>
            <span style={{ color: "var(--border)", fontSize: 12 }}>·</span>
            <span style={{ fontSize: 12, color: "var(--fg)", fontWeight: 500 }}>{title}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Link
              href={`/projects/${slug}/launch`}
              style={{
                border: "1px solid var(--border-strong)",
                padding: "3px 8px",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--fg)",
              }}
            >
              Start Research
            </Link>
            <span className="rail-label">{slug}</span>
          </div>
        </header>

        {/* Content + optional right rail */}
        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
          <main style={{ flex: 1, overflow: "auto", minWidth: 0 }}>
            {children}
          </main>
          {rightRail && (
            <aside style={{
              width: 280,
              flexShrink: 0,
              borderLeft: "1px solid var(--border)",
              overflow: "auto",
              background: "var(--panel)",
            }}>
              {rightRail}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
