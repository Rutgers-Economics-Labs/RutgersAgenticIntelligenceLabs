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
import { useTheme } from "@/components/ThemeProvider";
import {
  Play, Save, Plus, LayoutDashboard, Code, Terminal,
  ChevronRight, ChevronLeft, Loader2, CheckCircle2, AlertCircle,
  Database, FileText, Sparkles, Wand2, History, Clock,
} from "lucide-react";
import { toast } from "sonner";
import Editor from "@monaco-editor/react";
import * as Tabs from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

interface AnalysisWorkspaceProps {
  projectSlug?: string;
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

export function AnalysisWorkspace({ projectSlug }: AnalysisWorkspaceProps) {
  const { theme } = useTheme();
  
  // Fetch project by slug
  const project = useQuery(api.projects.get, projectSlug ? { slug: projectSlug } : "skip");
  const projectId = project?._id;

  const [activeScriptId, setActiveScriptId] = useState<Id<"analysisScripts"> | null>(null);
  const [scriptName, setScriptName] = useState("New Analysis");
  const [code, setCode] = useState(DEFAULT_CODE);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [rightPanel, setRightPanel] = useState<"schema" | "agent">("schema");
  const [activeTab, setActiveTab] = useState("results");
  
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const [lastJobId, setLastJobId] = useState<string | null>(null);

  const saveScript = useMutation(api.analysis.saveScript);
  const runningJob = useQuery(api.executions.get, runningJobId ? { jobId: runningJobId } : "skip") as any;
  const lastJob = useQuery(api.executions.get, lastJobId ? { jobId: lastJobId } : "skip") as any;
  
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
    if (!projectId) return;
    const id = await saveScript({
      id: activeScriptId || undefined,
      projectId,
      name: scriptName,
      code,
    });
    if (!activeScriptId) setActiveScriptId(id as Id<"analysisScripts">);
  };

  const handleRun = async () => {
    if (!projectId) return;
    try {
      setRunningJobId(null);
      setActiveTab("logs");
      // Persist script first so history always has code + lastJobId after a run
      let sid = activeScriptId;
      if (!sid) {
        sid = (await saveScript({
          projectId,
          name: scriptName,
          code,
        })) as Id<"analysisScripts">;
        setActiveScriptId(sid);
      } else {
        await saveScript({ id: sid, projectId, name: scriptName, code });
      }

      const { jobId } = await analysis.runCode(code, String(projectId));
      setRunningJobId(jobId);

      await saveScript({
        id: sid,
        projectId,
        name: scriptName,
        code,
        lastJobId: jobId as any,
      });
    } catch (err) {
      console.error("Failed to run analysis:", err);
      const msg = err instanceof Error ? err.message : "Run failed";
      toast.error(msg);
    }
  };

  // Switch to results when job finishes (success or failure — both have a result payload)
  useEffect(() => {
    if (!runningJobId || !runningJob) return;
    if (runningJob.status === "success" || runningJob.status === "failed") {
      setLastJobId(runningJobId);
      setRunningJobId(null);
      setActiveTab("results");
    }
  }, [runningJob?.status, runningJobId, runningJob]);

  const currentJob = runningJob || lastJob;

  if (!projectSlug) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-20 opacity-50">
        <AlertCircle size={48} className="mb-4" />
        <h3 className="text-lg font-bold">No project context</h3>
        <p className="text-sm">Please select a project to start analysis.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full bg-[--background] transition-all duration-500 overflow-hidden">
      
      {/* Left History Sidebar */}
      <div className="w-[300px] shrink-0 overflow-hidden hidden lg:block bg-[--card]/10 backdrop-blur-3xl border-r border-[--border] shadow-[4px_0_24px_rgba(0,0,0,0.02)]">
        <div className="h-full flex flex-col">
          <div className="p-5 border-b border-[--border] flex items-center justify-between">
            <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-[--muted-foreground] flex items-center gap-2.5">
              <History size={16} className="text-[--primary]" />
              Analysis History
            </h3>
            <button
              onClick={handleNew}
              className="p-1.5 rounded-lg text-[--muted-foreground] hover:text-[--primary] hover:bg-[--primary]/5 transition-all"
              title="Start New Script"
            >
              <Plus size={16} />
            </button>
          </div>
          <div className="flex-1 min-h-0">
            {projectId && (
              <AnalysisHistory
                projectId={projectId}
                onSelect={handleSelectScript}
                selectedId={activeScriptId || undefined}
              />
            )}
          </div>
        </div>
      </div>

