"use client";

import { useEffect, useState } from "react";
import { FileTree, RepoNode } from "./FileTree";
import { FileViewer } from "./FileViewer";
import { Search, Loader2, Database, BookOpen, Settings, Layout } from "lucide-react";
import { cn } from "@/lib/utils";
import { 
  ResizableHandle, 
  ResizablePanel, 
  ResizablePanelGroup 
} from "@/components/ui/resizable";

interface RepoBrowserProps {
  projectSlug: string;
  rootDir?: string;
  title: string;
  defaultSelectedPath?: string;
}

export function RepoBrowser({ projectSlug, rootDir, title, defaultSelectedPath }: RepoBrowserProps) {
  const [tree, setTree] = useState<RepoNode | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(defaultSelectedPath || null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (defaultSelectedPath) {
      setSelectedPath(defaultSelectedPath);
    }
  }, [defaultSelectedPath]);

  useEffect(() => {
    const fetchTree = async () => {
      setLoading(true);
      try {
        const url = `/api/v1/projects/${projectSlug}/repo/tree${rootDir ? `?rootDir=${encodeURIComponent(rootDir)}` : ""}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch repo tree");
        const json = await res.json();
        setTree(json);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchTree();
  }, [projectSlug, rootDir]);

  return (
    <div className="h-full flex flex-col bg-background animate-in fade-in duration-500">
      <ResizablePanelGroup direction="horizontal">
        {/* Sub-Tree Sidebar */}
        <ResizablePanel defaultSize={20} minSize={15} className="border-r border-white/5 bg-black/40">
           <div className="h-full flex flex-col">
              <div className="p-4 border-b border-white/5 flex items-center justify-between bg-black/40">
                <div className="flex items-center gap-2">
                    <Database size={14} className="text-[--primary]" />
                    <h3 className="text-[10px] font-black uppercase tracking-[0.2em]">{title}</h3>
                </div>
              </div>
              
              <div className="flex-1 overflow-auto p-2 custom-scrollbar">
                {loading ? (
                  <div className="p-8 flex justify-center opacity-20">
                    <Loader2 className="animate-spin" size={20} />
                  </div>
                ) : tree?.children ? (
                  <FileTree 
                    nodes={tree.children} 
                    onFileSelect={setSelectedPath} 
                    selectedPath={selectedPath || undefined}
                  />
                ) : (
                  <div className="p-8 text-center opacity-20 italic text-[10px]">
                     No files found in {rootDir || "root"}
                  </div>
                )}
              </div>
           </div>
        </ResizablePanel>

        <ResizableHandle />

        {/* Viewer Area */}
        <ResizablePanel defaultSize={80}>
          <FileViewer projectSlug={projectSlug} filePath={selectedPath} />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
