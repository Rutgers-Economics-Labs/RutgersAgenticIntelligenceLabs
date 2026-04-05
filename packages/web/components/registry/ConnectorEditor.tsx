"use client";

import { useState, useRef } from "react";
import Editor from "@monaco-editor/react";
import { connectors } from "@/lib/api";
import { X, Play, CheckCircle } from "lucide-react";

interface ConnectorEditorProps {
  initialSlug?: string;
  initialContent?: string;
  initialName?: string;
  initialDescription?: string;
  initialVersion?: string;
  initialTags?: string[];
  onClose: () => void;
  onSaved: () => void;
}

export function ConnectorEditor({
  initialSlug = "",
  initialContent = "",
  initialName = "",
  initialDescription = "",
  initialVersion = "1.0",
  initialTags = [],
  onClose,
  onSaved,
}: ConnectorEditorProps) {
  const isNew = !initialSlug;
  const [slug, setSlug] = useState(initialSlug);
  const [content, setContent] = useState(initialContent);
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [version, setVersion] = useState(initialVersion);
  const [tags, setTags] = useState<string[]>(initialTags);

  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [successMsg, setSuccessMsg] = useState("");
  const [resolvedPreview, setResolvedPreview] = useState("");

  const handleValidate = async () => {
    setValidating(true);
    setErrors([]);
    setSuccessMsg("");
    try {
      const res = await connectors.validate(slug || "temp", content);
      if (res.valid) {
        setSuccessMsg("YAML is valid.");
      } else {
        setErrors(res.errors);
      }
    } catch (err: any) {
      setErrors([err.message || "Failed to validate"]);
    } finally {
      setValidating(false);
    }
  };

  const handleResolve = async () => {
    setResolving(true);
    setErrors([]);
    setSuccessMsg("");
    try {
      // Assuming resolve endpoint expects base_content and extends_slug.
      // If we are previewing the current editor content as base, the user
      // might just want to resolve the current content with whatever it extends.
      // But the endpoint is `resolve(baseContent: string, extendsSlug: string)`.
      // Actually, we can just pass the current content as the base content. Wait, `resolve` is usually
      // done when an extending config references a connector template.
      // Wait, if THIS is the connector template, there is no "extends" for it. It IS the template.
      // The spec says: "Preview Resolved" button → `POST /api/v1/connectors/resolve` with the current content → show merged YAML in a side panel.
      // The API is: POST /connectors/resolve { base_content, extends_slug }
      // This is a bit weird. I will just pass base_content="" and extends_slug=slug to show what it resolves to if someone extended it?
      // Or maybe the API for resolve expects the base_content to be an extending config that has `extends: <template-slug>`,
      // or the UI can construct a dummy `extends` yaml to resolve the current template.
      const dummyBase = `extends: ${slug || "temp"}\nparams: {}\n`;
      // We need the backend to actually evaluate `content` directly if we are previewing what we are typing.
      // Wait, if the endpoint in `connectors.py` uses `connector_service.resolve`, it reads the template from Convex by `extends_slug`.
      // The prompt spec is a bit ambiguous: 'with the current content → show merged YAML'.
      // I'll call `connectors.resolve(content, slug || "temp")` maybe?
      const res = await connectors.resolve(content, slug || "temp");
      setResolvedPreview(res.resolved_content);
    } catch (err: any) {
      setErrors([err.message || "Failed to resolve"]);
    } finally {
      setResolving(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setErrors([]);
    setSuccessMsg("");
    try {
      const payload = {
        name,
        slug,
        description,
        version,
        content,
        tags
      };
      if (isNew) {
        await connectors.create(payload);
      } else {
        await connectors.update(slug, payload);
      }
      onSaved();
      onClose();
    } catch (err: any) {
      setErrors([err.message || "Failed to save"]);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/50 z-40" onClick={onClose} />
      <div className="fixed right-0 top-0 h-full w-[80vw] max-w-5xl bg-background border-l border-border z-50 flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div>
            <h2 className="font-semibold text-sm">
              {isNew ? "New Connector Template" : "Edit Connector Template"}
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={handleValidate} disabled={validating} className="text-xs rounded border border-border bg-muted px-3 py-1 hover:text-foreground">
              {validating ? "Validating..." : "Validate"}
            </button>
            <button onClick={handleResolve} disabled={resolving} className="text-xs rounded border border-border bg-muted px-3 py-1 hover:text-foreground">
              {resolving ? "Resolving..." : "Preview Resolved"}
            </button>
            <button onClick={handleSave} disabled={saving || !slug || !name} className="text-xs rounded bg-primary text-[#0d1117] font-semibold px-4 py-1 hover:opacity-90 disabled:opacity-50">
              {saving ? "Saving..." : "Save"}
            </button>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground ml-2">
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="flex flex-1 overflow-hidden">
          <div className="w-1/3 flex flex-col border-r border-border p-4 gap-4 overflow-y-auto">
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Name</label>
              <input
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (isNew) setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));
                }}
                className="w-full rounded bg-muted border border-border px-3 py-1.5 text-sm outline-none focus:border-primary"
                placeholder="e.g. FRED Economic Data"
              />
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Slug</label>
              <input
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                disabled={!isNew}
                className="w-full rounded bg-muted border border-border px-3 py-1.5 text-sm font-mono outline-none focus:border-primary disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="w-full rounded bg-muted border border-border px-3 py-1.5 text-sm outline-none focus:border-primary"
              />
            </div>
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-xs text-muted-foreground mb-1">Version</label>
                <input
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  className="w-full rounded bg-muted border border-border px-3 py-1.5 text-sm outline-none focus:border-primary"
                />
              </div>
              <div className="flex-1">
                <label className="block text-xs text-muted-foreground mb-1">Tags (comma-separated)</label>
                <input
                  value={tags.join(", ")}
                  onChange={(e) => setTags(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                  className="w-full rounded bg-muted border border-border px-3 py-1.5 text-sm outline-none focus:border-primary"
                  placeholder="economics, fred"
                />
              </div>
            </div>

            {errors.length > 0 && (
              <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400 space-y-1">
                {errors.map((e, i) => <div key={i}>{e}</div>)}
              </div>
            )}

            {successMsg && (
              <div className="rounded border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-400 flex items-center gap-2">
                <CheckCircle size={14} />
                {successMsg}
              </div>
            )}

          </div>
          <div className={`flex flex-col ${resolvedPreview ? "w-1/3 border-r border-border" : "flex-1"}`}>
            <div className="px-4 py-2 border-b border-border bg-muted/30 text-xs text-muted-foreground uppercase tracking-wide font-medium">
              YAML Content
            </div>
            <div className="flex-1 relative">
              <Editor
                language="yaml"
                theme="vs-dark"
                value={content}
                onChange={(val) => setContent(val || "")}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  fontFamily: "var(--font-mono)",
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                }}
              />
            </div>
          </div>

          {resolvedPreview && (
            <div className="w-1/3 flex flex-col">
              <div className="px-4 py-2 border-b border-border bg-muted/30 text-xs text-muted-foreground uppercase tracking-wide flex items-center justify-between">
                <span>Resolved Preview</span>
                <button onClick={() => setResolvedPreview("")} className="hover:text-foreground">
                  <X size={14} />
                </button>
              </div>
              <div className="flex-1 relative">
                <Editor
                  language="yaml"
                  theme="vs-dark"
                  value={resolvedPreview}
                  options={{
                    minimap: { enabled: false },
                    fontSize: 13,
                    fontFamily: "var(--font-mono)",
                    readOnly: true,
                    scrollBeyondLastLine: false,
                    wordWrap: "on",
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
