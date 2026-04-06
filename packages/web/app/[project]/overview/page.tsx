"use client";

import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { use, Suspense, useState } from "react";
import useSWR, { mutate } from "swr";
import { ontology, sql, jobs, isSyncRequiredError, projects } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { formatDistanceToNow } from "date-fns";
import { 
  CheckCircle2, Circle, ArrowUpRight, 
  Activity, Database, Layers, GitBranch, 
  Search, Bot, Sparkles, ChevronRight, Link2, Loader2
} from "lucide-react";
import Link from "next/link";

const fetcher = (fn: any) => fn();

function StatCard({ title, value, subtext, icon: Icon, color }: any) {
  return (
    <Card className="bg-[--card]/50 backdrop-blur-sm border-[--border] hover:border-[--primary]/30 transition-all group overflow-hidden relative">
      <div className={`absolute top-0 right-0 w-24 h-24 -mr-8 -mt-8 rounded-full opacity-[0.03] group-hover:opacity-[0.06] transition-opacity`} style={{ backgroundColor: color }} />
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground opacity-70">
        <CardTitle className="text-[10px] uppercase tracking-widest">{title}</CardTitle>
        <Icon size={14} style={{ color }} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold tracking-tight mb-1">{value}</div>
        <p className="text-[10px] text-muted-foreground font-medium">{subtext}</p>
      </CardContent>
    </Card>
  );
}

