"use client";
import React, { useState, useEffect, useMemo, useRef } from "react";
import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";
import { analysis } from "@/lib/api";
import { AnalysisHistory } from "./AnalysisHistory";
import { SchemaBrowser } from "./SchemaBrowser";
import { AgentPanel } from "./AgentPanel";
import { ToolResult } from "@/components/jobs/ToolResult";
import {
  Play, Save, Plus, LayoutDashboard, Code, Terminal,
  ChevronRight, ChevronLeft, Loader2, CheckCircle2, AlertCircle,
  Database, FileText, Sparkles
} from "lucide-react";
import Editor from "@monaco-editor/react";
import * as Tabs from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

interface AnalysisWorkspaceProps {
  projectId: Id<"projects">;
}

const DEFAULT_CODE = `import pandas as pd
import matplotlib.pyplot as plt

# 1. Query data from DuckDB
# df = sql("SELECT * FROM State LIMIT 10")

# 2. Analyze
# print(df.describe())

# 3. Visualize
# df.plot(kind='bar')
# plt.title("Sample Analysis")
# plt.show()
`;

export function AnalysisWorkspace({ projectId }: AnalysisWorkspaceProps) {
  const [activeScriptId, setActiveScriptId] = useState<Id<"analysisScripts"> | null>(null);
  const [scriptName, setScriptName] = useState("New Analysis");
  const [code, setCode] = useState(DEFAULT_CODE);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [rightPanel, setRightPanel] = useState<"schema" | "agent">("schema");
  const [activeTab, setActiveTab] = useState("results");
  
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const [lastJobId, setLastJobId] = useState<string | null>(null);

  const saveScript = useMutation(api.analysis.saveScript);
  const runningJob = useQuery(api.executions.get, runningJobId ? { jobId: runningJobId } : "skip");
  const lastJob = useQuery(api.executions.get, lastJobId ? { jobId: lastJobId } : "skip");
  
  const logs = useQuery(api.jobs.getLogs, (runningJobId || lastJobId) ? { jobId: (runningJobId || lastJobId) as string } : "skip");

  // Load script when selected from history
  const handleSelectScript = (script: any) => {
    setActiveScriptId(script._id);
    setScriptName(script.name);
    setCode(script.code);
    if (script.lastJobId) {
      setLastJobId(script.lastJobId);
      setActiveTab("results");
    }
  };

  const handleNew = () => {
    setActiveScriptId(null);
    setScriptName("New Analysis");
    setCode(DEFAULT_CODE);
    setLastJobId(null);
    setRunningJobId(null);
    setActiveTab("editor");
  };

  const handleSave = async () => {
    const id = await saveScript({
      id: activeScriptId || undefined,
      projectId,
      name: scriptName,
      code,
    });
    if (!activeScriptId) setActiveScriptId(id as Id<"analysisScripts">);
  };

  const handleRun = async () => {
    try {
      setRunningJobId(null);
      setActiveTab("logs");
      const { jobId } = await analysis.runCode(code, projectId);
      setRunningJobId(jobId);
      
      // Update script with last job ID
      if (activeScriptId) {
        await saveScript({
          id: activeScriptId,
          projectId,
          name: scriptName,
          code,
          lastJobId: jobId as any,
        });
      }
    } catch (err) {
      console.error("Failed to run analysis:", err);
    }
  };

  // Switch to results when job succeeds
  useEffect(() => {
    if (runningJob?.status === "success") {
      setLastJobId(runningJobId);
      setRunningJobId(null);
      setActiveTab("results");
    }
  }, [runningJob?.status, runningJobId]);

  const currentJob = runningJob || lastJob;

  return (
    <div className="flex h-[calc(100vh-120px)] border border-[--border] rounded-xl overflow-hidden bg-[--background]">
      
      {/* Left History Sidebar */}
      <div className="w-64 shrink-0 overflow-hidden hidden md:block">
        <AnalysisHistory 
          projectId={projectId} 
          onSelect={handleSelectScript} 
          selectedId={activeScriptId || undefined} 
        />
      </div>

      {/* Main Workspace */}
      <div className="flex-1 flex flex-col min-w-0 bg-[--card]">
        
        {/* Toolbar */}
        <div className="h-14 border-b border-[--border] flex items-center justify-between px-4 bg-[--muted]/10">
          <div className="flex items-center gap-3 min-w-0">
            <input
              value={scriptName}
              onChange={(e) => setScriptName(e.target.value)}
              className="bg-transparent border-none text-[15px] font-semibold text-[--foreground] focus:outline-none focus:ring-1 focus:ring-[--primary]/30 rounded px-2 py-1 truncate max-w-[300px]"
              placeholder="Untitled Analysis"
            />
            {currentJob?.status === "running" && (
              <div className="flex items-center gap-2 px-2 py-1 rounded bg-[--primary]/10 text-[--primary] text-[10px] uppercase font-bold tracking-wider animate-pulse">
                <Loader2 size={12} className="animate-spin" />
                Executing...
              </div>
            )}
            {currentJob?.status === "success" && (
              <div className="flex items-center gap-1.5 text-green-500 text-[10px] uppercase font-bold">
                 <CheckCircle2 size={14} />
                 Ready
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleNew}
              className="p-2 text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted]/50 rounded-lg transition-colors"
              title="New Analysis"
            >
              <Plus size={18} />
            </button>
            <button
              onClick={handleSave}
              className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold text-[--foreground] border border-[--border] bg-[--card] hover:bg-[--muted]/50 rounded-lg transition-all"
            >
              <Save size={14} className="text-[--muted-foreground]" />
              Save
            </button>
            <button
              onClick={handleRun}
              disabled={!!runningJobId}
              className="flex items-center gap-2 px-4 py-1.5 text-xs font-bold text-white bg-[--primary] hover:bg-[--primary]/90 rounded-lg shadow-sm shadow-[--primary]/20 transition-all disabled:opacity-50"
            >
              <Play size={14} fill="currentColor" />
              Run Analysis
            </button>
          </div>
        </div>

        {/* Workspace Content */}
        <Tabs.Root value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
          <div className="px-4 border-b border-[--border] flex items-center justify-between bg-[--muted]/5">
            <Tabs.List className="flex">
              <Tabs.Trigger
                value="results"
                className={cn(
                  "px-4 py-3 text-xs font-semibold border-b-2 transition-all flex items-center gap-2",
                  activeTab === "results" ? "border-[--primary] text-[--foreground]" : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
                )}
              >
                <LayoutDashboard size={14} />
                Results
              </Tabs.Trigger>
              <Tabs.Trigger
                value="editor"
                className={cn(
                  "px-4 py-3 text-xs font-semibold border-b-2 transition-all flex items-center gap-2",
                  activeTab === "editor" ? "border-[--primary] text-[--foreground]" : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
                )}
              >
                <Code size={14} />
                Researcher IDE
              </Tabs.Trigger>
              <Tabs.Trigger
                value="logs"
                className={cn(
                  "px-4 py-3 text-xs font-semibold border-b-2 transition-all flex items-center gap-2",
                  activeTab === "logs" ? "border-[--primary] text-[--foreground]" : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
                )}
              >
                <Terminal size={14} />
                Logs
              </Tabs.Trigger>
            </Tabs.List>
            
            <div className="flex items-center gap-1">
              <button
                onClick={() => { setRightPanel("agent"); setIsSidebarOpen(true); }}
                title="AI Assistant"
                className={cn(
                  "p-1.5 rounded-lg text-xs flex items-center gap-1.5 transition-colors",
                  isSidebarOpen && rightPanel === "agent"
                    ? "bg-[--primary]/15 text-[--primary] font-semibold"
                    : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted]/40"
                )}
              >
                <Sparkles size={14} />
              </button>
              <button
                onClick={() => { setRightPanel("schema"); setIsSidebarOpen(true); }}
                title="Schema Browser"
                className={cn(
                  "p-1.5 rounded-lg transition-colors",
                  isSidebarOpen && rightPanel === "schema"
                    ? "bg-[--muted]/60 text-[--foreground]"
                    : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted]/40"
                )}
              >
                <Database size={14} />
              </button>
              <button
                onClick={() => setIsSidebarOpen(v => !v)}
                className="p-1.5 text-[--muted-foreground] hover:text-[--foreground] transition-colors"
              >
                {isSidebarOpen ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
              </button>
            </div>
          </div>

          <div className="flex-1 relative min-h-0 flex overflow-hidden">
            
            {/* Tab Panels */}
            <div className="flex-1 min-w-0 h-full overflow-hidden relative">
              
              <Tabs.Content value="results" className="h-full overflow-y-auto p-6 focus:outline-none custom-scrollbar">
                {!currentJob ? (
                  <div className="flex flex-col items-center justify-center h-full text-center p-10 opacity-40">
                     <LayoutDashboard size={48} className="mb-4" />
                     <p className="text-sm font-medium">No execution result yet</p>
                     <p className="text-xs mt-1">Run the analysis to generate data visualizations</p>
                  </div>
                ) : (
                  <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
                     <div className="flex items-center gap-3 pb-4 border-b border-[--border]">
                        <div className="w-10 h-10 rounded-xl bg-[--primary]/10 flex items-center justify-center text-[--primary]">
                           <FileText size={20} />
                        </div>
                        <div>
                           <h2 className="text-lg font-bold">{scriptName} Report</h2>
                           <p className="text-xs text-[--muted-foreground]">
                              Completed {new Date(currentJob.finishedAt || currentJob.createdAt).toLocaleString()}
                           </p>
                        </div>
                     </div>
                     <ToolResult name="execute_python" result={currentJob.result || {}} />
                  </div>
                )}
              </Tabs.Content>

              <Tabs.Content value="editor" className="h-full focus:outline-none overflow-hidden">
                <Editor
                  height="100%"
                  defaultLanguage="python"
                  theme="vs-dark"
                  value={code}
                  onChange={(val) => setCode(val || "")}
                  options={{
                    fontSize: 13,
                    fontFamily: "'Fira Code', 'Monaco', monospace",
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                    padding: { top: 16 },
                    lineNumbersMinChars: 3,
                  }}
                />
              </Tabs.Content>

              <Tabs.Content value="logs" className="h-full bg-[--muted]/30 focus:outline-none p-4 overflow-y-auto font-mono text-[11px]">
                 <div className="space-y-1">
                    {(logs ?? []).map((log: any) => (
                      <div key={log._id} className={cn(
                        "break-words",
                        log.level === "error" || log.level === "stderr" ? "text-red-400" :
                        log.level === "warn" ? "text-amber-400" :
                        log.level === "stdout" ? "text-blue-300" :
                        "text-[--muted-foreground]"
                      )}>
                        <span className="opacity-40">[{new Date(log.timestamp).toLocaleTimeString()}]</span>{" "}
                        <span>{log.message}</span>
                      </div>
                    ))}
                    {runningJobId && <div className="text-[--primary] animate-pulse">▋ Executing analysis...</div>}
                    {!logs?.length && !runningJobId && (
                       <p className="text-[--muted-foreground] italic opacity-40">No logs generated for this execution</p>
                    )}
                 </div>
              </Tabs.Content>
            </div>

            {/* Right Panel — Schema or AI Agent */}
            {isSidebarOpen && (
              <div className="w-72 border-l border-[--border] transform transition-all duration-300 animate-in slide-in-from-right-full flex flex-col">
                {rightPanel === "agent" ? (
                  <AgentPanel
                    projectId={projectId as string}
                    onInsertCode={(snippet) => setCode(prev =>
                      prev.trimEnd() + "\n\n" + snippet + "\n"
                    )}
                  />
                ) : (
                  <SchemaBrowser
                    projectId={projectId}
                    onSelect={(name) => setCode(prev => prev + `\n# ${name}`)}
                  />
                )}
              </div>
            )}
          </div>
        </Tabs.Root>
      </div>
    </div>
  );
}
