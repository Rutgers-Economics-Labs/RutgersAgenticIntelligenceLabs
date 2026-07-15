import Link from "next/link";
import { asResource, createServerKrailApiClient } from "@/lib/krail/api/server";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

const actions = [
  { href: "/krail-explore", number: "01", title: "Explore knowledge", description: "Search records, follow relationships, and open the sources behind an answer.", action: "Open knowledge" },
  { href: "/krail-workflows", number: "02", title: "Run a workflow", description: "Choose a repeatable workflow, run it safely, and watch progress in real time.", action: "Open workflows" },
  { href: "/krail-analyze", number: "03", title: "Analyze data", description: "Query hydrated project data and inspect results, charts, and provenance.", action: "Open analysis" },
  { href: "/krail-control", number: "04", title: "Manage projects", description: "Add a workspace and review its access, Git state, and execution permissions.", action: "Open projects" },
] as const;

export default async function PlatformHome() {
  const api = createServerKrailApiClient();
  const projects = await asResource(() => api.listProjects());
  const ready = projects.state === "ready";
  const project = ready ? projects.data[0] : undefined;
  const projectCount = ready ? projects.data.length : null;

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>Your local knowledge workspace</span>
          <h1>Turn project knowledge into clear, repeatable work.</h1>
          <p>RAIL gives you one place to explore information, analyze data, and run KRAIL workflows—with the original files and sources always visible.</p>
          {!ready ? <div className={styles.apiWarning} role="status"><strong>RAIL is waiting for the local API.</strong><span>Start the stack with <code>make start</code>, then reload this page.</span></div> : projectCount === 0 ? (
            <div className={styles.onboarding}>
              <span className={styles.step}>First step</span>
              <div><strong>Add your first project</strong><p>Create a new KRAIL workspace or connect an existing local directory.</p></div>
              <Link href="/krail-control#add-project">Add a project →</Link>
            </div>
          ) : (
            <div className={styles.currentProject}>
              <span className={styles.liveDot} aria-hidden="true" />
              <div><small>Ready to work</small><strong>{project?.displayName}</strong></div>
              <Link href={project ? { pathname: "/krail-explore", query: { project: project.projectId } } : "/krail-explore"}>Continue →</Link>
            </div>
          )}
        </div>
        <aside className={styles.principle} aria-label="How RAIL works">
          <span className={styles.eyebrow}>Simple by design</span>
          <ol>
            <li><span>1</span><div><strong>Your files stay canonical</strong><p>KRAIL project directories remain the source of truth.</p></div></li>
            <li><span>2</span><div><strong>Every result keeps its sources</strong><p>Evidence and provenance stay one click away.</p></div></li>
            <li><span>3</span><div><strong>Risky actions stay explicit</strong><p>Dry runs are the default; elevated access is opt-in.</p></div></li>
          </ol>
        </aside>
      </section>

      <section className={styles.actions} aria-labelledby="actions-title">
        <div className={styles.sectionHeading}><div><span className={styles.eyebrow}>What do you want to do?</span><h2 id="actions-title">Choose an action</h2></div>{projectCount !== null && <span>{projectCount} project{projectCount === 1 ? "" : "s"}</span>}</div>
        <div className={styles.grid}>
          {actions.map((item) => <Link className={styles.card} href={project && item.href !== "/krail-control" ? { pathname: item.href, query: { project: project.projectId } } : item.href} key={item.href}>
            <span className={styles.number}>{item.number}</span><div><h3>{item.title}</h3><p>{item.description}</p></div><span className={styles.open}>{item.action} →</span>
          </Link>)}
        </div>
      </section>

      <footer className={styles.footer}><span>Local-first · Git-backed · source-traceable</span><Link href="/krail-live">System status</Link></footer>
    </main>
  );
}
