"use client";
import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import Link from "next/link";
import { jobs } from "@/lib/api";

// ── Step types ────────────────────────────────────────────────────────────────

type Step = "setup" | "ontology" | "data" | "pipeline" | "run";

const DATA_FIRST_STEPS: Step[]     = ["setup", "data", "ontology", "pipeline", "run"];
const ONTOLOGY_FIRST_STEPS: Step[] = ["setup", "ontology", "data", "pipeline", "run"];

const STEP_LABELS: Record<Step, string> = {
  setup:    "Setup",
  ontology: "Ontology",
  data:     "Data Sources",
  pipeline: "Pipeline",
  run:      "Run",
};

// ── Stepper ───────────────────────────────────────────────────────────────────

function Stepper({ steps, current, onGo }: { steps: Step[]; current: Step; onGo: (s: Step) => void }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {steps.map((s, i) => {
        const idx = steps.indexOf(current);
        const done = i < idx;
        const active = s === current;
        return (
          <div key={s} className="flex items-center">
            <button
              onClick={() => onGo(s)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                active
                  ? "bg-[--primary] text-[#0d1117]"
                  : done
                  ? "text-[--primary] hover:bg-[--primary]/10"
                  : "text-[--muted-foreground] hover:text-[--foreground]"
              }`}
            >
              <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold border ${
                active ? "bg-[--background] border-[--background] text-[--primary]" :
                done   ? "border-[--primary] text-[--primary]" :
                         "border-[--border] text-[--muted-foreground]"
              }`}>
                {done ? "✓" : i + 1}
              </span>
              {STEP_LABELS[s]}
            </button>
            {i < steps.length - 1 && (
              <div className={`w-8 h-px mx-1 ${done ? "bg-[--primary]/40" : "bg-[--border]"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}


// ── Setup Step ────────────────────────────────────────────────────────────────

function SetupStep({ project, onNext }: { project: ProjectDoc; onNext: () => void }) {
  return (
    <div className="max-w-lg">
      <h2 className="text-lg font-semibold mb-1">{project.name}</h2>
      {project.description && <p className="text-sm text-[--muted-foreground] mb-4">{project.description}</p>}
      <div className="rounded-lg border border-[--border] p-4 mb-6">
        <p className="text-xs text-[--muted-foreground] mb-1 uppercase tracking-wide">Approach</p>
        <p className="text-sm font-medium">
          {project.approach === "data-first" ? "Data First → Build ontology from data sources" : "Ontology First → Find data sources for ontology"}
        </p>
      </div>
      <button
        onClick={onNext}
        className="text-sm px-4 py-2 rounded bg-[--primary] text-[#0d1117] font-semibold hover:opacity-90"
      >
        Continue →
      </button>
    </div>
  );
}

// ── Ontology Step ─────────────────────────────────────────────────────────────

function OntologyStep({ project, onNext }: {
  project: ProjectDoc;
  onNext: () => void;
}) {
  const ontologies = useQuery(api.configs.listOntologies, {});
  const updateProject = useMutation(api.projects.update);
  const [selected, setSelected] = useState(project.ontologyConfigSlug ?? "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await updateProject({ slug: project.slug, ontologyConfigSlug: selected || undefined });
      onNext();
    } finally { setSaving(false); }
  }

  return (
    <div className="max-w-2xl">
      <h2 className="text-base font-semibold mb-1">Choose an Ontology</h2>
      <p className="text-sm text-[--muted-foreground] mb-4">
        Select an existing ontology config or go to{" "}
        <Link href="/configs" className="text-[--primary] hover:underline">Configs</Link>{" "}
        to create one.
      </p>

      {ontologies === undefined && <p className="text-sm text-[--muted-foreground]">Loading…</p>}

      {ontologies?.length === 0 && (
        <div className="p-4 rounded border border-dashed border-[--border] text-sm text-[--muted-foreground] mb-4">
          No ontology configs yet.{" "}
          <Link href="/configs" className="text-[--primary] hover:underline">Create one in Configs →</Link>
        </div>
      )}

      {ontologies && ontologies.length > 0 && (
        <div className="grid gap-3 mb-5">
          {/* None option */}
          <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
            selected === "" ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/40"
          }`}>
            <input type="radio" name="ontology" value="" checked={selected === ""} onChange={() => setSelected("")} className="mt-0.5 accent-[--primary]" />
            <div>
              <p className="text-sm font-medium text-[--muted-foreground]">None / skip for now</p>
            </div>
          </label>
          {ontologies.map((o) => (
            <label key={o._id} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
              selected === o.slug ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/40"
            }`}>
              <input type="radio" name="ontology" value={o.slug} checked={selected === o.slug} onChange={() => setSelected(o.slug)} className="mt-0.5 accent-[--primary]" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{o.name}</p>
                <p className="text-[10px] text-[--muted-foreground] font-mono">{o.slug}</p>
                <pre className="text-[10px] text-[--muted-foreground] mt-1 opacity-60 truncate">
                  {o.content.split("\n").slice(0, 2).join("\n")}
                </pre>
              </div>
            </label>
          ))}
        </div>
      )}

      <button
        onClick={save}
        disabled={saving}
        className="text-sm px-4 py-2 rounded bg-[--primary] text-[#0d1117] font-semibold hover:opacity-90 disabled:opacity-40"
      >
        {saving ? "Saving…" : "Continue →"}
      </button>
    </div>
  );
}

// ── Data Sources Step ─────────────────────────────────────────────────────────

function DataStep({ project, onNext }: {
  project: ProjectDoc;
  onNext: () => void;
}) {
  const apiConfigs = useQuery(api.configs.listApis, {});
  const updateProject = useMutation(api.projects.update);
  const [selected, setSelected] = useState<string[]>(project.apiConfigSlugs ?? []);
  const [saving, setSaving] = useState(false);

  function toggle(slug: string) {
    setSelected((prev) => prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]);
  }

  async function save() {
    setSaving(true);
    try {
      await updateProject({ slug: project.slug, apiConfigSlugs: selected });
      onNext();
    } finally { setSaving(false); }
  }

  return (
    <div className="max-w-2xl">
      <h2 className="text-base font-semibold mb-1">Select Data Sources</h2>
      <p className="text-sm text-[--muted-foreground] mb-4">
        Choose the API configs that will feed data into this project.{" "}
        <Link href="/configs" className="text-[--primary] hover:underline">Add more in Configs →</Link>
      </p>

      {apiConfigs === undefined && <p className="text-sm text-[--muted-foreground]">Loading…</p>}

      {apiConfigs?.length === 0 && (
        <div className="p-4 rounded border border-dashed border-[--border] text-sm text-[--muted-foreground] mb-4">
          No API configs yet.{" "}
          <Link href="/configs" className="text-[--primary] hover:underline">Create one in Configs →</Link>
        </div>
      )}

      {apiConfigs && apiConfigs.length > 0 && (
        <div className="grid gap-3 mb-5">
          {apiConfigs.map((a) => (
            <label key={a._id} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
              selected.includes(a.slug) ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/40"
            }`}>
              <input
                type="checkbox"
                checked={selected.includes(a.slug)}
                onChange={() => toggle(a.slug)}
                className="mt-0.5 accent-[--primary]"
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{a.name}</p>
                <p className="text-[10px] text-[--muted-foreground] font-mono">{a.slug}</p>
                {a.tags && a.tags.length > 0 && (
                  <div className="flex gap-1 flex-wrap mt-1">
                    {a.tags.map((tag) => (
                      <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded bg-[--muted] text-[--muted-foreground]">{tag}</span>
                    ))}
                  </div>
                )}
              </div>
            </label>
          ))}
        </div>
      )}

      {selected.length > 0 && (
        <p className="text-xs text-[--muted-foreground] mb-4">{selected.length} source{selected.length > 1 ? "s" : ""} selected</p>
      )}

      <button
        onClick={save}
        disabled={saving}
        className="text-sm px-4 py-2 rounded bg-[--primary] text-[#0d1117] font-semibold hover:opacity-90 disabled:opacity-40"
      >
        {saving ? "Saving…" : "Continue →"}
      </button>
    </div>
  );
}

