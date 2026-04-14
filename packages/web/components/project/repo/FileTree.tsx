"use client";

import { useState } from "react";
import { Folder, FolderOpen, FileText, ChevronRight, ChevronDown, FileCode, FileJson, FilePlus, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface RepoNode {
  name: str;
  path: str;
  isDir: boolean;
  size?: number;
  children?: RepoNode[];
}

interface FileTreeProps {
  nodes: RepoNode[];
  onFileSelect: (path: string) => void;
  selectedPath?: string;
  level?: number;
}

export function FileTree({ nodes, onFileSelect, selectedPath, level = 0 }: FileTreeProps) {
  return (
    <div className={cn("space-y-0.5", level > 0 && "ml-3 border-l border-white/5 pl-1")}>
      {nodes.map((node) => (
        <FileTreeNode 
          key={node.path} 
          node={node} 
          onFileSelect={onFileSelect} 
          selectedPath={selectedPath}
          level={level}
        />
      ))}
    </div>
  );
}

function FileTreeNode({ node, onFileSelect, selectedPath, level }: { 
  node: RepoNode, 
  onFileSelect: (path: string) => void, 
  selectedPath?: string,
  level: number 
}) {
  const [isOpen, setIsOpen] = useState(level < 1); // Expand top level by default
  const isSelected = selectedPath === node.path;
  
  const getIcon = () => {
    if (node.isDir) {
      return isOpen ? <FolderOpen size={14} className="text-[--primary]" /> : <Folder size={14} className="text-[--muted-foreground]" />;
    }
    const ext = node.name.split('.').pop()?.toLowerCase();
    if (ext === 'md') return <FileText size={14} className="text-blue-400" />;
    if (ext === 'py' || ext === 'js' || ext === 'ts') return <FileCode size={14} className="text-yellow-400" />;
    if (ext === 'json' || ext === 'yaml' || ext === 'yml') return <FileJson size={14} className="text-purple-400" />;
    return <FileText size={14} className="text-[--muted-foreground]" />;
  };

  const handleClick = () => {
    if (node.isDir) {
      setIsOpen(!isOpen);
    } else {
      onFileSelect(node.path);
    }
  };

  return (
    <div className="select-none">
      <div
        onClick={handleClick}
        className={cn(
          "flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-all group",
          isSelected 
            ? "bg-[--primary]/10 text-[--primary] border border-[--primary]/20 shadow-[inset_0_0_8px_rgba(var(--primary-rgb),0.1)]" 
            : "hover:bg-white/5 text-[--muted-foreground] hover:text-[--foreground]"
        )}
      >
        <div className="w-3 flex items-center justify-center">
            {node.isDir && (
                isOpen ? <ChevronDown size={10} className="text-[--muted-foreground]" /> : <ChevronRight size={10} className="text-[--muted-foreground]" />
            )}
        </div>
        <div className={cn("transition-transform group-hover:scale-110", isSelected && "scale-110")}>
            {getIcon()}
        </div>
        <span className={cn(
            "text-[11px] font-medium truncate",
            isSelected && "font-bold tracking-tight"
        )}>
          {node.name}
        </span>
      </div>

      {node.isDir && isOpen && node.children && (
        <FileTree 
          nodes={node.children} 
          onFileSelect={onFileSelect} 
          selectedPath={selectedPath}
          level={level + 1}
        />
      )}
    </div>
  );
}
