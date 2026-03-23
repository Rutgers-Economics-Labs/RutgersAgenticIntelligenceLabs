"use client";
import dynamic from "next/dynamic";
import { useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";
import Link from "next/link";
import {
  CheckCircle2, Circle, XCircle,
  ChevronDown, ChevronRight, ExternalLink,
  Database, Network, Code2, BrainCircuit,
  Plus, Link2, Trash2, Play, RefreshCw,
  Bot, Send, Loader2, X, Sparkles,
} from "lucide-react";
import { jobs as jobsApi, configs, projectAgent } from "@/lib/api";
import { useTheme } from "@/components/ThemeProvider";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

// Monaco — dynamically imported to avoid SSR issues
const MonacoEditor = dynamic(
  () => import("@monaco-editor/react").then((m) => m.default),
  {
    ssr: false,
    loading: () => (
      <div className="rounded-lg border border-[--border] bg-[--muted] animate-pulse" style={{ minHeight: 240 }} />
    ),
  }
);

// ── Types ──────────────────────────────────────────────────────────────────────

type Tab = "overview" | "ontology" | "data" | "pipeline" | "jobs" | "explore";
type ConfigType = "ontologies" | "apis" | "pipelines";
type ProjectDoc = NonNullable<ReturnType<typeof useQuery<typeof api.projects.get>>>;

type JobDoc = {
  _id: Id<"hydrationJobs">;
  status: "queued" | "running" | "success" | "failed" | "cancelled";
  pipelineSlug: string;
  projectId?: Id<"projects">;
  createdAt: number;
  startedAt?: number;
  finishedAt?: number;
  errorMessage?: string;
  stepResults: { stepName: string; status: string; rowCount?: number }[];
};

// ── YAML Editor ───────────────────────────────────────────────────────────────

function YamlEditor({
  value,
  onChange,
  readOnly = false,
  height = "240px",
}: {
  value: string;
  onChange?: (val: string) => void;
  readOnly?: boolean;
  height?: string;
}) {
  const { theme } = useTheme();
  return (
    <div className="rounded-lg overflow-hidden border border-[--border]">
      <MonacoEditor
        height={height}
        language="yaml"
        theme={theme === "light" ? "vs" : "vs-dark"}
        value={value}
        onChange={(val) => onChange?.(val ?? "")}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 12,
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          wordWrap: "on",
          padding: { top: 12, bottom: 12 },
          overviewRulerLanes: 0,
          renderLineHighlight: readOnly ? "none" : "line",
          scrollbar: { vertical: "auto", horizontal: "auto" },
        }}
      />
    </div>
  );
}

// ── Config Slide-Over ─────────────────────────────────────────────────────────