// ── Pipeline Step ─────────────────────────────────────────────────────────────

function PipelineStep({ project, onNext }: {
  project: ProjectDoc;
  onNext: () => void;
}) {
  const pipelines = useQuery(api.configs.listPipelines, {});
  const updateProject = useMutation(api.projects.update);
  const [selected, setSelected] = useState(project.pipelineConfigSlug ?? "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await updateProject({
        slug: project.slug,
        pipelineConfigSlug: selected || undefined,
        status: selected ? "ready" : "draft",
      });
      onNext();
    } finally { setSaving(false); }
  }

  // Generate a YAML template based on selected data sources & ontology
  function generateTemplate() {
    const apiSlugs = project.apiConfigSlugs;
    const onto = project.ontologyConfigSlug;
    const lines = [
      `name: ${project.slug}-pipeline`,
      `ontology: ${onto ?? "# set ontology slug here"}`,
      `steps:`,
      ...(apiSlugs.length > 0
        ? apiSlugs.map((s) => `  - api: ${s}\n    transform: default`)
        : ["  - api: # add api slug here\n    transform: default"]),
    ];
    return lines.join("\n");
  }

  return (
    <div className="max-w-2xl">
      <h2 className="text-base font-semibold mb-1">Choose a Pipeline</h2>
      <p className="text-sm text-[--muted-foreground] mb-4">
        Select a pipeline config that combines your ontology and data sources.{" "}
        <Link href="/configs" className="text-[--primary] hover:underline">Manage in Configs →</Link>
      </p>

      {/* Template hint */}
      <div className="mb-5 p-3 rounded-lg border border-[--border] bg-[--muted]">
        <p className="text-xs text-[--muted-foreground] mb-2 font-medium">Generated template (copy to Configs → Pipelines)</p>
        <pre className="text-[10px] text-[--foreground] font-mono whitespace-pre-wrap">{generateTemplate()}</pre>
      </div>

      {pipelines === undefined && <p className="text-sm text-[--muted-foreground]">Loading…</p>}

      {pipelines?.length === 0 && (
        <div className="p-4 rounded border border-dashed border-[--border] text-sm text-[--muted-foreground] mb-4">
          No pipeline configs yet.{" "}
          <Link href="/configs" className="text-[--primary] hover:underline">Create one in Configs →</Link>
        </div>
      )}

      {pipelines && pipelines.length > 0 && (
        <div className="grid gap-3 mb-5">
          <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
            selected === "" ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/40"
          }`}>
            <input type="radio" name="pipeline" value="" checked={selected === ""} onChange={() => setSelected("")} className="mt-0.5 accent-[--primary]" />
            <p className="text-sm font-medium text-[--muted-foreground]">None / skip for now</p>
          </label>
          {pipelines.map((p) => (
            <label key={p._id} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
              selected === p.slug ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/40"
            }`}>
              <input type="radio" name="pipeline" value={p.slug} checked={selected === p.slug} onChange={() => setSelected(p.slug)} className="mt-0.5 accent-[--primary]" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{p.name}</p>
                <p className="text-[10px] text-[--muted-foreground] font-mono">{p.slug}</p>
                {p.referencedApiSlugs.length > 0 && (
                  <div className="flex gap-1 flex-wrap mt-1">
                    {p.referencedApiSlugs.map((s) => (
                      <span key={s} className="text-[9px] px-1.5 py-0.5 rounded bg-[--muted] text-[--muted-foreground] font-mono">{s}</span>
                    ))}
                  </div>
                )}
              </div>
            </label>
          ))}
        </div>
      )}

      <button
        onClick={save}
        disabled={saving}
        className="text-sm px-4 py-2 rounded bg-[--primary] text-[#0d1117] font-semibold hover:opacity-90 disabled:opacity-40"
      >
        {saving ? "Saving…" : "Continue →"}
      </button>
    </div>
  );
}

