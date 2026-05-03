import Link from "next/link";
import { ProjectCatalogAction } from "@/components/project-catalog-actions";
import { StatusPill } from "@/components/status-pill";
import { fetchProjectCatalog, fetchCommandCenter } from "@/lib/api";
import { ProjectCatalogItem } from "@/lib/types";

const FALLBACK_PROJECTS: ProjectCatalogItem[] = [
  {
    slug: "sad",
    name: "RAIL-sad",
    description: "NJ-focused project with planner state and ontology sources.",
    repoUrl: "",
    directory: "RAIL-sad",
    localRepoPath: "",
    localExists: true,
    manifestExists: true,
    needsClone: false,
    backendProject: { slug: "sad", name: "RAIL-sad" },
  },
];

async function loadProjects(): Promise<ProjectCatalogItem[]> {
  try {
    const catalog = await fetchProjectCatalog();
    return catalog.projects.length ? catalog.projects : FALLBACK_PROJECTS;
  } catch {
    return FALLBACK_PROJECTS;
  }
}

type Progress = { done: number; total: number };

async function loadProgressMap(projects: ProjectCatalogItem[]): Promise<Record<string, Progress>> {
  const withBackend = projects.filter((p) => p.backendProject?.slug);
  const results = await Promise.allSettled(withBackend.map((p) => fetchCommandCenter(p.slug)));
  const map: Record<string, Progress> = {};
  withBackend.forEach((p, i) => {
    const r = results[i];
    if (r.status === "fulfilled") {
      const counts = r.value.taskCounts;
      const done = (counts.byStatus["done"] ?? 0) + (counts.byStatus["completed"] ?? 0);
      map[p.slug] = { done, total: counts.total };
    }
  });
  return map;
}

function progressColor(pct: number): string {
  if (pct >= 0.8) return "#22c55e";
  if (pct >= 0.4) return "#f59e0b";
  return "var(--muted)";
}

function ProgressBar({ progress }: { progress: Progress }) {
  const pct = progress.total > 0 ? progress.done / progress.total : 0;
  return (
    <div style={{ marginTop: 7 }}>
      <div
        style={{
          height: 3,
          background: "var(--border)",
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${Math.round(pct * 100)}%`,
            background: progressColor(pct),
            borderRadius: 2,
            transition: "width 0.4s ease",
          }}
        />
      </div>
      <div
        style={{
          marginTop: 4,
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "var(--muted)",
        }}
      >
        {progress.done} / {progress.total} tasks done
      </div>
    </div>
  );
}

export default async function LandingPage() {
  const projects = await loadProjects();
  const progressMap = await loadProgressMap(projects).catch(() => ({} as Record<string, Progress>));

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "40px 24px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 720,
          border: "1px solid var(--border)",
          background: "var(--panel)",
        }}
      >
        <div
          style={{
            padding: "14px 20px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <img
            src="/rel-logo.jpeg"
            alt="Rutgers Economics Labs"
            style={{
              width: 30,
              height: 30,
              objectFit: "contain",
              background: "#fff",
              border: "1px solid var(--border)",
            }}
          />
          <span
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: "0.06em",
              color: "var(--fg)",
            }}
          >
            RAIL
          </span>
          <span
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--muted)",
            }}
          >
            Project Catalog
          </span>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
            <span
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                color: "var(--muted)",
              }}
            >
              {process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1"}
            </span>
            <Link
              href="/projects/new"
              style={{
                padding: "4px 10px",
                border: "1px solid var(--border-strong)",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--fg)",
                background: "var(--panel)",
              }}
            >
              + New
            </Link>
          </div>
        </div>

        <div style={{ padding: "8px 0" }}>
          <div
            style={{
              padding: "6px 20px 10px",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--muted)",
            }}
          >
            Projects
          </div>
          {projects.map((project) => {
            const backendReady = Boolean(project.backendProject?.slug);
            const progress = progressMap[project.slug];
            return (
              <div
                key={project.slug}
                className="project-link-row"
                style={{
                  padding: "12px 20px",
                  borderTop: "1px solid var(--border)",
                  display: "grid",
                  gridTemplateColumns: "minmax(0, 1fr) auto",
                  alignItems: "center",
                  gap: 14,
                  transition: "background 120ms",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      flexWrap: "wrap",
                      marginBottom: 4,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 13,
                        fontWeight: 600,
                        color: "var(--fg)",
                      }}
                    >
                      {project.name}
                    </span>
                    <StatusPill
                      value={
                        backendReady
                          ? "ready"
                          : project.localExists
                          ? "local"
                          : "clone required"
                      }
                    />
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 5 }}>
                    {project.description}
                  </div>
                  <div
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      color: "var(--muted)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {project.localExists ? project.localRepoPath : project.repoUrl}
                  </div>
                  {progress && <ProgressBar progress={progress} />}
                </div>
                <ProjectCatalogAction
                  slug={project.slug}
                  localExists={project.localExists}
                  backendReady={backendReady}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
