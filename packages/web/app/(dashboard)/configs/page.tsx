"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { useState, useEffect, useRef } from "react";
import { agent, configs, type ConfigDoc, type ModelInfo } from "@/lib/api";

type Tab = "apis" | "ontologies" | "pipelines";

const CONFIG_TYPE_LABEL: Record<Tab, string> = {
  apis: "api", ontologies: "ontology", pipelines: "pipeline",
};

function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

// ── YAML Editor Panel ─────────────────────────────────────────────────────────

function EditorPanel({
  tab, doc, onClose, onSaved,
}: {
  tab: Tab;
  doc: ConfigDoc | null; // null = new
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = doc === null;
  const [name, setName] = useState(doc?.name ?? "");
  const [slug, setSlug] = useState(doc?.slug ?? "");
  const [content, setContent] = useState(doc?.content ?? "");
  const [isPublic, setIsPublic] = useState(doc?.isPublic ?? false);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-slug from name when creating
  useEffect(() => {
    if (isNew) setSlug(name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));
  }, [name, isNew]);

  // Tab key inserts 2 spaces in textarea
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Tab") {
      e.preventDefault();
      const el = e.currentTarget;
      const s = el.selectionStart, end = el.selectionEnd;
      const next = content.slice(0, s) + "  " + content.slice(end);
      setContent(next);
      requestAnimationFrame(() => { el.selectionStart = el.selectionEnd = s + 2; });
    }
  }

  async function handleSave() {
    setSaving(true);
    setErrors([]);
    try {
      // Validate first
      const v = await configs.validate(CONFIG_TYPE_LABEL[tab], content);
      if (!v.valid) { setErrors(v.errors); setSaving(false); return; }

      const body = { name, slug, content, isPublic, tags: [] };
      if (isNew) await configs.create(tab, body);
      else await configs.update(tab, doc!.slug, body);
      onSaved();
      onClose();
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : "Save failed"]);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    setDeleting(true);
    try {
      await configs.delete(tab, doc!.slug);
      onSaved();
      onClose();
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : "Delete failed"]);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/50 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-full max-w-2xl bg-[--background] border-l border-[--border] z-50 flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[--border]">
          <div>
            <h2 className="font-semibold text-sm">
              {isNew ? `New ${CONFIG_TYPE_LABEL[tab]} config` : doc!.name}
            </h2>
            {!isNew && <p className="text-xs text-[--muted-foreground] font-mono mt-0.5">{doc!.slug}</p>}
          </div>
          <button onClick={onClose} className="text-[--muted-foreground] hover:text-[--foreground] text-xl leading-none px-1">×</button>
        </div>

        {/* Meta fields (new only) */}
        {isNew && (
          <div className="px-5 pt-4 pb-3 border-b border-[--border] flex gap-4">
            <div className="flex-1">
              <label className="text-xs text-[--muted-foreground] block mb-1">Name</label>
              <input
                value={name} onChange={(e) => setName(e.target.value)}
                placeholder="My Data Source"
                className="w-full px-3 py-1.5 rounded border border-[--border] bg-[--muted] text-sm text-[--foreground] outline-none focus:border-[--primary]"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-[--muted-foreground] block mb-1">Slug</label>
              <input
                value={slug} onChange={(e) => setSlug(e.target.value)}
                placeholder="my-data-source"
                className="w-full px-3 py-1.5 rounded border border-[--border] bg-[--muted] text-sm text-[--foreground] font-mono outline-none focus:border-[--primary]"
              />
            </div>
          </div>
        )}

        {/* YAML editor */}
        <div className="flex-1 relative overflow-hidden flex flex-col px-5 pt-4 pb-2">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs text-[--muted-foreground] uppercase tracking-wide">YAML</label>
            <label className="flex items-center gap-2 text-xs text-[--muted-foreground] cursor-pointer">
              <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)}
                className="accent-[--primary]" />
              Public
            </label>
          </div>
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            spellCheck={false}
            className="flex-1 w-full font-mono text-sm bg-[--muted] border border-[--border] rounded p-4 text-[--foreground] resize-none outline-none focus:border-[--primary] leading-6"
            placeholder={`# ${CONFIG_TYPE_LABEL[tab]} config\nname: my-config\n...`}
          />
        </div>

        {/* Validation errors */}
        {errors.length > 0 && (
          <div className="mx-5 mb-2 p-3 rounded bg-red-900/30 border border-red-700/60">
            {errors.map((e, i) => (
              <p key={i} className="text-xs text-red-300 font-mono">{e}</p>
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-[--border]">
          <div>
            {!isNew && (
              <button
                onClick={handleDelete}
                disabled={deleting}
                className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                  confirmDelete
                    ? "border-red-600 bg-red-600/20 text-red-300 hover:bg-red-600/30"
                    : "border-[--border] text-[--muted-foreground] hover:text-red-400 hover:border-red-600/50"
                }`}
              >
                {deleting ? "Deleting…" : confirmDelete ? "Confirm delete" : "Delete"}
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !content.trim() || (isNew && (!name.trim() || !slug.trim()))}
              className="text-xs px-4 py-1.5 rounded bg-[--primary] text-[#0d1117] font-semibold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saving ? "Saving…" : isNew ? "Create" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

type InferenceStep = "input" | "review" | "save";

function InferenceModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [step, setStep] = useState<InferenceStep>("input");
  const [inputMode, setInputMode] = useState<"sample" | "describe">("sample");
  const [sample, setSample] = useState("");
  const [description, setDescription] = useState("");
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [apiYaml, setApiYaml] = useState("");
  const [ontologyYaml, setOntologyYaml] = useState("");
  const [explanation, setExplanation] = useState("");
  const [apiName, setApiName] = useState("Generated API Config");
  const [apiSlug, setApiSlug] = useState("generated-api-config");
  const [ontologyName, setOntologyName] = useState("Generated Ontology Config");
  const [ontologySlug, setOntologySlug] = useState("generated-ontology-config");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    agent.models()
      .then((data) => {
        setModels(data.models);
        setSelectedModel(data.default);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    setApiSlug(slugify(apiName));
  }, [apiName]);

  useEffect(() => {
    setOntologySlug(slugify(ontologyName));
  }, [ontologyName]);

  async function handleGenerate() {
    setLoading(true);
    setError("");
    try {
      const result = await agent.inferSchema(
        inputMode === "sample" ? sample : undefined,
        description || (inputMode === "describe" ? sample : undefined),
        selectedModel || undefined
      );
      setApiYaml(result.api_yaml);
      setOntologyYaml(result.ontology_yaml);
      setExplanation(result.explanation);
      setStep("review");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to generate configs");
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveBoth() {
    setSaving(true);
    setError("");
    try {
      await Promise.all([
        configs.create("apis", {
          name: apiName,
          slug: apiSlug,
          content: apiYaml,
          isPublic: false,
          tags: [],
        }),
        configs.create("ontologies", {
          name: ontologyName,
          slug: ontologySlug,
          content: ontologyYaml,
          isPublic: false,
          tags: [],
        }),
      ]);
      onSaved();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save generated configs");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/50 z-40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-6xl max-h-[92vh] overflow-hidden rounded-2xl border border-[--border] bg-[--background] shadow-2xl flex flex-col">
          <div className="flex items-center justify-between px-5 py-4 border-b border-[--border]">
            <div>
              <h2 className="font-semibold text-sm">Generate from sample</h2>
              <p className="mt-0.5 text-xs text-[--muted-foreground]">
                Infer API and ontology YAML from a sample or description.
              </p>
            </div>
            <button onClick={onClose} className="text-[--muted-foreground] hover:text-[--foreground] text-xl leading-none px-1">×</button>
          </div>

          <div className="px-5 py-3 border-b border-[--border] flex gap-2 text-xs">
            {[
              { id: "input", label: "1. Input" },
              { id: "review", label: "2. Review" },
              { id: "save", label: "3. Save" },
            ].map((item) => (
              <div
                key={item.id}
                className={`rounded-full px-3 py-1 ${
                  step === item.id
                    ? "bg-[--primary] text-[#0d1117] font-semibold"
                    : "bg-[--muted] text-[--muted-foreground]"
                }`}
              >
                {item.label}
              </div>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-5">
            {step === "input" && (
              <div className="space-y-5">
                <div className="flex gap-3">
                  <button
                    onClick={() => setInputMode("sample")}
                    className={`rounded-lg border px-3 py-2 text-sm ${
                      inputMode === "sample"
                        ? "border-[--primary] bg-[--primary]/10 text-[--primary]"
                        : "border-[--border] text-[--muted-foreground]"
                    }`}
                  >
                    Paste sample
                  </button>
                  <button
                    onClick={() => setInputMode("describe")}
                    className={`rounded-lg border px-3 py-2 text-sm ${
                      inputMode === "describe"
                        ? "border-[--primary] bg-[--primary]/10 text-[--primary]"
                        : "border-[--border] text-[--muted-foreground]"
                    }`}
                  >
                    Describe the data
                  </button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-4">
                  <div className="space-y-4">
                    <div>
                      <label className="text-xs text-[--muted-foreground] block mb-1">
                        {inputMode === "sample" ? "CSV header / JSON sample" : "Data description"}
                      </label>
                      <textarea
                        value={sample}
                        onChange={(e) => setSample(e.target.value)}
                        rows={12}
                        placeholder={
                          inputMode === "sample"
                            ? "Paste CSV rows or JSON here..."
                            : "Describe the data you want to ingest..."
                        }
                        className="w-full rounded-lg border border-[--border] bg-[--muted] p-4 text-sm text-[--foreground] outline-none focus:border-[--primary] resize-none"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-[--muted-foreground] block mb-1">Additional description (optional)</label>
                      <input
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Context for the generator..."
                        className="w-full rounded-lg border border-[--border] bg-[--muted] px-3 py-2 text-sm text-[--foreground] outline-none focus:border-[--primary]"
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label className="text-xs text-[--muted-foreground] block mb-1">Model</label>
                      <select
                        value={selectedModel}
                        onChange={(e) => setSelectedModel(e.target.value)}
                        className="w-full rounded-lg border border-[--border] bg-[--muted] px-3 py-2 text-sm text-[--foreground] outline-none focus:border-[--primary]"
                      >
                        {models.map((model) => (
                          <option key={model.id} value={model.id}>{model.label}</option>
                        ))}
                      </select>
                    </div>
                    <button
                      onClick={handleGenerate}
                      disabled={loading || !sample.trim()}
                      className="w-full rounded-lg bg-[--primary] px-4 py-2 text-sm font-semibold text-[#0d1117] hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {loading ? "Generating configs…" : "Generate"}
                    </button>
                    <p className="text-xs text-[--muted-foreground] leading-relaxed">
                      This uses the existing `/agent/infer-schema` backend to suggest both config files.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {step === "review" && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-[--muted-foreground] block mb-1">API Config YAML</label>
                    <textarea
                      value={apiYaml}
                      onChange={(e) => setApiYaml(e.target.value)}
                      rows={18}
                      spellCheck={false}
                      className="w-full rounded-lg border border-[--border] bg-[--muted] p-4 font-mono text-sm text-[--foreground] outline-none focus:border-[--primary] resize-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-[--muted-foreground] block mb-1">Ontology Config YAML</label>
                    <textarea
                      value={ontologyYaml}
                      onChange={(e) => setOntologyYaml(e.target.value)}
                      rows={18}
                      spellCheck={false}
                      className="w-full rounded-lg border border-[--border] bg-[--muted] p-4 font-mono text-sm text-[--foreground] outline-none focus:border-[--primary] resize-none"
                    />
                  </div>
                </div>
                {explanation && (
                  <div className="rounded-lg border border-[--border] bg-[--card] p-4 text-sm text-[--muted-foreground]">
                    {explanation}
                  </div>
                )}
              </div>
            )}

            {step === "save" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-[--border] bg-[--card] p-4 space-y-3">
                  <h3 className="font-medium text-sm">API config</h3>
                  <div>
                    <label className="text-xs text-[--muted-foreground] block mb-1">Name</label>
                    <input
                      value={apiName}
                      onChange={(e) => setApiName(e.target.value)}
                      className="w-full rounded-lg border border-[--border] bg-[--muted] px-3 py-2 text-sm text-[--foreground] outline-none focus:border-[--primary]"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-[--muted-foreground] block mb-1">Slug</label>
                    <input
                      value={apiSlug}
                      onChange={(e) => setApiSlug(e.target.value)}
                      className="w-full rounded-lg border border-[--border] bg-[--muted] px-3 py-2 font-mono text-sm text-[--foreground] outline-none focus:border-[--primary]"
                    />
                  </div>
                </div>

                <div className="rounded-xl border border-[--border] bg-[--card] p-4 space-y-3">
                  <h3 className="font-medium text-sm">Ontology config</h3>
                  <div>
                    <label className="text-xs text-[--muted-foreground] block mb-1">Name</label>
                    <input
                      value={ontologyName}
                      onChange={(e) => setOntologyName(e.target.value)}
                      className="w-full rounded-lg border border-[--border] bg-[--muted] px-3 py-2 text-sm text-[--foreground] outline-none focus:border-[--primary]"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-[--muted-foreground] block mb-1">Slug</label>
                    <input
                      value={ontologySlug}
                      onChange={(e) => setOntologySlug(e.target.value)}
                      className="w-full rounded-lg border border-[--border] bg-[--muted] px-3 py-2 font-mono text-sm text-[--foreground] outline-none focus:border-[--primary]"
                    />
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="mt-4 rounded-lg border border-red-700/60 bg-red-900/20 p-3 text-sm text-red-300">
                {error}
              </div>
            )}
          </div>

          <div className="flex items-center justify-between px-5 py-4 border-t border-[--border]">
            <div>
              {step !== "input" && (
                <button
                  onClick={() => setStep(step === "save" ? "review" : "input")}
                  className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
                >
                  Back
                </button>
              )}
            </div>
            <div className="flex gap-2">
              {error && step === "input" && (
                <button
                  onClick={() => {
                    setError("");
                    setStep("input");
                  }}
                  className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
                >
                  Try again
                </button>
              )}
              <button
                onClick={onClose}
                className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
              >
                Cancel
              </button>
              {step === "review" && (
                <button
                  onClick={() => setStep("save")}
                  disabled={!apiYaml.trim() || !ontologyYaml.trim()}
                  className="text-sm px-4 py-1.5 rounded bg-[--primary] text-[#0d1117] font-semibold hover:opacity-90 disabled:opacity-40"
                >
                  Continue
                </button>
              )}
              {step === "save" && (
                <button
                  onClick={handleSaveBoth}
                  disabled={saving || !apiName.trim() || !apiSlug.trim() || !ontologyName.trim() || !ontologySlug.trim()}
                  className="text-sm px-4 py-1.5 rounded bg-[--primary] text-[#0d1117] font-semibold hover:opacity-90 disabled:opacity-40"
                >
                  {saving ? "Saving…" : "Save Both"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ConfigsPage() {
  const [tab, setTab] = useState<Tab>("apis");
  const [editDoc, setEditDoc] = useState<ConfigDoc | null | undefined>(undefined); // undefined=closed, null=new
  const [showInference, setShowInference] = useState(false);

  const apiConfigs = useQuery(api.configs.listApis, {});
  const ontologyConfigs = useQuery(api.configs.listOntologies, {});
  const pipelineConfigs = useQuery(api.configs.listPipelines, {});

  const tabs: { id: Tab; label: string; count: number | undefined }[] = [
    { id: "apis", label: "Data Sources", count: apiConfigs?.length },
    { id: "ontologies", label: "Ontologies", count: ontologyConfigs?.length },
    { id: "pipelines", label: "Pipelines", count: pipelineConfigs?.length },
  ];

  const items =
    tab === "apis" ? apiConfigs :
    tab === "ontologies" ? ontologyConfigs :
    pipelineConfigs;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Configs</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setEditDoc(null)}
            className="text-sm px-3 py-1.5 rounded bg-[--primary] text-[#0d1117] font-semibold hover:opacity-90"
          >
            + New Config
          </button>
          <button
            onClick={() => setShowInference(true)}
            className="text-sm px-3 py-1.5 rounded border border-[--border] text-[--foreground] hover:border-[--primary]/50 hover:text-[--primary]"
          >
            ✦ Generate from sample
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-[--border]">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === t.id
                ? "border-[--primary] text-[--primary]"
                : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
            }`}
          >
            {t.label}
            {t.count !== undefined && (
              <span className="ml-2 text-xs opacity-60">({t.count})</span>
            )}
          </button>
        ))}
      </div>

      {items === undefined && <p className="text-[--muted-foreground] text-sm">Loading…</p>}

      {items?.length === 0 && (
        <div className="flex flex-col items-center justify-center h-48 border border-dashed border-[--border] rounded-lg gap-3">
          <p className="text-[--muted-foreground] text-sm">No {tab} configs yet.</p>
          <button
            onClick={() => setEditDoc(null)}
            className="text-xs px-3 py-1.5 rounded border border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
          >
            + Create one
          </button>
        </div>
      )}

      {items && items.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map((cfg) => (
            <button
              key={cfg._id}
              onClick={() => setEditDoc(cfg as unknown as ConfigDoc)}
              className="p-4 rounded-lg border border-[--border] bg-[--card] hover:border-[--primary]/60 hover:bg-[--muted] transition-colors text-left group"
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-medium text-sm group-hover:text-[--primary] transition-colors">{cfg.name}</h3>
                {cfg.isPublic && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[--primary]/10 text-[--primary] border border-[--primary]/20">
                    public
                  </span>
                )}
              </div>
              <p className="text-xs font-mono text-[--muted-foreground] mb-3">{cfg.slug}</p>
              {"tags" in cfg && (cfg as { tags: string[] }).tags.length > 0 && (
                <div className="flex gap-1 flex-wrap mb-2">
                  {(cfg as { tags: string[] }).tags.map((tag) => (
                    <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-[--muted] text-[--muted-foreground]">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              {/* YAML preview — first 3 lines */}
              <pre className="text-[10px] text-[--muted-foreground] font-mono leading-4 truncate-lines overflow-hidden mt-2 opacity-60">
                {(cfg as unknown as ConfigDoc).content?.split("\n").slice(0, 3).join("\n")}
              </pre>
              <p className="text-[10px] text-[--muted-foreground] mt-2">
                Updated {new Date(cfg.updatedAt).toLocaleDateString()}
              </p>
            </button>
          ))}
        </div>
      )}

      {/* Editor panel */}
      {editDoc !== undefined && (
        <EditorPanel
          tab={tab}
          doc={editDoc}
          onClose={() => setEditDoc(undefined)}
          onSaved={() => {}}
        />
      )}

      {showInference && (
        <InferenceModal
          onClose={() => setShowInference(false)}
          onSaved={() => {}}
        />
      )}
    </div>
  );
}