// ── Run Step ──────────────────────────────────────────────────────────────────

function RunStep({ project }: {
  project: ProjectDoc;
}) {
  const updateProject = useMutation(api.projects.update);
  const [triggering, setTriggering] = useState(false);
  const [jobResult, setJobResult] = useState<{ jobId: string; status: string } | null>(null);
  const [error, setError] = useState("");

  const ready = !!project.pipelineConfigSlug;

  async function handleRun() {
    if (!project.pipelineConfigSlug) return;
    setTriggering(true);
    setError("");
    try {
      const result = await jobs.trigger(project.pipelineConfigSlug);
      setJobResult(result);
      await updateProject({ slug: project.slug, status: "hydrated", lastJobId: result.jobId });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to trigger job");
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div className="max-w-lg">
      <h2 className="text-base font-semibold mb-4">Run Hydration</h2>

      {/* Summary */}
      <div className="rounded-lg border border-[--border] divide-y divide-[--border] mb-6">
        <Row label="Ontology" value={project.ontologyConfigSlug ?? "—"} />
        <Row label="Data Sources" value={project.apiConfigSlugs.length > 0 ? project.apiConfigSlugs.join(", ") : "—"} />
        <Row label="Pipeline" value={project.pipelineConfigSlug ?? "—"} />
        <Row label="Status" value={project.status} />
      </div>

      {!ready && (
        <p className="text-sm text-yellow-400 mb-4">No pipeline selected. Go back to the Pipeline step to choose one.</p>
      )}

      {jobResult && (
        <div className="mb-4 p-3 rounded-lg border border-green-700/50 bg-green-900/20">
          <p className="text-sm text-green-300 font-medium">Job queued successfully</p>
          <p className="text-xs text-green-400 font-mono mt-1">ID: {jobResult.jobId}</p>
          <Link href="/jobs" className="text-xs text-[--primary] hover:underline mt-1 inline-block">
            View in Jobs →
          </Link>
        </div>
      )}

      {error && <p className="text-sm text-red-400 mb-4">{error}</p>}

      <button
        onClick={handleRun}
        disabled={triggering || !ready}
        className="text-sm px-5 py-2 rounded bg-[--primary] text-[#0d1117] font-semibold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {triggering ? "Triggering…" : "▶ Run Hydration"}
      </button>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center px-4 py-3">
      <span className="text-xs text-[--muted-foreground] w-32 shrink-0">{label}</span>
      <span className="text-sm font-mono">{value}</span>
    </div>
  );
}

// ── Project Workspace (rendered after data loads) ─────────────────────────────

type ProjectDoc = NonNullable<ReturnType<typeof useQuery<typeof api.projects.get>>>;

function ProjectWorkspace({ project }: { project: ProjectDoc }) {
  const removeProject = useMutation(api.projects.remove);
  const router = useRouter();
  const steps = project.approach === "data-first" ? DATA_FIRST_STEPS : ONTOLOGY_FIRST_STEPS;
  const [currentStep, setCurrentStep] = useState<Step>(steps[0]);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const currentIdx = steps.indexOf(currentStep);
  function goNext() {
    if (currentIdx < steps.length - 1) setCurrentStep(steps[currentIdx + 1]);
  }

  async function handleDelete() {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    await removeProject({ slug: project.slug });
    router.push("/projects");
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <Link href="/projects" className="text-sm text-[--primary] hover:underline">← Projects</Link>
        <button
          onClick={handleDelete}
          className={`text-xs px-3 py-1.5 rounded border transition-colors ${
            confirmDelete
              ? "border-red-600 bg-red-600/20 text-red-300 hover:bg-red-600/30"
              : "border-[--border] text-[--muted-foreground] hover:text-red-400 hover:border-red-600/50"
          }`}
        >
          {confirmDelete ? "Confirm delete" : "Delete project"}
        </button>
      </div>

      <Stepper steps={steps} current={currentStep} onGo={setCurrentStep} />

      {currentStep === "setup"    && <SetupStep    project={project} onNext={goNext} />}
      {currentStep === "ontology" && <OntologyStep project={project} onNext={goNext} />}
      {currentStep === "data"     && <DataStep     project={project} onNext={goNext} />}
      {currentStep === "pipeline" && <PipelineStep project={project} onNext={goNext} />}
      {currentStep === "run"      && <RunStep      project={project} />}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ProjectPage() {
  const { slug } = useParams<{ slug: string }>();
  const project = useQuery(api.projects.get, { slug });

  if (project === undefined) {
    return <div className="text-sm text-[--muted-foreground]">Loading…</div>;
  }
  if (project === null) {
    return (
      <div>
        <Link href="/projects" className="text-sm text-[--primary] hover:underline mb-4 inline-block">← Back to Projects</Link>
        <p className="text-sm text-red-400">Project not found.</p>
      </div>
    );
  }

  return <ProjectWorkspace project={project} />;
}
