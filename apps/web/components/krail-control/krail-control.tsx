"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import type { Project, Resource } from "@/lib/krail/api";
import type { ExecutionCapabilities, ProjectMutation } from "@/lib/krail/control/types";
import styles from "./krail-control.module.css";

const apiRoot = () => (process.env.NEXT_PUBLIC_KRAIL_API_URL || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");
const slugify = (value: string) => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80) || "new-project";

async function mutate(path: string, body: Record<string, unknown>): Promise<Project> {
  const response = await fetch(`${apiRoot()}${path}`, { method: "POST", headers: { accept: "application/json", "content-type": "application/json" }, body: JSON.stringify(body) });
  const payload = await response.json().catch(() => ({})) as ProjectMutation;
  if (!response.ok) {
    const request = payload.error?.requestId ? ` Request ${payload.error.requestId}.` : "";
    throw new Error(`${payload.error?.message || `Request failed (${response.status}).`}${request}`);
  }
  return payload as unknown as Project;
}

export function KrailControl({ projects: initial, execution }: { projects: Resource<Project[]>; execution: Resource<ExecutionCapabilities> }) {
  const [projects, setProjects] = useState(initial.state === "ready" ? initial.data : []);
  const [mode, setMode] = useState<"managed" | "linked">("managed");
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);

  function remember(project: Project) { setProjects((items) => [...items.filter((item) => item.projectId !== project.projectId), project]); }

  async function submitManaged(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setNotice(undefined);
    const form = event.currentTarget; const data = new FormData(form); const displayName = String(data.get("displayName") || "").trim(); const slug = slugify(displayName);
    try {
      const project = await mutate("/projects/managed", { projectId: slug, displayName, name: displayName, slug, pack: data.get("pack"), mode: data.get("mode"), knowledgeMode: data.get("knowledgeMode") });
      remember(project); setNotice(`${project.displayName} is ready. You can start exploring or run a workflow.`); form.reset();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Project creation failed."); } finally { setBusy(false); }
  }

  async function submitLinked(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setNotice(undefined);
    const form = event.currentTarget; const data = new FormData(form); const displayName = String(data.get("displayName") || "").trim(); const customId = String(data.get("projectId") || "").trim();
    try {
      const project = await mutate("/projects", { projectId: customId || slugify(displayName), displayName, path: data.get("path"), workspaceMode: "linked_local" });
      remember(project); setNotice(`${project.displayName} is connected. Its existing files remain the source of truth.`); form.reset();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Project registration failed."); } finally { setBusy(false); }
  }

  return <main className={styles.page}>
    <header className={styles.header}><span className={styles.eyebrow}>Projects</span><h1>Set up your workspace.</h1><p>Create a new KRAIL project or connect one you already have. RAIL handles the setup and keeps the underlying files visible.</p></header>

    {notice && <div className={styles.notice} role="status">{notice}</div>}

    <section className={styles.section} aria-labelledby="projects-title">
      <div className={styles.sectionTitle}><div><span className={styles.eyebrow}>Your workspace</span><h2 id="projects-title">Projects</h2></div><strong>{projects.length}</strong></div>
      {initial.state === "error" ? <div className={styles.empty}><strong>RAIL cannot reach the local API.</strong><span>Run <code>make start</code> in the repository, then reload.</span></div> : projects.length === 0 ? <div className={styles.empty}><strong>No projects yet.</strong><span>Use the simple setup below to add your first one.</span></div> : <div className={styles.projectGrid}>{projects.map((project) => <article className={styles.project} key={project.projectId}>
        <div className={styles.projectTop}><div><span className={styles.mode}>{project.workspaceMode === "managed" ? "Managed by RAIL" : "Connected folder"}</span><h3>{project.displayName}</h3></div><span className={styles.access} data-write={project.access === "read_write"}>{project.access === "read_write" ? "Ready" : "Read only"}</span></div>
        <p>{project.access === "read_write" ? "This project can run approved workflows." : "You can explore this project safely; writes are disabled."}</p>
        <nav><Link className={styles.primary} href={`/krail-explore?project=${encodeURIComponent(project.projectId)}`}>Open knowledge</Link><Link href={`/krail-workflows?project=${encodeURIComponent(project.projectId)}`}>Workflows</Link><Link href={`/krail-analyze?project=${encodeURIComponent(project.projectId)}`}>Analyze</Link></nav>
        <details><summary>Technical details</summary><code>{project.canonicalPath}</code><dl><div><dt>Git</dt><dd>{project.git.branch || "detached"} · {project.git.isDirty ? "uncommitted changes" : "clean"}</dd></div><div><dt>Baseline</dt><dd>{project.git.baselineCommit?.slice(0, 10) || "not recorded"}</dd></div></dl></details>
      </article>)}</div>}
    </section>

    <section className={styles.add} id="add-project" aria-labelledby="add-title">
      <div className={styles.addIntro}><span className={styles.eyebrow}>Add a project</span><h2 id="add-title">How do you want to start?</h2><p>Most people should create a new project. Connect a folder when it already contains a KRAIL workspace.</p></div>
      <div className={styles.tabs} role="tablist" aria-label="Project setup type"><button type="button" role="tab" aria-selected={mode === "managed"} onClick={() => setMode("managed")}><strong>Create new</strong><span>Recommended</span></button><button type="button" role="tab" aria-selected={mode === "linked"} onClick={() => setMode("linked")}><strong>Connect folder</strong><span>Existing KRAIL project</span></button></div>
      {mode === "managed" ? <form onSubmit={submitManaged} className={styles.form}><div className={styles.formLead}><h3>Create a new project</h3><p>Give it a name. RAIL creates the folder, initializes KRAIL, and records the first Git version automatically.</p></div><label>Project name<input autoFocus required name="displayName" placeholder="Customer research" autoComplete="off" /></label><details className={styles.advanced}><summary>Advanced setup</summary><div className={styles.advancedFields}><label>Template<select name="pack" defaultValue="research-intelligence"><option value="research-intelligence">Research intelligence</option><option value="company-brain">Company knowledge</option><option value="software-architecture">Software architecture</option><option value="policy-compiler">Policy compiler</option></select></label><label>Structure<select name="mode" defaultValue="ontology_first"><option value="ontology_first">Ontology first</option><option value="markdown_graph">Markdown graph</option></select></label><label>Knowledge type<select name="knowledgeMode" defaultValue="research"><option value="research">Research</option><option value="company">Company</option><option value="personal">Personal</option><option value="project">Project</option><option value="software">Software</option></select></label></div></details><button className={styles.submit} disabled={busy}>{busy ? "Creating…" : "Create project"}</button></form> : <form onSubmit={submitLinked} className={styles.form}><div className={styles.formLead}><h3>Connect an existing folder</h3><p>The folder stays where it is. RAIL validates it and records operational metadata only.</p></div><label>Project name<input autoFocus required name="displayName" placeholder="Policy library" autoComplete="off" /></label><label>Folder path<input required name="path" placeholder="/Users/you/projects/policy-library" autoComplete="off" /><small>The folder must be inside a location allowed by the operator.</small></label><details className={styles.advanced}><summary>Advanced setup</summary><div className={styles.advancedFields}><label>Custom project ID <small>Optional</small><input name="projectId" pattern="[A-Za-z0-9][A-Za-z0-9._-]*" /></label></div></details><button className={styles.submit} disabled={busy}>{busy ? "Connecting…" : "Connect folder"}</button></form>}
    </section>

    <details className={styles.security}><summary><span><strong>Security and execution permissions</strong><small>Sandbox and profile status for this computer</small></span><span>View details</span></summary>{execution.state !== "ready" ? <div className={styles.empty}>Execution capability information is unavailable.</div> : <div className={styles.securityBody}><article className={styles.sandbox}><div><span className={styles.mode}>Local sandbox</span><h3>{execution.data.sandbox.provider}</h3><p>{execution.data.sandbox.reason || execution.data.sandbox.portabilityNote || "Local enforcement is ready."}</p></div><strong data-ok={execution.data.sandbox.available}>{execution.data.sandbox.available ? "Available" : "Unavailable"}</strong></article><div className={styles.profileGrid}>{execution.data.profiles.map((profile) => <article className={styles.profile} key={profile.name}><div><h3>{profile.name}</h3><span data-ok={profile.enabled}>{profile.enabled ? "Enabled" : "Disabled"}</span></div><p>{profile.dryRunOnly ? "Safe dry runs only" : "Full execution"} · {profile.filesystemMode.replaceAll("_", " ")} files · {profile.networkEnabled ? "network on" : "network off"}</p></article>)}</div></div>}</details>
  </main>;
}
