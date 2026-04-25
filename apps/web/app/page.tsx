import { ProjectCatalogAction } from "@/components/project-catalog-actions";
import { StatusPill } from "@/components/status-pill";
import { fetchProjectCatalog } from "@/lib/api";
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

export default async function LandingPage() {
  const projects = await loadProjects();
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
      <div style={{
        width: "100%",
        maxWidth: 720,
        border: "1px solid var(--border)",
        background: "var(--panel)",
      }}>
        <div style={{
          padding: "14px 20px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "baseline",
          gap: 12,
        }}>
          <span style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: "0.06em",
            color: "var(--fg)",
          }}>
            RAIL
          </span>
          <span style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--muted)",
          }}>
            Project Catalog
          </span>
          <span style={{
            marginLeft: "auto",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            color: "var(--muted)",
          }}>
            {process.env.NEXT_PUBLIC_RAIL_API_URL ?? "http://127.0.0.1:8000/api/v1"}
          </span>
        </div>

        <div style={{ padding: "8px 0" }}>
          <div style={{
            padding: "6px 20px 10px",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--muted)",
          }}>
            Projects
          </div>
          {projects.map((project) => {
            const backendReady = Boolean(project.backendProject?.slug);
            return (
              <div key={project.slug} className="project-link-row" style={{
                padding: "12px 20px",
                borderTop: "1px solid var(--border)",
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) auto",
                alignItems: "center",
                gap: 14,
                transition: "background 120ms",
              }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                    <span style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 13,
                      fontWeight: 600,
                      color: "var(--fg)",
                    }}>
                      {project.name}
                    </span>
                    <StatusPill value={backendReady ? "ready" : project.localExists ? "local" : "clone required"} />
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 5 }}>
                    {project.description}
                  </div>
                  <div style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    color: "var(--muted)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}>
                    {project.localExists ? project.localRepoPath : project.repoUrl}
                  </div>
                </div>
                <ProjectCatalogAction slug={project.slug} localExists={project.localExists} backendReady={backendReady} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