function ConfigSlideOver({
  type,
  initialContent = "",
  onClose,
  onSaved,
}: {
  type: ConfigType;
  initialContent?: string;
  onClose: () => void;
  onSaved: (slug: string) => Promise<void>;
}) {
  const typeLabel = type === "ontologies" ? "ontology" : type === "apis" ? "api" : "pipeline";
  const [name, setName] = useState("");
  const [content, setContent] = useState(initialContent);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  async function handleSave() {
    if (!name.trim() || !content.trim()) return;
    setSaving(true);
    setErrors([]);
    try {
      const result = await configs.validate(typeLabel, content);
      if (!result.valid) { setErrors(result.errors); setSaving(false); return; }
      await configs.create(type, { name: name.trim(), slug, content, isPublic: false, tags: [] });
      await onSaved(slug);
    } catch (e) {
      setErrors([e instanceof Error ? e.message : "Save failed"]);
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/60 z-40" onClick={onClose} />
      <div className="fixed right-0 top-0 h-full w-full max-w-2xl bg-[--card] border-l border-[--border] z-50 flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[--border]">
          <h2 className="font-semibold text-sm">New {typeLabel} config</h2>
          <button onClick={onClose} className="text-[--muted-foreground] hover:text-[--foreground] text-xl px-1 leading-none">×</button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <div>
            <label className="text-xs text-[--muted-foreground] block mb-1">Name</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={`My ${typeLabel} config`}
              className="w-full px-3 py-2 rounded border border-[--border] bg-[--muted] text-sm text-[--foreground] outline-none focus:border-[--primary]"
            />
            {name && <p className="text-[10px] text-[--muted-foreground] mt-1 font-mono">slug: {slug}</p>}
          </div>

          <div>
            <label className="text-xs text-[--muted-foreground] block mb-2">YAML</label>
            <YamlEditor value={content} onChange={setContent} height="440px" />
          </div>

          {errors.length > 0 && (
            <div className="rounded border border-red-800/60 bg-red-900/20 p-3 space-y-1">
              {errors.map((e, i) => <p key={i} className="text-xs text-red-400">{e}</p>)}
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-[--border] flex justify-end gap-2">
          <button
            onClick={onClose}
            className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name.trim() || !content.trim()}
            className="text-sm px-4 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? "Saving…" : "Create & Link"}
          </button>
        </div>
      </div>
    </>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(ms: number) {
  const d = Date.now() - ms;
  if (d < 60_000) return "just now";
  if (d < 3_600_000) return `${Math.floor(d / 60_000)}m ago`;
  if (d < 86_400_000) return `${Math.floor(d / 3_600_000)}h ago`;
  return new Date(ms).toLocaleDateString();
}

const STATUS_COLOR: Record<string, string> = {
  success:   "text-green-400 bg-green-900/20 border-green-800/50",
  failed:    "text-red-400 bg-red-900/20 border-red-800/50",
  running:   "text-blue-400 bg-blue-900/20 border-blue-800/50",
  queued:    "text-yellow-400 bg-yellow-900/20 border-yellow-800/50",
  cancelled: "text-[--muted-foreground] bg-[--muted] border-[--border]",
};

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab({ project, onTabSwitch }: { project: ProjectDoc; onTabSwitch: (t: Tab) => void }) {
  const recentJobs = useQuery(api.jobs.listByProject, { projectId: project._id, limit: 1 });
  const lastJob = recentJobs?.[0] as JobDoc | undefined;

  const checklist = [
    { label: "Project created",        done: true,                              tab: null          as Tab | null },
    { label: "Ontology configured",    done: !!project.ontologyConfigSlug,      tab: "ontology"    as Tab },
    { label: "Data sources attached",  done: project.apiConfigSlugs.length > 0, tab: "data"        as Tab },
    { label: "Pipeline configured",    done: !!project.pipelineConfigSlug,      tab: "pipeline"    as Tab },
    { label: "Hydration run",          done: project.status === "hydrated",     tab: "pipeline"    as Tab },
  ];
  const allDone = checklist.every((s) => s.done);

  return (
    <div className="space-y-6">
      {/* Status grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          {
            label: "Ontology",
            value: project.ontologyConfigSlug ?? "Not set",
            ok: !!project.ontologyConfigSlug,
            tab: "ontology" as Tab,
          },
          {
            label: "Data Sources",
            value: project.apiConfigSlugs.length > 0
              ? `${project.apiConfigSlugs.length} attached`
              : "None attached",
            ok: project.apiConfigSlugs.length > 0,
            tab: "data" as Tab,
          },
          {
            label: "Pipeline",
            value: project.pipelineConfigSlug ?? "Not set",
            ok: !!project.pipelineConfigSlug,
            tab: "pipeline" as Tab,
          },
          {
            label: "Last Job",
            value: lastJob ? lastJob.status : "Never run",
            ok: lastJob?.status === "success",
            tab: "jobs" as Tab,
          },
        ].map(({ label, value, ok, tab }) => (
          <button
            key={label}
            onClick={() => onTabSwitch(tab)}
            className={`text-left p-4 rounded-xl border transition-opacity hover:opacity-80 ${
              ok
                ? "border-green-700/50 bg-green-900/10"
                : "border-[--border] bg-[--muted]"
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              {ok
                ? <CheckCircle2 size={13} className="text-green-400 shrink-0" />
                : <Circle size={13} className="text-[--muted-foreground] shrink-0" />
              }
              <span className="text-[10px] text-[--muted-foreground] uppercase tracking-wide font-medium">{label}</span>
            </div>
            <p className="text-sm font-semibold truncate">{value}</p>
          </button>
        ))}
      </div>

      {/* Setup checklist */}
      {!allDone && (
        <div className="rounded-xl border border-[--border] p-5">
          <h3 className="text-sm font-semibold mb-4">Getting Started</h3>
          <div className="space-y-3">
            {checklist.map((step) => (
              <div
                key={step.label}
                onClick={() => step.tab && !step.done && onTabSwitch(step.tab)}
                className={`flex items-center gap-3 ${step.tab && !step.done ? "cursor-pointer group" : ""}`}
              >
                {step.done
                  ? <CheckCircle2 size={15} className="text-green-400 shrink-0" />
                  : <Circle size={15} className="text-[--border] shrink-0" />
                }
                <span className={`text-sm flex-1 ${
                  step.done
                    ? "text-[--muted-foreground] line-through"
                    : "text-[--foreground] group-hover:text-[--primary]"
                }`}>
                  {step.label}
                </span>
                {step.tab && !step.done && (
                  <span className="text-[10px] text-[--primary] opacity-0 group-hover:opacity-100 transition-opacity">
                    Go →
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Last job summary */}
      {lastJob && (
        <div className="rounded-xl border border-[--border] p-5">
          <h3 className="text-sm font-semibold mb-3">Last Hydration</h3>
          <div className="flex items-center gap-4">
            <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${STATUS_COLOR[lastJob.status]}`}>
              {lastJob.status}
            </span>
            <span className="text-xs text-[--muted-foreground]">{timeAgo(lastJob.createdAt)}</span>
            {lastJob.stepResults.length > 0 && (
              <span className="text-xs text-[--muted-foreground]">
                {lastJob.stepResults.filter((s) => s.status === "done").length}/{lastJob.stepResults.length} steps
              </span>
            )}
            <button
              onClick={() => onTabSwitch("jobs")}
              className="ml-auto text-xs text-[--primary] hover:underline"
            >
              View all jobs →
            </button>
          </div>
        </div>
      )}

      {/* Explore shortcuts (only when hydrated) */}
      {project.status === "hydrated" && (
        <div className="rounded-xl border border-[--border] p-5">
          <h3 className="text-sm font-semibold mb-4">Explore Your Data</h3>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { icon: <Database size={15} />, label: "Entity Explorer", href: "/explorer" },
              { icon: <Network size={15} />, label: "Knowledge Graph",  href: "/graph" },
              { icon: <Code2 size={15} />,   label: "SQL Editor",       href: "/sql" },
              { icon: <BrainCircuit size={15} />, label: "AI Workspace", href: "/workspace" },
            ].map(({ icon, label, href }) => (
              <Link
                key={href}
                href={href}
                className="flex items-center gap-2.5 p-3 rounded-lg border border-[--border] hover:border-[--primary]/60 hover:bg-[--muted] transition-colors group text-sm"
              >
                <span className="text-[--muted-foreground] group-hover:text-[--primary] transition-colors shrink-0">{icon}</span>
                <span className="font-medium group-hover:text-[--primary] transition-colors truncate">{label}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Ontology Tab ──────────────────────────────────────────────────────────────

function OntologyTab({ project }: { project: ProjectDoc }) {
  const updateProject = useMutation(api.projects.update);
  const allOntologies = useQuery(api.configs.listOntologies, {});
  const linkedConfig = useQuery(
    api.configs.getOntology,
    project.ontologyConfigSlug ? { slug: project.ontologyConfigSlug } : "skip"
  );

  const [mode, setMode] = useState<"view" | "link" | "create">("view");
  const [linkSelected, setLinkSelected] = useState(project.ontologyConfigSlug ?? "");

  const TEMPLATE = `uri: http://example.org/${project.slug}#
classes:
  - name: Entity
    description: Top-level entity class
data_properties:
  - name: hasName
    range: str
  - name: hasValue
    range: float
  - name: hasDate
    range: str
object_properties:
  - name: isPartOf
    domain: Entity
    range: Entity
`;

  async function handleLink(slug: string) {
    await updateProject({ slug: project.slug, ontologyConfigSlug: slug || undefined });
    setMode("view");
  }

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">Ontology Schema</h2>
          <p className="text-xs text-[--muted-foreground] mt-0.5">
            Defines the OWL classes and properties for this project's knowledge graph.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {project.ontologyConfigSlug && (
            <button
              onClick={() => setMode(mode === "link" ? "view" : "link")}
              className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground] flex items-center gap-1.5"
            >
              <Link2 size={11} /> Link Different
            </button>
          )}
          <button
            onClick={() => setMode("create")}
            className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--primary] hover:bg-[--primary]/10 flex items-center gap-1.5"
          >
            <Plus size={11} /> Create New
          </button>
        </div>
      </div>

      {/* Link picker */}
      {mode === "link" && (
        <div className="rounded-xl border border-[--border] p-4">
          <p className="text-xs font-medium mb-3">Select existing ontology</p>
          <div className="space-y-2 max-h-56 overflow-y-auto mb-4">
            <label className={`flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors ${linkSelected === "" ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/30"}`}>
              <input type="radio" name="onto-link" checked={linkSelected === ""} onChange={() => setLinkSelected("")} className="accent-[--primary]" />
              <span className="text-sm text-[--muted-foreground]">None</span>
            </label>
            {allOntologies?.map((o) => (
              <label key={o._id} className={`flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors ${linkSelected === o.slug ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/30"}`}>
                <input type="radio" name="onto-link" checked={linkSelected === o.slug} onChange={() => setLinkSelected(o.slug)} className="accent-[--primary]" />
                <div>
                  <p className="text-sm font-medium">{o.name}</p>
                  <p className="text-[10px] text-[--muted-foreground] font-mono">{o.slug}</p>
                </div>
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={() => handleLink(linkSelected)} className="text-sm px-3 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90">Save</button>
            <button onClick={() => setMode("view")} className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]">Cancel</button>
          </div>
        </div>
      )}

      {/* Linked config display */}
      {project.ontologyConfigSlug ? (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle2 size={13} className="text-green-400" />
            <span className="text-sm font-medium">{linkedConfig?.name ?? project.ontologyConfigSlug}</span>
            <span className="text-[10px] font-mono text-[--muted-foreground] px-1.5 py-0.5 rounded bg-[--muted]">{project.ontologyConfigSlug}</span>
          </div>
          {linkedConfig
            ? <YamlEditor value={linkedConfig.content} readOnly height="340px" />
            : <div className="h-40 rounded-xl border border-[--border] bg-[--muted] flex items-center justify-center"><span className="text-xs text-[--muted-foreground]">Loading…</span></div>
          }
          <Link href="/configs" className="mt-3 inline-flex items-center gap-1 text-xs text-[--primary] hover:underline">
            Edit in Configs <ExternalLink size={10} />
          </Link>
        </div>
      ) : (
        mode !== "link" && (
          <div className="rounded-xl border border-dashed border-[--border] p-10 text-center">
            <p className="text-sm text-[--muted-foreground] mb-5">No ontology linked to this project yet.</p>
            <div className="flex justify-center gap-3">
              {allOntologies && allOntologies.length > 0 && (
                <button onClick={() => setMode("link")} className="text-sm px-4 py-2 rounded border border-[--border] text-[--foreground] hover:border-[--primary]/60">
                  Link Existing
                </button>
              )}
              <button onClick={() => setMode("create")} className="text-sm px-4 py-2 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90">
                Create New Ontology
              </button>
            </div>
          </div>
        )
      )}

      {/* Create slide-over */}
      {mode === "create" && (
        <ConfigSlideOver
          type="ontologies"
          initialContent={TEMPLATE}
          onClose={() => setMode("view")}
          onSaved={async (slug) => {
            await updateProject({ slug: project.slug, ontologyConfigSlug: slug });
            setMode("view");
          }}
        />
      )}
    </div>
  );
}

// ── Data Sources Tab ──────────────────────────────────────────────────────────

const SOURCE_BADGE: Record<string, string> = {
  api:    "bg-blue-900/30 text-blue-400",
  csv:    "bg-purple-900/30 text-purple-400",
  excel:  "bg-green-900/30 text-green-400",
  scrape: "bg-orange-900/30 text-orange-400",
};

function DataSourcesTab({ project }: { project: ProjectDoc }) {
  const updateProject = useMutation(api.projects.update);
  const allApis = useQuery(api.configs.listApis, {});

  const [showPicker, setShowPicker] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [pickerSelected, setPickerSelected] = useState<string[]>(project.apiConfigSlugs);

  const attached = allApis?.filter((a) => project.apiConfigSlugs.includes(a.slug)) ?? [];
  const unattached = allApis?.filter((a) => !project.apiConfigSlugs.includes(a.slug)) ?? [];

  const API_TEMPLATE = `name: my-data-source
type: api
url: https://api.example.com/data
response_format: json
fields:
  - source: id
    alias: entityId
  - source: name
    alias: entityName
  - source: value
    alias: dataValue
    cast: float
`;

  function togglePicker(slug: string) {
    setPickerSelected((prev) => prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]);
  }

  async function saveAttachments() {
    await updateProject({ slug: project.slug, apiConfigSlugs: pickerSelected });
    setShowPicker(false);
  }

  async function removeSource(slug: string) {
    await updateProject({ slug: project.slug, apiConfigSlugs: project.apiConfigSlugs.filter((s) => s !== slug) });
  }

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">Data Sources</h2>
          <p className="text-xs text-[--muted-foreground] mt-0.5">
            APIs, CSVs, and other feeds that hydrate this project's ontology.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {unattached.length > 0 && (
            <button
              onClick={() => { setPickerSelected(project.apiConfigSlugs); setShowPicker(!showPicker); setShowCreate(false); }}
              className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground] flex items-center gap-1.5"
            >
              <Link2 size={11} /> Add Existing
            </button>
          )}
          <button
            onClick={() => { setShowCreate(!showCreate); setShowPicker(false); }}
            className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--primary] hover:bg-[--primary]/10 flex items-center gap-1.5"
          >
            <Plus size={11} /> Create New
          </button>
        </div>
      </div>

      {/* Picker */}
      {showPicker && (
        <div className="rounded-xl border border-[--border] p-4">
          <p className="text-xs font-medium mb-3">Select sources to attach</p>
          <div className="space-y-2 max-h-56 overflow-y-auto mb-4">
            {unattached.map((a) => (
              <label key={a._id} className={`flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors ${pickerSelected.includes(a.slug) ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/30"}`}>
                <input type="checkbox" checked={pickerSelected.includes(a.slug)} onChange={() => togglePicker(a.slug)} className="accent-[--primary]" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{a.name}</p>
                  <p className="text-[10px] font-mono text-[--muted-foreground]">{a.slug}</p>
                </div>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono shrink-0 ${SOURCE_BADGE[a.sourceType] ?? "bg-[--muted] text-[--muted-foreground]"}`}>{a.sourceType}</span>
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={saveAttachments} className="text-sm px-3 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90">Save</button>
            <button onClick={() => setShowPicker(false)} className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]">Cancel</button>
          </div>
        </div>
      )}

      {/* Attached grid */}
      {attached.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {attached.map((a) => (
            <div key={a._id} className="p-4 rounded-xl border border-[--border] bg-[--muted] flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold truncate">{a.name}</p>
                  <p className="text-[10px] font-mono text-[--muted-foreground] mt-0.5">{a.slug}</p>
                </div>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono shrink-0 ${SOURCE_BADGE[a.sourceType] ?? "bg-[--background] text-[--muted-foreground]"}`}>{a.sourceType}</span>
              </div>
              {a.tags && a.tags.length > 0 && (
                <div className="flex gap-1 flex-wrap">
                  {a.tags.map((t) => <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-[--background] text-[--muted-foreground]">{t}</span>)}
                </div>
              )}
              <button
                onClick={() => removeSource(a.slug)}
                className="self-end mt-1 text-[10px] text-[--muted-foreground] hover:text-red-400 flex items-center gap-1 transition-colors"
              >
                <Trash2 size={10} /> Remove
              </button>
            </div>
          ))}
        </div>
      ) : (
        !showPicker && !showCreate && (
          <div className="rounded-xl border border-dashed border-[--border] p-10 text-center">
            <p className="text-sm text-[--muted-foreground] mb-5">No data sources attached yet.</p>
            <div className="flex justify-center gap-3">
              {allApis && allApis.length > 0 && (
                <button onClick={() => { setPickerSelected([]); setShowPicker(true); }} className="text-sm px-4 py-2 rounded border border-[--border] text-[--foreground] hover:border-[--primary]/60">
                  Add Existing
                </button>
              )}
              <button onClick={() => setShowCreate(true)} className="text-sm px-4 py-2 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90">
                Create New Source
              </button>
            </div>
          </div>
        )
      )}

      {/* Create slide-over */}
      {showCreate && (
        <ConfigSlideOver
          type="apis"
          initialContent={API_TEMPLATE}
          onClose={() => setShowCreate(false)}
          onSaved={async (slug) => {
            await updateProject({ slug: project.slug, apiConfigSlugs: [...project.apiConfigSlugs, slug] });
            setShowCreate(false);
          }}
        />
      )}
    </div>
  );
}

// ── Pipeline Tab ──────────────────────────────────────────────────────────────

function PipelineTab({ project, onRunSuccess }: { project: ProjectDoc; onRunSuccess: () => void }) {
  const updateProject = useMutation(api.projects.update);
  const allPipelines = useQuery(api.configs.listPipelines, {});
  const linkedPipeline = useQuery(
    api.configs.getPipeline,
    project.pipelineConfigSlug ? { slug: project.pipelineConfigSlug } : "skip"
  );

  const [mode, setMode] = useState<"view" | "link" | "create">("view");
  const [linkSelected, setLinkSelected] = useState(project.pipelineConfigSlug ?? "");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");

  function generateTemplate() {
    const steps = project.apiConfigSlugs.length > 0
      ? project.apiConfigSlugs.flatMap((s) => [
          `  - name: Load ${s}`,
          `    api: ${s}`,
          `    class: Entity`,
          `    uri: "http://example.org/${project.slug}#Entity_{id}"`,
        ]).join("\n")
      : [
          `  - name: Load source`,
          `    api: # set api slug`,
          `    class: Entity`,
          `    uri: "http://example.org/${project.slug}#Entity_{id}"`,
        ].join("\n");

    return [
      `name: ${project.slug}-pipeline`,
      `ontology: ${project.ontologyConfigSlug ?? "# set ontology slug"}`,
      `steps:`,
      steps,
    ].join("\n");
  }

  async function handleLink(slug: string) {
    await updateProject({ slug: project.slug, pipelineConfigSlug: slug || undefined, status: slug ? "ready" : "draft" });
    setMode("view");
  }

  async function handleRun() {
    if (!project.pipelineConfigSlug) return;
    setRunning(true);
    setRunError("");
    try {
      const result = await jobsApi.trigger(project.pipelineConfigSlug, project._id);
      await updateProject({ slug: project.slug, status: "hydrated", lastJobId: result.jobId });
      onRunSuccess();
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Failed to start job");
      setRunning(false);
    }
  }

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">Hydration Pipeline</h2>
          <p className="text-xs text-[--muted-foreground] mt-0.5">
            Wires data sources to the ontology and runs the hydration job.
          </p>
        </div>
        <div className="flex gap-2 shrink-0 flex-wrap justify-end">
          {project.pipelineConfigSlug && (
            <button
              onClick={() => setMode(mode === "link" ? "view" : "link")}
              className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground] flex items-center gap-1.5"
            >
              <Link2 size={11} /> Link Different
            </button>
          )}
          <button
            onClick={() => setMode("create")}
            className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--primary] hover:bg-[--primary]/10 flex items-center gap-1.5"
          >
            <Plus size={11} /> Create New
          </button>
          {project.pipelineConfigSlug && (
            <button
              onClick={handleRun}
              disabled={running}
              className="text-xs px-3 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90 disabled:opacity-40 flex items-center gap-1.5"
            >
              <Play size={11} /> {running ? "Starting…" : "Run Hydration"}
            </button>
          )}
        </div>
      </div>

      {runError && (
        <div className="rounded-lg border border-red-800/60 bg-red-900/20 p-3">
          <p className="text-xs text-red-400">{runError}</p>
        </div>
      )}

      {/* Link picker */}
      {mode === "link" && (
        <div className="rounded-xl border border-[--border] p-4">
          <p className="text-xs font-medium mb-3">Select existing pipeline</p>
          <div className="space-y-2 max-h-56 overflow-y-auto mb-4">
            <label className={`flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors ${linkSelected === "" ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/30"}`}>
              <input type="radio" name="pipe-link" checked={linkSelected === ""} onChange={() => setLinkSelected("")} className="accent-[--primary]" />
              <span className="text-sm text-[--muted-foreground]">None</span>
            </label>
            {allPipelines?.map((p) => (
              <label key={p._id} className={`flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors ${linkSelected === p.slug ? "border-[--primary] bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/30"}`}>
                <input type="radio" name="pipe-link" checked={linkSelected === p.slug} onChange={() => setLinkSelected(p.slug)} className="accent-[--primary]" />
                <div>
                  <p className="text-sm font-medium">{p.name}</p>
                  <p className="text-[10px] font-mono text-[--muted-foreground]">{p.slug}</p>
                </div>
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={() => handleLink(linkSelected)} className="text-sm px-3 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90">Save</button>
            <button onClick={() => setMode("view")} className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]">Cancel</button>
          </div>
        </div>
      )}

      {/* Generated template (when nothing linked) */}
      {!project.pipelineConfigSlug && mode !== "link" && (
        <div className="rounded-xl border border-[--border] p-4">
          <p className="text-[10px] text-[--muted-foreground] uppercase tracking-wide font-medium mb-2">
            Generated template — copy to Configs to save
          </p>
          <YamlEditor value={generateTemplate()} readOnly height="200px" />
        </div>
      )}

      {/* Linked pipeline display */}
      {project.pipelineConfigSlug && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle2 size={13} className="text-green-400" />
            <span className="text-sm font-medium">{linkedPipeline?.name ?? project.pipelineConfigSlug}</span>
            <span className="text-[10px] font-mono text-[--muted-foreground] px-1.5 py-0.5 rounded bg-[--muted]">{project.pipelineConfigSlug}</span>
          </div>
          {linkedPipeline
            ? <YamlEditor value={linkedPipeline.content} readOnly height="340px" />
            : <div className="h-40 rounded-xl border border-[--border] bg-[--muted] flex items-center justify-center"><span className="text-xs text-[--muted-foreground]">Loading…</span></div>
          }
          <Link href="/configs" className="mt-3 inline-flex items-center gap-1 text-xs text-[--primary] hover:underline">
            Edit in Configs <ExternalLink size={10} />
          </Link>
        </div>
      )}

      {!project.pipelineConfigSlug && mode === "view" && (
        <div className="rounded-xl border border-dashed border-[--border] p-10 text-center">
          <p className="text-sm text-[--muted-foreground] mb-5">No pipeline linked yet.</p>
          <div className="flex justify-center gap-3">
            {allPipelines && allPipelines.length > 0 && (
              <button onClick={() => setMode("link")} className="text-sm px-4 py-2 rounded border border-[--border] text-[--foreground] hover:border-[--primary]/60">
                Link Existing
              </button>
            )}
            <button onClick={() => setMode("create")} className="text-sm px-4 py-2 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90">
              Create New Pipeline
            </button>
          </div>
        </div>
      )}

      {/* Create slide-over */}
      {mode === "create" && (
        <ConfigSlideOver
          type="pipelines"
          initialContent={generateTemplate()}
          onClose={() => setMode("view")}
          onSaved={async (slug) => {
            await updateProject({ slug: project.slug, pipelineConfigSlug: slug, status: "ready" });
            setMode("view");
          }}
        />
      )}
    </div>
  );
}

// ── Jobs Tab ──────────────────────────────────────────────────────────────────

function JobRow({ job }: { job: JobDoc }) {
  const [expanded, setExpanded] = useState(false);
  const logs = useQuery(api.jobs.getLogs, expanded ? { jobId: job._id, limit: 400 } : "skip");

  const stepsDone = job.stepResults.filter((s) => s.status === "done").length;
  const stepsTotal = job.stepResults.length;

  function duration() {
    if (!job.startedAt || !job.finishedAt) return "—";
    const ms = job.finishedAt - job.startedAt;
    return ms < 60_000 ? `${Math.round(ms / 1000)}s` : `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
  }

  return (
    <div className="border-b border-[--border] last:border-0">
      <div
        className="flex items-center gap-4 px-4 py-3 hover:bg-[--muted]/50 cursor-pointer select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className={`text-[10px] px-2 py-0.5 rounded border font-medium w-[72px] text-center shrink-0 ${STATUS_COLOR[job.status]}`}>
          {job.status}
        </span>
        <span className="text-xs text-[--muted-foreground] w-20 shrink-0">{timeAgo(job.createdAt)}</span>
        <span className="text-xs text-[--muted-foreground] w-14 shrink-0">{duration()}</span>
        <span className="text-xs text-[--muted-foreground] flex-1">
          {stepsTotal > 0 ? `${stepsDone}/${stepsTotal} steps` : "—"}
        </span>
        <span className="text-[--muted-foreground] shrink-0">
          {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </span>
      </div>

      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* Step list */}
          {stepsTotal > 0 && (
            <div className="space-y-1.5">
              {job.stepResults.map((s) => (
                <div key={s.stepName} className="flex items-center gap-2 text-xs">
                  {s.status === "done"    && <CheckCircle2 size={12} className="text-green-400 shrink-0" />}
                  {s.status === "failed"  && <XCircle      size={12} className="text-red-400 shrink-0" />}
                  {s.status === "running" && <RefreshCw    size={12} className="text-blue-400 shrink-0 animate-spin" />}
                  {s.status === "pending" && <Circle       size={12} className="text-[--border] shrink-0" />}
                  <span className="text-[--foreground]">{s.stepName}</span>
                  {s.rowCount != null && <span className="text-[--muted-foreground]">· {s.rowCount.toLocaleString()} rows</span>}
                </div>
              ))}
            </div>
          )}

          {/* Log output */}
          <div className="rounded-lg bg-[--muted] border border-[--border] p-3 max-h-52 overflow-y-auto font-mono text-[10px] leading-relaxed space-y-0.5">
            {logs === undefined && <span className="text-[--muted-foreground]">Loading logs…</span>}
            {logs?.length === 0  && <span className="text-[--muted-foreground]">No log output.</span>}
            {logs?.map((l) => (
              <div
                key={l.seq}
                className={
                  l.level === "error" ? "text-red-400" :
                  l.level === "warn"  ? "text-yellow-400" :
                  "text-[--muted-foreground]"
                }
              >
                {l.message}
              </div>
            ))}
          </div>

          {job.errorMessage && (
            <p className="text-xs text-red-400">{job.errorMessage}</p>
          )}
        </div>
      )}
    </div>
  );
}

function JobsTab({ project }: { project: ProjectDoc }) {
  const projectJobs = useQuery(api.jobs.listByProject, { projectId: project._id, limit: 25 }) as JobDoc[] | undefined;

  return (
    <div className="space-y-5 max-w-3xl">
      <div>
        <h2 className="text-sm font-semibold">Hydration Jobs</h2>
        <p className="text-xs text-[--muted-foreground] mt-0.5">All pipeline runs for this project, most recent first.</p>
      </div>

      {projectJobs === undefined && (
        <p className="text-sm text-[--muted-foreground]">Loading…</p>
      )}

      {projectJobs?.length === 0 && (
        <div className="rounded-xl border border-dashed border-[--border] p-10 text-center">
          <p className="text-sm text-[--muted-foreground]">No jobs yet for this project.</p>
          <p className="text-xs text-[--muted-foreground] mt-1">Run hydration from the Pipeline tab to get started.</p>
        </div>
      )}

      {projectJobs && projectJobs.length > 0 && (
        <div className="rounded-xl border border-[--border] overflow-hidden">
          <div className="flex items-center gap-4 px-4 py-2 bg-[--muted] border-b border-[--border]">
            <span className="text-[10px] text-[--muted-foreground] uppercase tracking-wide w-[72px] shrink-0">Status</span>
            <span className="text-[10px] text-[--muted-foreground] uppercase tracking-wide w-20 shrink-0">Started</span>
            <span className="text-[10px] text-[--muted-foreground] uppercase tracking-wide w-14 shrink-0">Duration</span>
            <span className="text-[10px] text-[--muted-foreground] uppercase tracking-wide flex-1">Steps</span>
          </div>
          {projectJobs.map((job) => <JobRow key={job._id} job={job} />)}
        </div>
      )}
    </div>
  );
}

// ── Explore Tab ───────────────────────────────────────────────────────────────

function ExploreTab({ project }: { project: ProjectDoc }) {
  const hydrated = project.status === "hydrated";

  const tools = [
    {
      icon: <Database size={22} />,
      label: "Entity Explorer",
      desc: "Browse all entities and their properties in the knowledge graph.",
      href: "/explorer",
      available: hydrated,
    },
    {
      icon: <Network size={22} />,
      label: "Knowledge Graph",
      desc: "Visualize entity relationships as an interactive force-directed graph.",
      href: "/graph",
      available: hydrated,
    },
    {
      icon: <Code2 size={22} />,
      label: "SQL Editor",
      desc: "Query the DuckDB ontology mirror with SQL or plain-English questions.",
      href: "/sql",
      available: hydrated,
    },
    {
      icon: <BrainCircuit size={22} />,
      label: "AI Workspace",
      desc: "Chat with the AI agent to discover, query, and analyze your data.",
      href: "/workspace",
      available: true,
    },
  ];

  return (
    <div className="space-y-5 max-w-3xl">
      <div>
        <h2 className="text-sm font-semibold">Explore & Analyze</h2>
        <p className="text-xs text-[--muted-foreground] mt-0.5">
          {hydrated
            ? "Your ontology is populated — start exploring."
            : "Run a hydration job first to populate the ontology."}
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {tools.map(({ icon, label, desc, href, available }) =>
          available ? (
            <Link
              key={href}
              href={href}
              className="p-5 rounded-xl border border-[--border] hover:border-[--primary]/60 hover:bg-[--muted] transition-colors group"
            >
              <div className="text-[--primary] mb-3">{icon}</div>
              <p className="text-sm font-semibold group-hover:text-[--primary] transition-colors">{label}</p>
              <p className="text-xs text-[--muted-foreground] mt-1 leading-relaxed">{desc}</p>
            </Link>
          ) : (
            <div
              key={href}
              className="p-5 rounded-xl border border-[--border] opacity-40 cursor-not-allowed"
            >
              <div className="text-[--muted-foreground] mb-3">{icon}</div>
              <p className="text-sm font-semibold">{label}</p>
              <p className="text-xs text-[--muted-foreground] mt-1 leading-relaxed">{desc}</p>
              <p className="text-[10px] text-yellow-500 mt-2">Requires hydrated data</p>
            </div>
          )
        )}
      </div>
    </div>
  );
}

// ── Project AI Panel ──────────────────────────────────────────────────────────

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        code({ className, children, ...props }) {
          const isBlock = className?.startsWith("language-");
          return isBlock ? (
            <pre className="overflow-x-auto rounded bg-black/30 p-2 text-[10px] my-1.5">
              <code className={className} {...props}>{children}</code>
            </pre>
          ) : (
            <code className="bg-black/20 rounded px-1 py-0.5 text-[10px] font-mono" {...props}>{children}</code>
          );
        },
        ul({ children }) { return <ul className="list-disc list-inside space-y-0.5 my-1 text-xs">{children}</ul>; },
        ol({ children }) { return <ol className="list-decimal list-inside space-y-0.5 my-1 text-xs">{children}</ol>; },
        h1({ children }) { return <h1 className="text-sm font-semibold mt-2 mb-1">{children}</h1>; },
        h2({ children }) { return <h2 className="text-xs font-semibold mt-2 mb-0.5">{children}</h2>; },
        h3({ children }) { return <h3 className="text-xs font-medium mt-1.5 mb-0.5">{children}</h3>; },
        p({ children }) { return <p className="text-xs leading-relaxed mb-1">{children}</p>; },
        a({ href, children }) { return <a href={href} target="_blank" rel="noopener noreferrer" className="text-[--primary] underline underline-offset-2">{children}</a>; },
        blockquote({ children }) { return <blockquote className="border-l-2 border-[--primary] pl-2 italic text-[--muted-foreground] text-xs">{children}</blockquote>; },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

const TOOL_LABELS: Record<string, string> = {
  get_project_info:       "Reading project info",
  list_available_configs: "Listing configs",
  link_ontology:          "Linking ontology",
  link_pipeline:          "Linking pipeline",
  add_data_source:        "Adding data source",
  remove_data_source:     "Removing data source",
  run_hydration:          "Running hydration",
  get_recent_jobs:        "Checking recent jobs",
  get_job_logs:           "Fetching job logs",
  create_config:          "Creating config",
  search_data_registry:   "Searching registry",
};

type ToolCallBlock = { id: string; name: string; args: Record<string, unknown>; result?: unknown };

type AIChatMsg =
  | { role: "user";      content: string }
  | { role: "assistant"; content: string; toolCalls?: ToolCallBlock[]; streaming?: boolean };

function AIToolCard({ tc }: { tc: ToolCallBlock }) {
  const [open, setOpen] = useState(false);
  const label = TOOL_LABELS[tc.name] ?? tc.name;
  const done = tc.result !== undefined;
  const isError = done && typeof tc.result === "object" && tc.result !== null && "error" in (tc.result as object);

  return (
    <div className="my-1 rounded-lg border border-[--border] bg-[--background]/60 text-[10px]">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[--muted-foreground] hover:text-[--foreground] transition-colors"
      >
        {open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        <Code2 size={10} className={isError ? "text-red-400" : "text-[--primary]"} />
        <span className={`font-medium ${isError ? "text-red-400" : "text-[--primary]"}`}>{label}</span>
        {!done && <Loader2 size={9} className="ml-auto animate-spin text-[--muted-foreground]" />}
        {done && !isError && <span className="ml-auto text-green-400/70">✓</span>}
        {isError && <span className="ml-auto text-red-400/70">✗</span>}
      </button>
      {open && (
        <div className="border-t border-[--border] px-2.5 py-2 space-y-1.5">
          <pre className="overflow-x-auto rounded bg-black/20 p-1.5 text-[10px] text-[--foreground] max-h-32">
            {JSON.stringify(tc.result ?? tc.args, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

const SUGGESTIONS = [
  "What's the current state of this project?",
  "Debug my pipeline — check the last job logs",
  "Link a pipeline to this project",
  "Run hydration for this project",
];

type ChatId = Id<"projectChats">;

function ProjectAIPanel({ project, onClose }: { project: ProjectDoc; onClose: () => void }) {
  const recentJobs = useQuery(api.jobs.listByProject, { projectId: project._id, limit: 1 }) as JobDoc[] | undefined;
  const lastJob = recentJobs?.[0];

  const savedChats = useQuery(api.projectChats.listByProject, { projectId: project._id, limit: 30 });
  const createChat   = useMutation(api.projectChats.create);
  const appendMsgs   = useMutation(api.projectChats.appendMessages);
  const updateTitle  = useMutation(api.projectChats.updateTitle);
  const deleteChat   = useMutation(api.projectChats.remove);

  const [activeChatId, setActiveChatId]   = useState<ChatId | null>(null);
  const [messages, setMessages]           = useState<AIChatMsg[]>([]);
  const [input, setInput]                 = useState("");
  const [loading, setLoading]             = useState(false);
  const [showHistory, setShowHistory]     = useState(false);
  const historyRef  = useRef<{ role: string; content: string }[]>([]);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollBottom = () => setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);

  function newChat() {
    setActiveChatId(null);
    setMessages([]);
    historyRef.current = [];
    setShowHistory(false);
    textareaRef.current?.focus();
  }

  function loadChat(chat: { _id: ChatId; messages: { role: "user" | "assistant"; content: string }[] }) {
    setActiveChatId(chat._id);
    setMessages(chat.messages.map(m => ({ role: m.role, content: m.content })));
    historyRef.current = chat.messages.map(m => ({ role: m.role, content: m.content }));
    setShowHistory(false);
    setTimeout(() => bottomRef.current?.scrollIntoView(), 50);
  }

  const send = useCallback(async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || loading) return;
    setInput("");
    setLoading(true);
    setShowHistory(false);

    setMessages(prev => [...prev, { role: "user", content: text }]);
    setMessages(prev => [...prev, { role: "assistant", content: "", toolCalls: [], streaming: true }]);

    const pendingToolCalls: Record<string, ToolCallBlock> = {};
    let finalAssistantText = "";

    try {
      for await (const event of projectAgent.chat(project._id, text, historyRef.current)) {
        if (event.type === "text_delta") {
          finalAssistantText += event.content;
          setMessages(prev => prev.map((m, i) =>
            i === prev.length - 1 && m.role === "assistant" ? { ...m, content: m.content + event.content } : m
          ));
          scrollBottom();
        } else if (event.type === "tool_call") {
          const tc: ToolCallBlock = { id: event.id, name: event.name, args: event.args };
          pendingToolCalls[event.id] = tc;
          setMessages(prev => prev.map((m, i) =>
            i === prev.length - 1 && m.role === "assistant" ? { ...m, toolCalls: [...(m.toolCalls ?? []), tc] } : m
          ));
        } else if (event.type === "tool_result") {
          if (pendingToolCalls[event.id]) pendingToolCalls[event.id].result = event.result;
          setMessages(prev => prev.map((m, i) => {
            if (i !== prev.length - 1 || m.role !== "assistant") return m;
            return { ...m, toolCalls: (m.toolCalls ?? []).map(tc => tc.id === event.id ? { ...tc, result: event.result } : tc) };
          }));
          scrollBottom();
        } else if (event.type === "done") {
          historyRef.current = [...historyRef.current, ...event.new_messages];

          // Persist to Convex
          const newPair = [
            { role: "user" as const, content: text },
            { role: "assistant" as const, content: finalAssistantText },
          ].filter(m => m.content);

          if (activeChatId) {
            await appendMsgs({ chatId: activeChatId, messages: newPair });
          } else {
            const { chatId } = await createChat({
              projectId: project._id,
              title: text.slice(0, 60),
              messages: newPair,
            });
            setActiveChatId(chatId as ChatId);
            // Use first assistant response as a better title
            if (finalAssistantText) {
              await updateTitle({ chatId: chatId as ChatId, title: text.slice(0, 60) });
            }
          }
        } else if (event.type === "error") {
          setMessages(prev => prev.map((m, i) =>
            i === prev.length - 1 && m.role === "assistant"
              ? { ...m, content: `**Error:** ${event.message}`, streaming: false } : m
          ));
        }
      }
    } catch (err) {
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1 && m.role === "assistant"
          ? { ...m, content: `**Error:** ${err instanceof Error ? err.message : String(err)}`, streaming: false } : m
      ));
    } finally {
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1 && m.role === "assistant" ? { ...m, streaming: false } : m
      ));
      setLoading(false);
      scrollBottom();
      textareaRef.current?.focus();
    }
  }, [input, loading, project._id, activeChatId, appendMsgs, createChat, updateTitle]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
  };

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="fixed right-0 top-0 h-full w-full max-w-md bg-[--card] border-l border-[--border] z-50 flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[--border] shrink-0">
          <div className="flex items-center gap-2">
            <Sparkles size={14} className="text-[--primary]" />
            <span className="text-sm font-semibold">Project Assistant</span>
            {activeChatId && (
              <span className="text-[10px] text-[--muted-foreground] font-mono truncate max-w-[120px]">
                · saved
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowHistory(v => !v)}
              title="Chat history"
              className={`p-1.5 rounded text-xs font-medium transition-colors ${showHistory ? "bg-[--primary]/10 text-[--primary]" : "text-[--muted-foreground] hover:text-[--foreground]"}`}
            >
              History
            </button>
            <button
              onClick={newChat}
              title="New chat"
              className="p-1.5 rounded text-[--muted-foreground] hover:text-[--foreground] transition-colors text-xs"
            >
              + New
            </button>
            <button onClick={onClose} className="p-1.5 rounded text-[--muted-foreground] hover:text-[--foreground]">
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Context pills */}
        <div className="px-4 py-2 border-b border-[--border] shrink-0 flex flex-wrap gap-1.5">
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[--muted] text-[--muted-foreground] font-mono">{project.name}</span>
          {project.ontologyConfigSlug && <span className="text-[10px] px-2 py-0.5 rounded-full bg-[--muted] text-[--muted-foreground] font-mono">onto: {project.ontologyConfigSlug}</span>}
          {project.pipelineConfigSlug && <span className="text-[10px] px-2 py-0.5 rounded-full bg-[--muted] text-[--muted-foreground] font-mono">pipe: {project.pipelineConfigSlug}</span>}
          {lastJob && (
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${lastJob.status === "success" ? "bg-green-900/30 text-green-400" : lastJob.status === "failed" ? "bg-red-900/30 text-red-400" : "bg-yellow-900/30 text-yellow-400"}`}>
              last job: {lastJob.status}
            </span>
          )}
        </div>

        {/* History overlay */}
        {showHistory && (
          <div className="absolute inset-x-0 top-[89px] bottom-0 z-10 bg-[--card] border-t border-[--border] flex flex-col">
            <div className="px-4 py-3 border-b border-[--border] flex items-center justify-between shrink-0">
              <span className="text-xs font-semibold">Saved Chats</span>
              <button onClick={newChat} className="text-xs px-2.5 py-1 rounded bg-[--primary] text-[--primary-foreground] font-medium hover:opacity-90">
                + New Chat
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
              {savedChats === undefined && <p className="text-xs text-[--muted-foreground] p-2">Loading…</p>}
              {savedChats?.length === 0 && <p className="text-xs text-[--muted-foreground] p-2">No saved chats yet.</p>}
              {savedChats?.map(chat => (
                <div
                  key={chat._id}
                  className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 transition-colors ${activeChatId === chat._id ? "border-[--primary]/50 bg-[--primary]/5" : "border-[--border] hover:border-[--primary]/30 hover:bg-[--muted]"}`}
                >
                  <button className="flex-1 text-left min-w-0" onClick={() => loadChat(chat)}>
                    <p className="text-xs font-medium truncate text-[--foreground]">{chat.title}</p>
                    <p className="text-[10px] text-[--muted-foreground] mt-0.5">
                      {chat.messages.length} messages · {timeAgo(chat.updatedAt)}
                    </p>
                  </button>
                  <button
                    onClick={() => { void deleteChat({ chatId: chat._id }); if (activeChatId === chat._id) newChat(); }}
                    className="shrink-0 p-1 rounded text-[--muted-foreground] hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="space-y-3">
              <p className="text-xs text-[--muted-foreground]">I can read your project config, run hydration, link configs, check job logs, and help you debug anything.</p>
              <div className="space-y-1.5">
                {SUGGESTIONS.map(s => (
                  <button key={s} onClick={() => void send(s)}
                    className="w-full text-left text-xs px-3 py-2 rounded-lg border border-[--border] bg-[--muted]/40 text-[--muted-foreground] hover:text-[--foreground] hover:border-[--primary]/40 transition-colors">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-2 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              {msg.role === "assistant" && (
                <div className="shrink-0 w-6 h-6 rounded-full bg-[--primary]/20 flex items-center justify-center mt-0.5">
                  <Bot size={11} className="text-[--primary]" />
                </div>
              )}
              <div className={`min-w-0 max-w-[85%]`}>
                {msg.role === "assistant" && msg.toolCalls && msg.toolCalls.length > 0 && (
                  <div className="space-y-0.5 mb-1">
                    {msg.toolCalls.map(tc => <AIToolCard key={tc.id} tc={tc} />)}
                  </div>
                )}
                {(msg.content || (msg.role === "assistant" && msg.streaming)) && (
                  <div className={`rounded-xl px-3 py-2 text-xs leading-relaxed ${msg.role === "user" ? "bg-[--primary] text-[--primary-foreground] rounded-tr-sm whitespace-pre-wrap" : "bg-[--muted] text-[--foreground] rounded-tl-sm"}`}>
                    {msg.role === "user" ? msg.content : (
                      <>
                        <MarkdownContent content={msg.content} />
                        {msg.streaming && !msg.content && <span className="inline-block w-1 h-3 bg-current rounded-sm animate-pulse" />}
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="shrink-0 px-4 pb-4 pt-2 border-t border-[--border]">
          <div className="flex items-end gap-2 rounded-xl border border-[--border] bg-[--muted] px-3 py-2 focus-within:border-[--primary]/50 transition-colors">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Ask about pipelines, errors, configs… (Enter to send)"
              rows={1}
              disabled={loading}
              className="flex-1 resize-none bg-transparent text-xs text-[--foreground] placeholder:text-[--muted-foreground] focus:outline-none max-h-24 overflow-y-auto"
              style={{ fieldSizing: "content" } as React.CSSProperties}
            />
            <button
              onClick={() => void send()}
              disabled={loading || !input.trim()}
              className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center bg-[--primary] text-[--primary-foreground] hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed transition-opacity"
            >
              {loading ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ── Project Dashboard ─────────────────────────────────────────────────────────

const TAB_LABELS: Record<Tab, string> = {
  overview:  "Overview",
  ontology:  "Ontology",
  data:      "Data Sources",
  pipeline:  "Pipeline",
  jobs:      "Jobs",
  explore:   "Explore",
};

const ALL_TABS: Tab[] = ["overview", "ontology", "data", "pipeline", "jobs", "explore"];

const STATUS_BADGE: Record<string, string> = {
  draft:    "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  ready:    "bg-blue-500/10 text-blue-400 border-blue-500/20",
  hydrated: "bg-green-500/10 text-green-400 border-green-500/20",
};

function ProjectDashboard({ project }: { project: ProjectDoc }) {
  const removeProject = useMutation(api.projects.remove);
  const updateProject = useMutation(api.projects.update);
  const router = useRouter();

  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [aiOpen, setAiOpen] = useState(false);

  async function handleQuickRun() {
    if (!project.pipelineConfigSlug) return;
    setRunning(true);
    setRunError("");
    try {
      const result = await jobsApi.trigger(project.pipelineConfigSlug, project._id);
      await updateProject({ slug: project.slug, status: "hydrated", lastJobId: result.jobId });
      setActiveTab("jobs");
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Failed to start job");
      setRunning(false);
    }
  }

  async function handleDelete() {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    await removeProject({ slug: project.slug });
    router.push("/projects");
  }

  return (
    <div className="max-w-5xl">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between gap-4 mb-1">
          <div className="flex items-center gap-3 min-w-0">
            <Link href="/projects" className="text-sm text-[--muted-foreground] hover:text-[--foreground] shrink-0">
              ← Projects
            </Link>
            <span className="text-[--border]">/</span>
            <h1 className="text-lg font-semibold truncate">{project.name}</h1>
            <span className={`text-[10px] px-2 py-0.5 rounded border font-medium shrink-0 ${STATUS_BADGE[project.status]}`}>
              {project.status}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {project.pipelineConfigSlug && (
              <button
                onClick={handleQuickRun}
                disabled={running}
                className="text-xs px-3 py-1.5 rounded bg-[--primary] text-[--primary-foreground] font-semibold hover:opacity-90 disabled:opacity-40 flex items-center gap-1.5"
              >
                <Play size={11} /> {running ? "Starting…" : "Run Hydration"}
              </button>
            )}
            <button
              onClick={handleDelete}
              className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                confirmDelete
                  ? "border-red-600 text-red-300 bg-red-900/20 hover:bg-red-900/30"
                  : "border-[--border] text-[--muted-foreground] hover:text-red-400 hover:border-red-600/50"
              }`}
            >
              {confirmDelete ? "Confirm delete?" : "Delete"}
            </button>
          </div>
        </div>
        {project.description && (
          <p className="text-sm text-[--muted-foreground] pl-[calc(theme(spacing.14))]">
            {project.description}
          </p>
        )}
        {runError && <p className="mt-2 text-xs text-red-400">{runError}</p>}
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-0 border-b border-[--border] mb-6 overflow-x-auto">
        {ALL_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${
              activeTab === tab
                ? "border-[--primary] text-[--primary]"
                : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
            }`}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "overview"  && <OverviewTab  project={project} onTabSwitch={setActiveTab} />}
      {activeTab === "ontology"  && <OntologyTab  project={project} />}
      {activeTab === "data"      && <DataSourcesTab project={project} />}
      {activeTab === "pipeline"  && <PipelineTab  project={project} onRunSuccess={() => setActiveTab("jobs")} />}
      {activeTab === "jobs"      && <JobsTab      project={project} />}
      {activeTab === "explore"   && <ExploreTab   project={project} />}

      {/* Floating AI button */}
      {!aiOpen && (
        <button
          onClick={() => setAiOpen(true)}
          className="fixed bottom-6 right-6 z-30 flex items-center gap-2 px-4 py-2.5 rounded-full bg-[--primary] text-[--primary-foreground] shadow-lg hover:opacity-90 transition-opacity text-sm font-semibold"
        >
          <Sparkles size={15} />
          Ask AI
        </button>
      )}

      {/* AI Panel */}
      {aiOpen && <ProjectAIPanel project={project} onClose={() => setAiOpen(false)} />}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ProjectPage() {
  const { slug } = useParams<{ slug: string }>();
  const project = useQuery(api.projects.get, { slug });

  if (project === undefined) return <p className="text-sm text-[--muted-foreground]">Loading…</p>;
  if (project === null) return (
    <div>
      <Link href="/projects" className="text-sm text-[--primary] hover:underline mb-4 inline-block">← Back to Projects</Link>
      <p className="text-sm text-red-400">Project not found.</p>
    </div>
  );

  return <ProjectDashboard project={project} />;
}
