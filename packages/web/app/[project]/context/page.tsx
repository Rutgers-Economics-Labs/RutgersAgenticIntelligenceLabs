"use client";
import { Suspense, use } from "react";
import { useState, useRef } from "react";

import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import { context as contextApi } from "@/lib/api";
import {
  Upload, Link2, FileText, Globe, Trash2,
  Loader2, BookOpen, Plus, File, AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

const TYPE_ICONS: Record<string, React.ElementType> = {
  pdf:  File,
  docx: File,
  text: FileText,
  url:  Globe,
};

const TYPE_LABELS: Record<string, string> = {
  pdf:  "PDF",
  docx: "Document",
  text: "Text",
  url:  "Website",
};

function ContextPageInner({ projectSlug }: { projectSlug: string }) {



  const docs = useQuery(api.context.list, projectSlug ? { projectSlug: projectSlug as any } : {});
  const removeDoc = useMutation(api.context.remove);

  const [tab, setTab] = useState<"upload" | "url" | "text">("upload");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // URL form
  const [url, setUrl] = useState("");
  const [urlName, setUrlName] = useState("");

  // Text form
  const [textName, setTextName] = useState("");
  const [textContent, setTextContent] = useState("");

  const flash = (msg: string) => {
    setSuccess(msg);
    setTimeout(() => setSuccess(null), 3000);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setError(null);
    try {
      await contextApi.uploadFile(file, projectSlug);
      flash(`"${file.name}" uploaded`);
    } catch (err: any) {
      setError(err.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleAddUrl = async () => {
    if (!url.trim()) return;
    setUploading(true); setError(null);
    try {
      await contextApi.addUrl(url.trim(), urlName.trim() || undefined, projectSlug);
      flash(`"${urlName || url}" added`);
      setUrl(""); setUrlName("");
    } catch (err: any) {
      setError(err.message || "Failed to fetch URL");
    } finally {
      setUploading(false);
    }
  };

  const handleAddText = async () => {
    if (!textName.trim() || !textContent.trim()) return;
    setUploading(true); setError(null);
    try {
      await contextApi.addText(textName.trim(), textContent.trim(), projectSlug);
      flash(`"${textName}" saved`);
      setTextName(""); setTextContent("");
    } catch (err: any) {
      setError(err.message || "Failed to save text");
    } finally {
      setUploading(false);
    }
  };

  const handleRemove = async (id: string) => {
    await removeDoc({ id: id as any });
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[--foreground] flex items-center gap-3">
          <BookOpen size={24} className="text-[--primary]" />
          Knowledge Base
        </h1>
        <p className="text-sm text-[--muted-foreground] mt-1">
          Upload research papers, laws, reports, or websites. Agents will search these
          before falling back to web search.
          {projectSlug
            ? " Documents here are available to this project and globally."
            : " Documents here are available to all projects."}
        </p>
      </div>

      {/* Feedback */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-500 text-sm">
          <AlertCircle size={15} /> {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-green-500/10 border border-green-500/20 text-green-500 text-sm">
          ✓ {success}
        </div>
      )}

      {/* Add panel */}
      <div className="rounded-2xl border border-[--border] bg-[--card] overflow-hidden">
        <div className="flex border-b border-[--border]">
          {(["upload", "url", "text"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex-1 py-3 text-xs font-semibold uppercase tracking-wide transition-colors",
                tab === t
                  ? "bg-[--primary]/10 text-[--primary] border-b-2 border-[--primary]"
                  : "text-[--muted-foreground] hover:text-[--foreground]"
              )}
            >
              {t === "upload" ? "Upload File" : t === "url" ? "Web URL" : "Paste Text"}
            </button>
          ))}
        </div>

        <div className="p-6">
          {tab === "upload" && (
            <div
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-[--border] rounded-xl p-10 text-center cursor-pointer hover:border-[--primary]/50 hover:bg-[--primary]/5 transition-all group"
            >
              {uploading
                ? <Loader2 size={28} className="animate-spin text-[--primary] mx-auto mb-3" />
                : <Upload size={28} className="text-[--muted-foreground] group-hover:text-[--primary] mx-auto mb-3 transition-colors" />
              }
              <p className="text-sm font-medium text-[--foreground]">
                {uploading ? "Uploading…" : "Drop a file or click to browse"}
              </p>
              <p className="text-xs text-[--muted-foreground] mt-1">PDF, DOCX, TXT — up to 50 MB</p>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt,.md"
                className="hidden"
                onChange={handleFileUpload}
              />
            </div>
          )}

          {tab === "url" && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[--muted-foreground] mb-1.5 uppercase tracking-wide">
                  URL
                </label>
                <input
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  placeholder="https://example.com/report"
                  className="w-full px-3 py-2 rounded-lg border border-[--border] bg-[--muted]/20 text-sm text-[--foreground] focus:outline-none focus:border-[--primary]/50"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[--muted-foreground] mb-1.5 uppercase tracking-wide">
                  Name (optional)
                </label>
                <input
                  value={urlName}
                  onChange={e => setUrlName(e.target.value)}
                  placeholder="NJ Economic Report 2024"
                  className="w-full px-3 py-2 rounded-lg border border-[--border] bg-[--muted]/20 text-sm text-[--foreground] focus:outline-none focus:border-[--primary]/50"
                />
              </div>
              <button
                onClick={handleAddUrl}
                disabled={uploading || !url.trim()}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--primary] text-white text-sm font-semibold disabled:opacity-50 hover:bg-[--primary]/90 transition-colors"
              >
                {uploading ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
                Fetch & Add
              </button>
            </div>
          )}

          {tab === "text" && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[--muted-foreground] mb-1.5 uppercase tracking-wide">
                  Title
                </label>
                <input
                  value={textName}
                  onChange={e => setTextName(e.target.value)}
                  placeholder="NJ Housing Act 2023"
                  className="w-full px-3 py-2 rounded-lg border border-[--border] bg-[--muted]/20 text-sm text-[--foreground] focus:outline-none focus:border-[--primary]/50"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[--muted-foreground] mb-1.5 uppercase tracking-wide">
                  Content
                </label>
                <textarea
                  value={textContent}
                  onChange={e => setTextContent(e.target.value)}
                  placeholder="Paste the full text of the document…"
                  rows={8}
                  className="w-full px-3 py-2 rounded-lg border border-[--border] bg-[--muted]/20 text-sm text-[--foreground] focus:outline-none focus:border-[--primary]/50 resize-none font-mono"
                />
              </div>
              <button
                onClick={handleAddText}
                disabled={uploading || !textName.trim() || !textContent.trim()}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--primary] text-white text-sm font-semibold disabled:opacity-50 hover:bg-[--primary]/90 transition-colors"
              >
                {uploading ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                Save Document
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Document list */}
      <div>
        <h2 className="text-sm font-semibold text-[--muted-foreground] uppercase tracking-wide mb-3">
          {docs ? `${docs.length} Document${docs.length !== 1 ? "s" : ""}` : "Documents"}
        </h2>

        {!docs && (
          <div className="flex items-center gap-2 text-sm text-[--muted-foreground] py-4">
            <Loader2 size={14} className="animate-spin" /> Loading…
          </div>
        )}

        {docs?.length === 0 && (
          <div className="text-center py-12 text-[--muted-foreground]">
            <BookOpen size={32} className="mx-auto mb-3 opacity-30" />
            <p className="text-sm">No documents yet. Add research papers, laws, or reports above.</p>
          </div>
        )}

        <div className="space-y-2">
          {docs?.map((doc: any) => {
            const Icon = TYPE_ICONS[doc.type] ?? FileText;
            const chars = doc.content?.length ?? 0;
            const scope = doc.projectSlug ? "Project" : "Global";
            return (
              <div
                key={doc._id}
                className="flex items-center gap-4 px-4 py-3 rounded-xl border border-[--border] bg-[--card] hover:bg-[--muted]/20 transition-colors group"
              >
                <div className="w-9 h-9 rounded-lg bg-[--primary]/10 flex items-center justify-center shrink-0">
                  <Icon size={16} className="text-[--primary]" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[--foreground] truncate">{doc.name}</p>
                  <p className="text-xs text-[--muted-foreground] mt-0.5">
                    {TYPE_LABELS[doc.type] ?? doc.type}
                    {doc.url && <span className="ml-2 truncate font-mono opacity-60">{doc.url}</span>}
                    <span className="mx-2 opacity-30">·</span>
                    {Math.round(chars / 1000)}k chars
                    <span className="mx-2 opacity-30">·</span>
                    <span className={scope === "Global" ? "text-[--primary]" : "text-[--muted-foreground]"}>{scope}</span>
                  </p>
                </div>
                <button
                  onClick={() => handleRemove(doc._id)}
                  className="opacity-0 group-hover:opacity-100 p-2 text-[--muted-foreground] hover:text-red-500 transition-all"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}


export default function ContextPage({ params }: { params: Promise<{ project: string }> }) {
  const { project } = use(params);
  return (
    <Suspense fallback={<div className="p-8 text-[--muted-foreground]">Loading context...</div>}>
      <ContextPageInner projectSlug={project} />
    </Suspense>
  );
}