      {/* Main Workspace */}
      <div className="flex-1 flex flex-col min-w-0 bg-transparent">
        
        {/* Toolbar */}
        <div className="h-16 border-b border-[--border] flex items-center justify-between px-8 bg-[--background]/40 shadow-sm relative z-20 backdrop-blur-md">
          <div className="flex items-center gap-5 min-w-0">
            <div className="w-10 h-10 rounded-2xl bg-[--primary]/10 flex items-center justify-center text-[--primary] shrink-0 border border-[--primary]/20 shadow-inner">
               <Wand2 size={20} />
            </div>
            <div className="flex flex-col min-w-0">
              <input
                value={scriptName}
                onChange={(e) => setScriptName(e.target.value)}
                className="bg-transparent border-none text-[15px] font-black text-[--foreground] focus:outline-none focus:ring-0 p-0 truncate max-w-[500px]"
                placeholder="Untitled Analysis"
              />
              <div className="flex items-center gap-2 mt-0.5">
                {currentJob?.status === "running" ? (
                  <span className="flex items-center gap-1.5 text-[9px] text-[--primary] font-black uppercase tracking-widest animate-pulse">
                    <Loader2 size={10} className="animate-spin" />
                    Executing...
                  </span>
                ) : currentJob?.status === "failed" ? (
                  <span className="flex items-center gap-1.5 text-[9px] text-red-400 font-black uppercase tracking-widest">
                    <AlertCircle size={10} />
                    Failed
                  </span>
                ) : currentJob?.status === "success" ? (
                  <span className="flex items-center gap-1.5 text-[9px] text-emerald-500 font-black uppercase tracking-widest">
                    <CheckCircle2 size={10} />
                    Ready
                  </span>
                ) : (
                  <span className="text-[9px] text-[--muted-foreground]/60 font-black uppercase tracking-widest">Idle Engine</span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={handleSave}
              className="group flex items-center gap-2.5 px-4 py-2 text-[11px] font-black uppercase tracking-widest text-[--foreground] border border-[--border] bg-[--card]/40 hover:bg-[--muted]/60 rounded-xl transition-all active:scale-95 shadow-sm"
            >
              <Save size={16} className="text-[--muted-foreground] group-hover:text-[--primary] transition-colors" />
              Save
            </button>
            <button
              onClick={handleRun}
              disabled={!!runningJobId || !projectId}
              className="flex items-center gap-2.5 px-6 py-2.5 text-[11px] font-black uppercase tracking-widest text-primary-foreground bg-primary hover:bg-primary/90 rounded-xl shadow-xl shadow-primary/10 transition-all active:scale-95 disabled:opacity-30 disabled:scale-100 disabled:pointer-events-none"
            >
              <Play size={16} fill="currentColor" />
              Run Analysis
            </button>
          </div>
        </div>

        {/* Workspace Content */}
        <Tabs.Root value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
          <div className="px-6 border-b border-[--border] flex items-center justify-between bg-[--muted]/5">
            <Tabs.List className="flex gap-2">
              <Tabs.Trigger
                value="results"
                className={cn(
                  "px-4 py-4 text-sm font-bold border-b-2 transition-all flex items-center gap-2 relative",
                  activeTab === "results" 
                    ? "border-[--primary] text-[--foreground]" 
                    : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
                )}
              >
                <LayoutDashboard size={16} />
                Results
                {activeTab === "results" && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[--primary] shadow-[0_0_8px_var(--primary)]" />}
              </Tabs.Trigger>
              <Tabs.Trigger
                value="editor"
                className={cn(
                  "px-4 py-4 text-sm font-bold border-b-2 transition-all flex items-center gap-2 relative",
                  activeTab === "editor" 
                    ? "border-[--primary] text-[--foreground]" 
                    : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
                )}
              >
                <Code size={16} />
                Researcher IDE
                {activeTab === "editor" && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[--primary] shadow-[0_0_8px_var(--primary)]" />}
              </Tabs.Trigger>
              <Tabs.Trigger
                value="logs"
                className={cn(
                  "px-4 py-4 text-sm font-bold border-b-2 transition-all flex items-center gap-2 relative",
                  activeTab === "logs" 
                    ? "border-[--primary] text-[--foreground]" 
                    : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
                )}
              >
                <Terminal size={16} />
                Logs
                {activeTab === "logs" && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[--primary] shadow-[0_0_8px_var(--primary)]" />}
              </Tabs.Trigger>
            </Tabs.List>
            
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => { setRightPanel("agent"); setIsSidebarOpen(true); }}
                title="AI Assistant"
                className={cn(
                  "p-2 rounded-xl text-xs flex items-center gap-2 transition-all",
                  isSidebarOpen && rightPanel === "agent"
                    ? "bg-[--primary]/15 text-[--primary] font-bold shadow-sm"
                    : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted]/40"
                )}
              >
                <Sparkles size={16} />
                <span className="hidden sm:inline">AI Agent</span>
              </button>
              <button
                onClick={() => { setRightPanel("schema"); setIsSidebarOpen(true); }}
                title="Schema Browser"
                className={cn(
                  "p-2 rounded-xl transition-all",
                  isSidebarOpen && rightPanel === "schema"
                    ? "bg-[--muted]/60 text-[--foreground] shadow-sm"
                    : "text-[--muted-foreground] hover:text-[--foreground] hover:bg-[--muted]/40"
                )}
              >
                <Database size={16} />
              </button>
              <div className="w-px h-6 bg-[--border] mx-1" />
              <button
                onClick={() => setIsSidebarOpen(v => !v)}
                className="p-2 text-[--muted-foreground] hover:text-[--foreground] transition-all hover:bg-[--muted]/40 rounded-xl"
              >
                {isSidebarOpen ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
              </button>
            </div>
          </div>

          <div className="flex-1 relative min-h-0 flex overflow-hidden">
            
            {/* Tab Panels */}
            <div className="flex-1 min-w-0 h-full overflow-hidden relative">
              
              <Tabs.Content value="results" className="h-full overflow-y-auto p-0 focus:outline-none custom-scrollbar">
                {!currentJob ? (
                  <div className="flex flex-col items-center justify-center h-full text-center p-10 space-y-4">
                     <div className="w-20 h-20 rounded-3xl bg-[--muted]/10 flex items-center justify-center text-[--muted-foreground]/30 border border-[--border]">
                        <LayoutDashboard size={40} />
                     </div>
                     <div className="space-y-1">
                        <p className="text-lg font-bold text-[--foreground]">Ready for Analysis</p>
                        <p className="text-sm text-[--muted-foreground] max-w-xs mx-auto">
                           Compose your python script in the IDE tab and run it to generate interactive visualizations and data reports.
                        </p>
                     </div>
                     <button 
                        onClick={() => setActiveTab("editor")}
                        className="px-6 py-2.5 bg-[--primary]/10 text-[--primary] rounded-xl font-bold hover:bg-[--primary]/20 transition-all text-sm"
                     >
                        Open Researcher IDE
                     </button>
                  </div>
                ) : (
                  <div className="animate-in fade-in slide-in-from-bottom-4 duration-700 bg-[--background]/40 h-full">
                     <div className="max-w-5xl mx-auto p-8 space-y-10">
                        <div className="flex items-center justify-between pb-6 border-b border-[--border]">
                           <div className="flex items-center gap-4">
                              <div className="w-12 h-12 rounded-2xl bg-[--primary]/10 flex items-center justify-center text-[--primary] border border-[--primary]/20 shadow-inner">
                                 <FileText size={24} />
                              </div>
                              <div>
                                 <h2 className="text-xl font-extrabold tracking-tight">{scriptName} Report</h2>
                                 <p className="text-xs text-[--muted-foreground] font-medium flex items-center gap-1.5 mt-0.5">
                                    <Clock size={12} />
                                    Completed {new Date(currentJob.finishedAt || currentJob.createdAt).toLocaleString()}
                                 </p>
                              </div>
                           </div>
                           <div
                             className={
                               currentJob.status === "failed"
                                 ? "px-3 py-1 bg-red-500/10 text-red-400 border border-red-500/20 rounded-full text-[10px] font-bold uppercase tracking-widest"
                                 : "px-3 py-1 bg-green-500/10 text-green-500 border border-green-500/20 rounded-full text-[10px] font-bold uppercase tracking-widest"
                             }
                           >
                              {currentJob.status === "failed" ? "Failed" : "Success"}
                           </div>
                        </div>
                        
                        <div className="glass-card rounded-2xl border border-[--border] p-1 shadow-xl bg-[--background]/30 overflow-hidden">
                           <ToolResult
                             name="execute_python"
                             result={
                               currentJob.status === "failed" && currentJob.errorMessage
                                 ? { error: currentJob.errorMessage, stderr: currentJob.errorMessage }
                                 : currentJob.result || {}
                             }
                           />
                        </div>
                     </div>
                  </div>
                )}
              </Tabs.Content>

              <Tabs.Content value="editor" className="h-full focus:outline-none overflow-hidden">
                <Editor
                  height="100%"
                  defaultLanguage="python"
                  theme={theme === "dark" ? "vs-dark" : "light"}
                  value={code}
                  onChange={(val) => setCode(val || "")}
                  options={{
                    fontSize: 14,
                    fontFamily: "'Fira Code', 'JetBrains Mono', 'Monaco', monospace",
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                    padding: { top: 20 },
                    lineNumbersMinChars: 3,
                    cursorSmoothCaretAnimation: "on",
                    smoothScrolling: true,
                    renderLineHighlight: "all",
                    bracketPairColorization: { enabled: true },
                  }}
                />
              </Tabs.Content>

              <Tabs.Content value="logs" className="h-full bg-[--muted]/10 focus:outline-none p-6 overflow-y-auto font-mono text-[12px] custom-scrollbar">
                 <div className="space-y-1.5 max-w-4xl mx-auto">
                    <div className="flex items-center gap-2 mb-4 text-[--muted-foreground]/60 border-b border-[--border] pb-2 font-bold uppercase tracking-tighter text-[10px]">
                       <Terminal size={12} />
                       Runtime Logs
                    </div>
                    {(logs ?? []).map((log: any) => (
                      <div key={log._id} className={cn(
                        "break-words py-0.5 border-l-2 pl-3 transition-colors hover:bg-[--muted]/20 rounded-r",
                        log.level === "error" || log.level === "stderr" ? "text-red-400 border-red-500/50 bg-red-500/5" :
                        log.level === "warn" ? "text-amber-400 border-amber-500/50 bg-amber-500/5" :
                        log.level === "stdout" ? "text-blue-300 border-blue-500/50 bg-blue-500/5" :
                        "text-[--muted-foreground] border-[--border]"
                      )}>
                        <span className="opacity-40 font-mono italic text-[10px]">[{new Date(log.timestamp).toLocaleTimeString()}]</span>{" "}
                        <span className="leading-relaxed">{log.message}</span>
                      </div>
                    ))}
                    {runningJobId && (
                       <div className="flex items-center gap-3 text-[--primary] font-bold mt-4 animate-pulse">
                          <div className="w-2 h-4 bg-[--primary]" />
                          Executing analysis engine...
                       </div>
                    )}
                    {!logs?.length && !runningJobId && (
                       <div className="flex flex-col items-center justify-center py-20 opacity-30 text-center space-y-2">
                          <Terminal size={32} />
                          <p className="text-sm font-medium">Listening for events...</p>
                       </div>
                    )}
                 </div>
              </Tabs.Content>
            </div>

            {/* Right Panel — Schema or AI Agent */}
            {isSidebarOpen && (
              <div className="w-80 border-l border-[--border] bg-[--muted]/5 backdrop-blur-md transform transition-all duration-300 animate-in slide-in-from-right-full flex flex-col shadow-2xl relative z-10">
                {rightPanel === "agent" ? (
                  <AgentPanel
                    projectId={String(projectId)}
                    onInsertCode={(snippet) => {
                      setCode(prev => prev.trimEnd() + "\n\n" + snippet + "\n");
                      setActiveTab("editor");
                    }}
                  />
                ) : (
                  <SchemaBrowser
                    projectId={String(projectId)}
                    onSelect={(name) => setCode(prev => prev + (prev.endsWith("\n") ? "" : "\n") + `# Reference: ${name}\n`)}
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
