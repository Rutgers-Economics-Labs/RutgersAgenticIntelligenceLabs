"use client";
import { useState } from "react";
import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import Link from "next/link";
import { GitFork, Trash2 } from "lucide-react";
import { Id } from "@/convex/_generated/dataModel";

const APPROACH_LABEL = {
  "data-first": "Data → Ontology",
  "ontology-first": "Ontology → Data",
};

const STATUS_STYLES: Record<string, string> = {
  draft:    "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  ready:    "bg-blue-500/10 text-blue-400 border-blue-500/20",
  hydrated: "bg-green-500/10 text-green-400 border-green-500/20",
};

function NewProjectModal({ onClose }: { onClose: () => void }) {
  const createProject = useMutation(api.projects.create);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [approach, setApproach] = useState<"data-first" | "ontology-first">("data-first");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  async function handleCreate() {
    if (!name.trim()) return;
    setSaving(true);
    setError("");
    try {
      await createProject({ name: name.trim(), slug, description: description.trim() || undefined, approach });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/60 z-40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-[--card] border border-[--border] rounded-xl shadow-2xl p-6">
          <h2 className="text-base font-semibold mb-5">New Project</h2>

          <div className="space-y-4">
            <div>
              <label className="text-xs text-[--muted-foreground] block mb-1">Project Name</label>
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Research Project"
                className="w-full px-3 py-2 rounded border border-[--border] bg-[--muted] text-sm text-[--foreground] outline-none focus:border-[--primary]"
              />
              {name && (
                <p className="text-[10px] text-[--muted-foreground] mt-1 font-mono">slug: {slug}</p>
              )}
            </div>

            <div>
              <label className="text-xs text-[--muted-foreground] block mb-1">Description (optional)</label>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief description…"
                className="w-full px-3 py-2 rounded border border-[--border] bg-[--muted] text-sm text-[--foreground] outline-none focus:border-[--primary]"
              />
            </div>

            <div>
              <label className="text-xs text-[--muted-foreground] block mb-2">Approach</label>
              <div className="grid grid-cols-2 gap-3">
                {(["data-first", "ontology-first"] as const).map((a) => (
                  <button
                    key={a}
                    onClick={() => setApproach(a)}
                    className={`p-3 rounded-lg border text-left transition-colors ${
                      approach === a
                        ? "border-[--primary] bg-[--primary]/10"
                        : "border-[--border] bg-[--muted] hover:border-[--primary]/40"
                    }`}
                  >
                    <p className={`text-xs font-semibold mb-1 ${approach === a ? "text-[--primary]" : "text-[--foreground]"}`}>
                      {a === "data-first" ? "Data First" : "Ontology First"}
                    </p>
                    <p className="text-[10px] text-[--muted-foreground] leading-relaxed">
                      {a === "data-first"
                        ? "Pick data sources, then build an ontology to organize them."
                        : "Define your ontology schema, then find data sources to populate it."}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {error && <p className="mt-3 text-xs text-red-400">{error}</p>}

          <div className="flex justify-end gap-2 mt-6">
            <button
              onClick={onClose}
              className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={saving || !name.trim()}
              className="text-sm px-4 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saving ? "Creating…" : "Create Project"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function ForkProjectModal({
  projectId,
  initialName,
  onClose,
}: {
  projectId: Id<"projects">;
  initialName: string;
  onClose: () => void;
}) {
  const forkProject = useMutation(api.projects.forkProject);
  const [name, setName] = useState(`${initialName} (fork)`);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleFork() {
    if (!name.trim()) return;
    setSaving(true);
    setError("");
    try {
      await forkProject({ projectId, newName: name.trim() });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fork project");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/60 z-40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-[--card] border border-[--border] rounded-xl shadow-2xl p-6">
          <h2 className="text-base font-semibold mb-5">Fork Project</h2>
          <div>
            <label className="text-xs text-[--muted-foreground] block mb-1">New project name</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 rounded border border-[--border] bg-[--muted] text-sm text-[--foreground] outline-none focus:border-[--primary]"
            />
          </div>
          {error && <p className="mt-3 text-xs text-red-400">{error}</p>}
          <div className="flex justify-end gap-2 mt-6">
            <button
              onClick={onClose}
              className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
            >
              Cancel
            </button>
            <button
              onClick={handleFork}
              disabled={saving || !name.trim()}
              className="text-sm px-4 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saving ? "Forking…" : "Fork Project"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export default function ProjectsPage() {
  const projects = useQuery(api.projects.list, {});
  const removeProject = useMutation(api.projects.remove);
  const [showNew, setShowNew] = useState(false);
  const [forkingProject, setForkingProject] = useState<{ id: Id<"projects">; name: string } | null>(null);

  async function handleDelete(slug: string) {
    await removeProject({ slug });
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <button
          onClick={() => setShowNew(true)}
          className="text-sm px-3 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90"
        >
          + New Project
        </button>
      </div>

      {projects === undefined && (
        <p className="text-[--muted-foreground] text-sm">Loading…</p>
      )}

      {projects?.length === 0 && (
        <div className="flex flex-col items-center justify-center h-64 border border-dashed border-[--border] rounded-xl gap-4">
          <div className="text-center">
            <p className="text-[--foreground] font-medium mb-1">No projects yet</p>
            <p className="text-sm text-[--muted-foreground]">
              Create a project to start building ontologies and pipelines.
            </p>
          </div>
          <button
            onClick={() => setShowNew(true)}
            className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
          >
            + Create your first project
          </button>
        </div>
      )}

      {projects && projects.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {projects.map((p) => (
            <div
              key={p._id}
              className="p-5 rounded-xl border border-[--border] bg-[--card] hover:border-[--primary]/60 hover:bg-[--muted] transition-colors group"
            >
              <div className="flex items-start justify-between gap-3 mb-3">
                <Link href={`/projects/${p.slug}`} className="min-w-0 flex-1">
                  <h3 className="font-semibold text-sm group-hover:text-[--primary] transition-colors truncate">{p.name}</h3>
                </Link>
                <span className={`text-[10px] px-2 py-0.5 rounded border font-medium shrink-0 ${STATUS_STYLES[p.status]}`}>
                  {p.status}
                </span>
              </div>
              <Link href={`/projects/${p.slug}`} className="block">
                {p.description && (
                  <p className="text-xs text-[--muted-foreground] mb-3 line-clamp-2">{p.description}</p>
                )}
                <div className="flex items-center gap-3 text-[10px] text-[--muted-foreground]">
                  <span className="px-1.5 py-0.5 rounded bg-[--muted] font-mono">
                    {APPROACH_LABEL[p.approach]}
                  </span>
                  {p.ontologyConfigSlug && (
                    <span>ontology: {p.ontologyConfigSlug}</span>
                  )}
                  {p.apiConfigSlugs.length > 0 && (
                    <span>{p.apiConfigSlugs.length} data source{p.apiConfigSlugs.length > 1 ? "s" : ""}</span>
                  )}
                </div>
                <p className="text-[10px] text-[--muted-foreground] mt-3">
                  Updated {new Date(p.updatedAt).toLocaleDateString()}
                </p>
              </Link>
              <div className="mt-4 flex items-center gap-2">
                <button
                  onClick={() => setForkingProject({ id: p._id, name: p.name })}
                  className="inline-flex items-center gap-1.5 rounded-md border border-[--border] px-2.5 py-1.5 text-xs text-[--muted-foreground] hover:border-[--primary]/50 hover:text-[--primary]"
                >
                  <GitFork size={12} />
                  Fork
                </button>
                <button
                  onClick={() => void handleDelete(p.slug)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-[--border] px-2.5 py-1.5 text-xs text-[--muted-foreground] hover:border-red-600/50 hover:text-red-400"
                >
                  <Trash2 size={12} />
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showNew && <NewProjectModal onClose={() => setShowNew(false)} />}
      {forkingProject && (
        <ForkProjectModal
          projectId={forkingProject.id}
          initialName={forkingProject.name}
          onClose={() => setForkingProject(null)}
        />
      )}
    </div>
  );
}
