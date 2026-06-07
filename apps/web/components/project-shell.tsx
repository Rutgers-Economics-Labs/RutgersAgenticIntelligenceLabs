"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { AgentMonitor } from "@/components/agent-monitor";
import { CommandPalette } from "@/components/command-palette";
import { LiveOutputPanel } from "@/components/live-output-panel";
import { PlannerCommandBar } from "@/components/planner-command-bar";

const NAV_GROUPS: Array<{ title: string; items: Array<{ label: string; suffix: string; key: string }> }> = [
  {
    title: "Control",
    items: [
      { label: "Overview", suffix: "", key: "overview" },
      { label: "Zen Mode", suffix: "/zen", key: "zen" },
      { label: "Dashboard", suffix: "/dashboard", key: "dashboard" },
    ],
  },
  {
    title: "Agents",
    items: [
      { label: "Planner", suffix: "/planner", key: "planner" },
      { label: "Launch", suffix: "/launch", key: "launch" },
      { label: "Sessions", suffix: "/runs", key: "sessions" },
      { label: "Review", suffix: "/review", key: "review" },
    ],
  },
  {
    title: "Evidence",
    items: [
      { label: "Sources", suffix: "/sources", key: "sources" },
      { label: "Artifacts", suffix: "/artifacts", key: "artifacts" },
      { label: "Integrity", suffix: "/integrity", key: "integrity" },
      { label: "Ontology", suffix: "/ontology", key: "ontology" },
    ],
  },
  {
    title: "Project",
    items: [
      { label: "Repo", suffix: "/repo", key: "repo" },
      { label: "Settings", suffix: "/settings", key: "settings" },
    ],
  },
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

function topbarActionForSection(slug: string, section: string): { label: string; href: string } {
  if (section === "launch") {
    return { label: "Open Planner", href: `/projects/${slug}/planner` };
  }
  if (section === "planner") {
    return { label: "Open Review", href: `/projects/${slug}/review` };
  }
  if (section === "agent") {
    return { label: "Open Planner", href: `/projects/${slug}/planner` };
  }
  if (section === "review") {
    return { label: "Back to Overview", href: `/projects/${slug}` };
  }
  if (section === "dashboard") {
    return { label: "Open Ontology", href: `/projects/${slug}/ontology` };
  }
  if (section === "sources") {
    return { label: "Open Dashboard", href: `/projects/${slug}/dashboard` };
  }
  if (section === "ontology") {
    return { label: "Open Dashboard", href: `/projects/${slug}/dashboard` };
  }
  if (section === "artifacts") {
    return { label: "Check Integrity", href: `/projects/${slug}/integrity` };
  }
  if (section === "integrity") {
    return { label: "Open Review", href: `/projects/${slug}/review` };
  }
  if (section === "sessions") {
    return { label: "Open Review", href: `/projects/${slug}/review` };
  }
  if (section === "repo" || section === "settings") {
    return { label: "Back to Overview", href: `/projects/${slug}` };
  }
  if (section === "zen") {
    return { label: "Open Planner", href: `/projects/${slug}/planner` };
  }
  return { label: "Open Planner", href: `/projects/${slug}/planner` };
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
  const topbarAction = topbarActionForSection(slug, section);
  return (
    <div className="shell-root">
      <CommandPalette slug={slug} />
      <LiveOutputPanel slug={slug} />

      <aside className="shell-sidebar">

        <div className="shell-sidebar-section shell-brand">
          <Link href="/" className="shell-brand-link">
            <img
              src="/rel-logo.jpeg"
              alt="Rutgers Economics Labs"
              className="shell-brand-mark"
            />
            <div style={{ minWidth: 0 }}>
              <div className="rail-label" style={{ fontSize: 9 }}>Rutgers Economics Labs</div>
              <div className="shell-brand-title">RAIL</div>
            </div>
          </Link>
        </div>

        <div className="shell-sidebar-section shell-project-meta">
          <div className="rail-label">Project</div>
          <div className="shell-project-slug">{slug}</div>
        </div>

        <div>
          {NAV_GROUPS.map((group) => (
            <div key={group.title} className="shell-sidebar-section">
              <div className="shell-nav-group-title">
                <span className="rail-label">{group.title}</span>
              </div>
              {group.items.map((tab) => {
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
          ))}
        </div>

        <div className="shell-sidebar-section">
          <AgentMonitor slug={slug} />
        </div>

        <div style={{ marginTop: "auto", borderTop: "1px solid var(--border)" }}>
          <ThemeToggle />
        </div>
      </aside>

      <div className="shell-main">

        <header className="shell-topbar">
          <div className="shell-topbar-title">
            <span className="rail-label">{section}</span>
            <span style={{ color: "var(--border)", fontSize: 12 }}>·</span>
            <span className="shell-section-title">{title}</span>
          </div>
          <div className="shell-topbar-actions">
            <button
              onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }))}
              className="shell-search-button"
            >
              <span>⌘K</span>
              <span style={{ opacity: 0.6 }}>search</span>
            </button>
            <Link
              href={topbarAction.href as any}
              className="shell-launch-link"
            >
              {topbarAction.label}
            </Link>
          </div>
        </header>
        <PlannerCommandBar slug={slug} section={section} />

        <div className="shell-content">
          <main className="shell-main-content">
            {children}
          </main>
          {rightRail && (
            <aside className="shell-right-rail">
              {rightRail}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