function OverviewContent({ projectSlug }: { projectSlug: string }) {
  const project = useQuery(api.projects.get, { slug: projectSlug });
  const jobsList = useQuery(api.jobs.listByProject, { projectSlug, limit: 3 });
  const [isRunning, setIsRunning] = useState(false);
  const [linkingArtifacts, setLinkingArtifacts] = useState(false);

  const handleLinkArtifacts = async () => {
    try {
      setLinkingArtifacts(true);
      await projects.registerArtifacts(projectSlug);
      toast.success("Ontology artifacts linked — refreshing stats");
      await mutate(["ontology", "classes", projectSlug]);
      await mutate(["sql", "query", projectSlug, "total_instances"]);
      await mutate(["jobs", "list", projectSlug]);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Could not link artifacts");
    } finally {
      setLinkingArtifacts(false);
    }
  };

  const handleRunPipeline = async () => {
    if (!project?.pipelineConfigSlug) {
      toast.error("No pipeline configuration found for this project.");
      return;
    }

    try {
      setIsRunning(true);
      const res = await jobs.trigger(project.pipelineConfigSlug, projectSlug);
      toast.success("Pipeline job triggered successfully", {
        description: `Job ID: ${res.jobId}`,
      });
    } catch (err: any) {
      toast.error("Failed to trigger pipeline", {
        description: err.message,
      });
    } finally {
      setIsRunning(false);
    }
  };

  const { data: classesResult, error: classesError } = useSWR(
    projectSlug ? ["ontology", "classes", projectSlug] : null,
    () => ontology.classes(projectSlug),
    {
      shouldRetryOnError: (err) => !isSyncRequiredError(err),
      revalidateOnFocus: false,
    }
  );
  
  const isSyncRequired = isSyncRequiredError(classesError);
  
  // Track last 5 jobs to see if one is currently active
  const { data: latestJobs } = useSWR(
    projectSlug ? ["jobs", "list", projectSlug] : null,
    () => jobs.list(projectSlug, 5),
    { refreshInterval: 2000 }
  );

  const activeJob = Array.isArray(latestJobs) 
    ? latestJobs.find(j => j.status === "running" || j.status === "queued")
    : null;
  const lastJob = Array.isArray(latestJobs) ? latestJobs[0] : null;

  const classesCount = classesResult?.length || 0;

  const { data: sqlResult } = useSWR(
    projectSlug && !isSyncRequired ? ["sql", "query", projectSlug, "total_instances"] : null,
    () => sql.query("SELECT SUM(estimated_size) as count FROM duckdb_tables", projectSlug)
  );

  const chartData = classesResult?.slice(0, 8).map((c: any, i: number) => ({
    name: c.name || "Unknown",
    instances: c.instanceCount || 0,
    color: [`var(--primary)`, `#8b5cf6`, `#ec4899`, `#f59e0b`, `#10b981`][i % 5]
  })) || [];

  if (!project) {
    return <div className="flex h-screen items-center justify-center"><div className="animate-pulse text-[--primary]">Loading session...</div></div>;
  }

  const steps = [
    { label: "Project Created", completed: true, href: null },
    { label: "Ontology Configured", completed: !!project.ontologyConfigSlug, href: `/${projectSlug}/settings` },
    { label: "Data Sources Attached", completed: project.apiConfigSlugs.length > 0, href: `/${projectSlug}/sources` },
    { label: "Pipeline Configured", completed: !!project.pipelineConfigSlug, href: `/${projectSlug}/pipelines` },
    { label: "Initial Hydration", completed: project.status === "hydrated", href: `/${projectSlug}/jobs` },
  ];

  return (
    <div className="flex flex-col gap-8 max-w-6xl mx-auto w-full pb-20 p-8 lg:p-12">
      {/* Header Section */}
      <div className="flex justify-between items-start pt-4">
        <div>
           <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-extrabold tracking-tight text-[--foreground]">{project.name}</h1>
              <Badge className={cn("px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider", 
                project.status === "hydrated" ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" : 
                project.status === "ready" ? "bg-blue-500/10 text-blue-500 border-blue-500/20" : "bg-slate-500/10 text-slate-500 border-slate-500/20"
              )}>
                {project.status}
              </Badge>
              {isSyncRequired && (
                <Badge variant="outline" className="bg-amber-500/10 text-amber-500 border-amber-500/20 text-[10px] font-bold uppercase tracking-wider">
                  Sync Required
                </Badge>
              )}
           </div>
           <p className="text-sm text-muted-foreground flex items-center gap-2">
             <Layers size={14} className="opacity-50" />
             {project.description || "Experimental Research Project"}
           </p>
        </div>
        <div className="flex gap-3 flex-wrap">
           <Button variant="outline" className="h-9 gap-2 border-[--border]" asChild>
             <Link href={`/${projectSlug}/agent`}>
                <Bot size={14} /> AI Workspace
             </Link>
           </Button>
           {isSyncRequired && (
             <Button
               variant="outline"
               className="h-9 gap-2 border-emerald-500/40 text-emerald-600 hover:bg-emerald-500/10"
               onClick={handleLinkArtifacts}
               disabled={linkingArtifacts}
             >
               {linkingArtifacts ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
               Link latest job
             </Button>
           )}
           <Button 
             className={cn("h-9 gap-2", isSyncRequired && !activeJob ? "bg-amber-600 hover:bg-amber-500 animate-pulse shadow-lg shadow-amber-600/20" : "bg-[--primary] hover:bg-[--accent]")}
             onClick={handleRunPipeline}
             disabled={isRunning || !project.pipelineConfigSlug || !!activeJob}
           >
              <Activity size={14} className={isRunning || activeJob ? "animate-spin" : ""} />
              {isRunning || activeJob ? (activeJob ? "Syncing..." : "Queueing...") : isSyncRequired ? "Run pipeline" : "Run Pipeline"}
           </Button>
        </div>
      </div>

      {isSyncRequired && (
        <Card className="border-amber-500/20 bg-amber-500/5 shadow-none">
          <CardContent className="py-4 flex items-center gap-4 text-amber-600 text-sm">
             <Sparkles size={20} className={cn("shrink-0", activeJob ? "animate-spin-slow" : "animate-pulse")} />
             <div>
                <p className="font-bold">
                  {project.status === "hydrated"
                    ? "API can’t load ontology artifacts yet"
                    : "Initial activation required"}
                </p>
                {activeJob ? (
                  <p className="opacity-70 text-xs">
                    Sync currently in progress on node <code className="bg-amber-500/10 px-1 rounded font-mono">{activeJob.machine || "unknown"}</code>. Features will unlock once complete.
                  </p>
                ) : project.status === "hydrated" ? (
                  <p className="opacity-70 text-xs">
                    Convex shows this project as hydrated, but the FastAPI server has no active ontology DB path (or the files aren’t on this machine). Run hydration again from{" "}
                    <Link className="underline font-medium text-amber-700 dark:text-amber-400" href={`/${projectSlug}/jobs`}>Jobs</Link>
                    , or ensure artifact paths in Convex match files the API can read (e.g. same machine as <code className="bg-amber-500/10 px-1 rounded font-mono">/tmp/rail_artifacts/…</code>).
                  </p>
                ) : (
                  <p className="opacity-70 text-xs">
                    Pipeline hydration must finish and register artifacts with the API. Use{" "}
                    <strong className="text-[--foreground]">Start Initial Sync</strong> to run the project pipeline, or open{" "}
                    <Link className="underline font-medium" href={`/${projectSlug}/jobs`}>Jobs</Link>.
                  </p>
                )}
             </div>
          </CardContent>
        </Card>
      )}

      {lastJob && (lastJob.status === "success" || lastJob.status === "completed") && (
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 w-fit">
           <CheckCircle2 size={12} className="text-emerald-500" />
           <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-tight">
             Last synced on <span className="underline">{lastJob.machine || "unknown"}</span> ({formatDistanceToNow(lastJob.createdAt, { addSuffix: true })})
           </span>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          title="Individuals" 
          value={isSyncRequired ? "—" : (sqlResult?.rows?.[0]?.count || 0).toLocaleString()} 
          subtext={isSyncRequired ? "Knowledge base empty" : "Total knowledge graph nodes"} 
          icon={Database}
          color={isSyncRequired ? "var(--muted-foreground)" : "var(--primary)"}
        />
        <StatCard 
          title="Ontology Classes" 
          value={isSyncRequired ? "—" : classesCount} 
          subtext={isSyncRequired ? "Schema not yet loaded" : "Entity types defined"} 
          icon={Layers}
          color={isSyncRequired ? "var(--muted-foreground)" : "#8b5cf6"}
        />
        <StatCard 
          title="Data Sources" 
          value={project.apiConfigSlugs.length} 
          subtext="Active ingest streams" 
          icon={GitBranch}
          color="#10b981"
        />
        <StatCard 
          title="Last Sync" 
          value={project.lastHydratedAt ? formatDistanceToNow(project.lastHydratedAt, { addSuffix: true }) : "Never"} 
          subtext="Previous pipeline run" 
          icon={Activity}
          color="#f59e0b"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Progress & Jobs */}
        <div className="lg:col-span-2 space-y-8">
          {/* Getting Started */}
          <Card className="bg-[--card]/30 border-[--border] shadow-xl overflow-hidden">
            <CardHeader className="bg-white/[0.02] border-b border-white/[0.05]">
              <CardTitle className="text-sm font-bold flex items-center gap-2 uppercase tracking-tight">
                <Sparkles size={16} className="text-[--primary]" />
                Project Readiness
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {steps.map((step, i) => (
                  <div key={i} className={cn("p-4 rounded-xl border transition-all flex items-center justify-between group/step", 
                    step.completed ? "bg-emerald-500/5 border-emerald-500/10" : "bg-white/5 border-white/5 opacity-60 hover:opacity-100"
                  )}>
                    <div className="flex items-center gap-3">
                      {step.completed ? (
                        <CheckCircle2 size={18} className="text-emerald-500" />
                      ) : (
                        <Circle size={18} className="text-muted-foreground opacity-20" />
                      )}
                      <div>
                        <p className={cn("text-xs font-semibold", step.completed ? "text-emerald-500/80" : "text-foreground")}>
                          {step.label}
                        </p>
                      </div>
                    </div>
                    {step.href && !step.completed && (
                       <Link href={step.href} className="text-[10px] font-bold text-[--primary] uppercase tracking-wider flex items-center gap-1 hover:underline">
                         Setup <ChevronRight size={10} />
                       </Link>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Activity */}
          <Card className="bg-[--card]/30 border-[--border] shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between py-4">
              <CardTitle className="text-sm font-bold uppercase tracking-tight">Recent Pipeline Runs</CardTitle>
              <Link href={`/${projectSlug}/jobs`} className="text-[10px] font-bold text-muted-foreground hover:text-[--primary] flex items-center gap-1">
                View all <ArrowUpRight size={12} />
              </Link>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {jobsList && jobsList.length > 0 ? (
                  jobsList.map((job: any) => (
                    <div key={job._id} className="flex items-center justify-between p-3 rounded-lg bg-white/5 border border-white/5 hover:border-white/10 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className={cn("w-1.5 h-1.5 rounded-full",
                          job.status === "success" ? "bg-emerald-500" :
                          job.status === "failed" ? "bg-red-500" : "bg-blue-400 animate-pulse"
                        )} />
                        <div>
                          <p className="text-xs font-semibold font-mono">{job.pipelineSlug}</p>
                          <p className="text-[10px] text-muted-foreground">
                            {formatDistanceToNow(job.createdAt, { addSuffix: true })}
                          </p>
                        </div>
                      </div>
                      <Badge variant="outline" className={cn("text-[10px] font-mono",
                        job.status === "success" ? "border-emerald-500/20 text-emerald-500" :
                        job.status === "failed" ? "border-red-500/20 text-red-500" : "border-blue-500/20 text-blue-500"
                      )}>
                        {job.status}
                      </Badge>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-10 opacity-30">
                    <Activity size={32} className="mx-auto mb-2" />
                    <p className="text-xs">No activity recorded yet.</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Schema breakdown */}
        <div className="space-y-8">
           <Card className="bg-[--card]/30 border-[--border] h-full shadow-xl">
             <CardHeader className="py-4">
                <CardTitle className="text-sm font-bold uppercase tracking-tight">Ontology Distribution</CardTitle>
                <CardDescription className="text-[10px]">Frequency of major classes</CardDescription>
             </CardHeader>
             <CardContent>
                <div className="h-[400px] w-full">
                  {chartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={chartData} layout="vertical" margin={{ left: -10, right: 30 }}>
                        <XAxis type="number" hide />
                        <YAxis 
                          dataKey="name" 
                          type="category" 
                          stroke="var(--muted-foreground)" 
                          fontSize={10} 
                          tickLine={false} 
                          axisLine={false} 
                          width={100} 
                        />
                        <Tooltip 
                          cursor={{ fill: 'rgba(255,255,255,0.05)' }} 
                          contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', borderRadius: '8px', fontSize: '10px' }}
                        />
                        <Bar dataKey="instances" radius={[0, 4, 4, 0]} barSize={20}>
                           {chartData.map((entry: any, index: number) => (
                             <Cell key={`cell-${index}`} fill={entry.color} fillOpacity={0.8} />
                           ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full opacity-20">
                       <Layers size={48} className="mb-2" />
                       <p className="text-xs">No analysis data</p>
                    </div>
                  )}
                </div>
             </CardContent>
             <CardFooter className="pt-0 pb-6 flex justify-center">
                <Button variant="ghost" size="sm" className="text-[10px] font-bold text-muted-foreground hover:bg-white/5" asChild>
                   <Link href={`/${projectSlug}/ontology/graph`}>Open Graph Explorer <ArrowUpRight size={10} className="ml-1" /></Link>
                </Button>
             </CardFooter>
           </Card>
        </div>
      </div>
    </div>
  );
}

// Helper function for class names
function cn(...classes: any[]) {
  return classes.filter(Boolean).join(' ');
}

export default function ProjectOverviewPage({ params }: { params: Promise<{ project: string }> }) {
  const { project: projectSlug } = use(params);

  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center"><div className="animate-pulse text-[--primary]">Synchronizing context...</div></div>}>
      <OverviewContent projectSlug={projectSlug} />
    </Suspense>
  );
}