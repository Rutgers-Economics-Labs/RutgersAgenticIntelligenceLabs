"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import type { Project, Resource } from "@/lib/krail/api";
import type { ExecutionCapabilities, ProjectMutation } from "@/lib/krail/control/types";
import styles from "./krail-control.module.css";

const apiRoot = () => (process.env.NEXT_PUBLIC_KRAIL_API_URL || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

async function mutate(path: string, body: Record<string, unknown>): Promise<Project> {
  const response = await fetch(`${apiRoot()}${path}`, {
    method: "POST",
    headers: { accept: "application/json", "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({})) as ProjectMutation;
  if (!response.ok) {
    const request = payload.error?.requestId ? ` · request ${payload.error.requestId}` : "";
    throw new Error(`${payload.error?.message || `Request failed (${response.status})`}${request}`);
  }
  return payload as unknown as Project;
}

export function KrailControl({ projects: initial, execution }: { projects: Resource<Project[]>; execution: Resource<ExecutionCapabilities> }) {
  const [projects, setProjects] = useState(initial.state === "ready" ? initial.data : []);
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submitManaged(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setNotice(undefined);
    const data = new FormData(event.currentTarget);
    try {
      const project = await mutate("/projects/managed", Object.fromEntries(data.entries()));
      setProjects((items) => [...items.filter((item) => item.projectId !== project.projectId), project]);
      setNotice(`Created ${project.displayName} in the platform-managed workspace root.`);
      event.currentTarget.reset();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Project creation failed."); }
    finally { setBusy(false); }
  }

  async function submitLinked(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setNotice(undefined);
    const data = new FormData(event.currentTarget);
    try {
      const project = await mutate("/projects", { projectId: data.get("projectId") || undefined, displayName: data.get("displayName"), path: data.get("path"), workspaceMode: "linked_local" });
      setProjects((items) => [...items.filter((item) => item.projectId !== project.projectId), project]);
      setNotice(`Linked ${project.displayName}; KRAIL remains canonical at its existing path.`);
      event.currentTarget.reset();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Project registration failed."); }
    finally { setBusy(false); }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div><span className={styles.eyebrow}>Control Plane</span><h1>Operate the local KRAIL platform.</h1><p>Register canonical workspaces, inspect Git boundaries, and see exactly which execution permissions this node can enforce.</p></div>
        <Link href="/" className={styles.back}>← Platform home</Link>
      </header>

      {notice && <div className={styles.notice} role="status">{notice}</div>}

      <section className={styles.section} aria-labelledby="projects-title">
        <div className={styles.sectionTitle}><div><span className={styles.eyebrow}>Source of truth</span><h2 id="projects-title">Registered projects</h2></div><strong>{projects.length}</strong></div>
        {initial.state === "error" && <div className={styles.empty}>Platform API unavailable. Start the local API, then reload.</div>}
        {projects.length === 0 && initial.state !== "error" ? <div className={styles.empty}>No KRAIL projects are registered yet.</div> : (
          <div className={styles.projectGrid}>{projects.map((project) => <article className={styles.project} key={project.projectId}>
            <div><span className={styles.mode}>{project.workspaceMode.replaceAll("_", " ")}</span><h3>{project.displayName}</h3><code>{project.canonicalPath}</code></div>
            <dl><div><dt>Access</dt><dd>{project.access.replaceAll("_", " ")}</dd></div><div><dt>Git</dt><dd>{project.git.branch || "detached"} · {project.git.isDirty ? "dirty" : "clean"}</dd></div><div><dt>Baseline</dt><dd>{project.git.baselineCommit?.slice(0, 10) || "not recorded"}</dd></div></dl>
            <nav><Link href={`/krail-explore?project=${encodeURIComponent(project.projectId)}`}>Explore</Link><Link href={`/krail-analyze?project=${encodeURIComponent(project.projectId)}`}>Analyze</Link><Link href={`/krail-workflows?project=${encodeURIComponent(project.projectId)}`}>Workflows</Link></nav>
          </article>)}</div>
        )}
      </section>

      <section className={styles.forms} aria-label="Register KRAIL projects">
        <form onSubmit={submitManaged} className={styles.form}><span className={styles.eyebrow}>Platform managed</span><h2>Create a KRAIL workspace</h2><p>The server derives the destination below its configured managed root. The browser never chooses that path.</p>
          <label>Project ID<input required name="projectId" pattern="[A-Za-z0-9][A-Za-z0-9._-]*" /></label><label>Display name<input required name="displayName" /></label><label>KRAIL name<input required name="name" /></label><label>Slug<input required name="slug" pattern="[a-z0-9][a-z0-9-]*" /></label>
          <div className={styles.row}><label>Pack<select name="pack" defaultValue="research-intelligence"><option>research-intelligence</option><option>company-brain</option><option>software-architecture</option><option>policy-compiler</option></select></label><label>Mode<select name="mode" defaultValue="ontology_first"><option>ontology_first</option><option>markdown_graph</option></select></label></div>
          <label>Knowledge mode<select name="knowledgeMode" defaultValue="research"><option>research</option><option>company</option><option>personal</option><option>project</option><option>software</option></select></label><button disabled={busy}>Create managed project</button>
        </form>
        <form onSubmit={submitLinked} className={styles.form}><span className={styles.eyebrow}>Operator selected</span><h2>Link an existing directory</h2><p>The path must be inside an operator-configured linked root. Registration validates KRAIL and records Git metadata without copying its truth.</p>
          <label>Project ID <small>optional</small><input name="projectId" pattern="[A-Za-z0-9][A-Za-z0-9._-]*" /></label><label>Display name<input required name="displayName" /></label><label>Absolute local path<input required name="path" type="text" placeholder="/Users/you/knowledge-project" /></label><button disabled={busy}>Register linked project</button>
        </form>
      </section>

      <section className={styles.section} aria-labelledby="execution-title"><div className={styles.sectionTitle}><div><span className={styles.eyebrow}>Permission boundary</span><h2 id="execution-title">Execution capabilities</h2></div></div>
        {execution.state !== "ready" ? <div className={styles.empty}>Execution capability inventory is unavailable.</div> : <>
          <article className={styles.sandbox}><div><span className={styles.mode}>Sandbox</span><h3>{execution.data.sandbox.provider}</h3></div><strong data-ok={execution.data.sandbox.available}>{execution.data.sandbox.available ? "available" : "unavailable"}</strong><p>{execution.data.sandbox.reason || execution.data.sandbox.portabilityNote || "Local enforcement provider is ready."}</p></article>
          <div className={styles.profileGrid}>{execution.data.profiles.map((profile) => <article className={styles.profile} key={profile.name}><div><h3>{profile.name}</h3><span data-ok={profile.enabled}>{profile.enabled ? "enabled" : "disabled"}</span></div><ul><li>{profile.filesystemMode.replaceAll("_", " ")} filesystem</li><li>{profile.networkEnabled ? "network allowed" : "network denied"}</li><li>{profile.shellEnabled ? "shell allowed" : "shell denied"}</li><li>{profile.maxConcurrency} concurrent · {profile.timeoutSeconds}s</li></ul>{profile.dryRunOnly && <p>Dry-run only</p>}</article>)}</div>
        </>}
      </section>
    </main>
  );
}
