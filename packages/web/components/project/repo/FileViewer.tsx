"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import Editor from "@monaco-editor/react";
import { Loader2, FileCode, FileText, Download, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface FileContent {
  path: string;
  content: string;
  extension: string;
  size: number;
}

interface FileViewerProps {
  projectSlug: string;
  filePath: string | null;
}

export function FileViewer({ projectSlug, filePath }: FileViewerProps) {
  const [data, setData] = useState<FileContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!filePath) {
      setData(null);
      return;
    }

    const fetchFile = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/v1/projects/${projectSlug}/repo/file?path=${encodeURIComponent(filePath)}`);
        if (!res.ok) throw new Error("Failed to fetch file");
        const json = await res.json();
        setData(json);
      } catch (err) {
        console.error(err);
        toast.error("Failed to load file content");
      } finally {
        setLoading(false);
      }
    };

    fetchFile();
  }, [projectSlug, filePath]);

  const handleCopy = () => {
    if (!data) return;
    navigator.clipboard.writeText(data.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success("Copied to clipboard");
  };

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center opacity-40">
        <Loader2 className="animate-spin mb-2" size={32} />
        <p className="text-xs font-medium uppercase tracking-[0.2em]">Reading Repository...</p>
      </div>
    );
  }

  if (!filePath || !data) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-8 opacity-20">
        <div className="w-20 h-20 rounded-3xl bg-white/5 border border-white/10 flex items-center justify-center mb-6">
            <FileText size={40} strokeWidth={1} />
        </div>
        <h3 className="text-sm font-bold uppercase tracking-widest">No File Selected</h3>
        <p className="text-[10px] mt-2 max-w-[200px] leading-relaxed">
          Select a file from the repository tree to view its contents, specifications, or code.
        </p>
      </div>
    );
  }

  const isMarkdown = data.extension === ".md";
  const language = data.extension.slice(1) || "text";

  return (
    <div className="h-full flex flex-col bg-black/20">
      {/* Viewer Header */}
      <div className="h-12 border-b border-white/5 flex items-center justify-between px-6 bg-black/40">
        <div className="flex items-center gap-3">
            <div className="p-1.5 rounded-lg bg-white/5 border border-white/10">
                {isMarkdown ? <FileText size={14} className="text-blue-400" /> : <FileCode size={14} className="text-yellow-400" />}
            </div>
            <div>
                <p className="text-[11px] font-bold tracking-tight">{data.path.split('/').pop()}</p>
                <p className="text-[8px] text-[--muted-foreground] uppercase tracking-tighter opacity-60">{data.path}</p>
            </div>
        </div>
        <div className="flex items-center gap-2">
            <button 
                onClick={handleCopy}
                className="p-2 rounded-lg hover:bg-white/5 text-[--muted-foreground] hover:text-[--foreground] transition-all"
                title="Copy content"
            >
                {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
            </button>
            <div className="h-4 w-px bg-white/10 mx-1" />
            <span className="text-[9px] font-bold text-[--muted-foreground] opacity-40 uppercase tracking-tighter">
                {(data.size / 1024).toFixed(1)} KB
            </span>
        </div>
      </div>

      {/* Viewer Content */}
      <div className="flex-1 overflow-auto custom-scrollbar">
        {isMarkdown ? (
          <div className="p-8 max-w-4xl mx-auto">
            <div className="prose prose-sm prose-invert prose-p:leading-relaxed prose-pre:bg-white/5 prose-pre:border prose-pre:border-white/10 prose-headings:font-black prose-headings:tracking-tight prose-a:text-[--primary] max-w-none">
                <ReactMarkdown>{data.content}</ReactMarkdown>
            </div>
          </div>
        ) : (
          <div className="h-full">
            <Editor
              height="100%"
              defaultLanguage={language}
              defaultValue={data.content}
              theme="vs-dark"
              options={{
                readOnly: true,
                fontSize: 12,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                lineNumbers: "on",
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                padding: { top: 20 },
                scrollbar: {
                    verticalScrollbarSize: 10,
                    horizontalScrollbarSize: 10
                }
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
