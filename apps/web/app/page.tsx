import Link from "next/link";
import { asResource, createServerKrailApiClient } from "@/lib/krail/api/server";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

const workspaces = [
  {
    href: "/krail-explore" as const,
    eyebrow: "Explore + Evidence",
    title: "Inspect canonical knowledge",
    description: "Search KRAIL records, traverse the graph, inspect sources, and trace provenance.",
  },
  {
    href: "/krail-analyze" as const,
    eyebrow: "Analyze",
    title: "Query canonical data",
    description: "Run bounded KRAIL queries and inspect tables, charts, reproducibility, and source context.",
  },
  {
    href: "/krail-workflows" as const,
    eyebrow: "Workflows",
    title: "Run controlled workflows",
    description: "Inspect workflow truth, choose server-owned permissions, and follow durable live execution.",
  },
  {
    href: "/krail-control" as const,
    eyebrow: "Control Plane",
    title: "Operate the platform",
    description: "Create or link projects and audit Git, sandbox, and execution capability boundaries.",
  },
  {
    href: "/krail-live" as const,
    eyebrow: "Runtime",
    title: "Check project health",
    description: "Open live manifest, health, and source data through the versioned platform API.",
  },
  {
    href: "/krail-preview" as const,
    eyebrow: "Platform map",
    title: "Review the complete control surface",
    description: "Preview the five-workspace product model and its resilient operational states.",
  },
];

export default async function PlatformHome() {
  const api = createServerKrailApiClient();
  const projects = await asResource(() => api.listProjects());
  const projectCount = projects.state === "ready" ? projects.data.length : null;

  return (
    <main className={styles.page}>
      <header className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>RAIL · powered by KRAIL</span>
          <h1>The visual control plane for repo-native knowledge.</h1>
          <p>
            KRAIL owns the ontology, evidence, and workflow truth. RAIL makes it visible,
            operable, and auditable without creating a second data model.
          </p>
        </div>
        <div className={styles.status}>
          <span aria-hidden="true" />
          {projectCount === null ? "Platform API unavailable" : `${projectCount} registered project${projectCount === 1 ? "" : "s"}`}
        </div>
      </header>

      <section className={styles.workspaceSection} aria-labelledby="workspace-heading">
        <div className={styles.sectionHeading}>
          <span className={styles.eyebrow}>Local single-node platform</span>
          <h2 id="workspace-heading">Choose a workspace</h2>
        </div>
        <div className={styles.grid}>
          {workspaces.map((workspace, index) => (
            <Link className={styles.card} href={workspace.href} key={workspace.href}>
              <span className={styles.number}>{String(index + 1).padStart(2, "0")}</span>
              <span className={styles.eyebrow}>{workspace.eyebrow}</span>
              <strong>{workspace.title}</strong>
              <p>{workspace.description}</p>
              <span className={styles.open}>Open workspace →</span>
            </Link>
          ))}
        </div>
      </section>

      <footer className={styles.footer}>
        <span>KRAIL project directories remain canonical.</span>
        <span>Git-backed · source-traceable · permission-aware</span>
      </footer>
    </main>
  );
}
