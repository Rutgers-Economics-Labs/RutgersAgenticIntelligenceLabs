"use client";

import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { use, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Github, GitPullRequest, GitMerge, CheckCircle2, AlertCircle, ExternalLink, RefreshCw } from "lucide-react";
import { github } from "@/lib/api";
import { formatDistanceToNow } from "date-fns";
import { Suspense } from "react";

function GitHubContent({ projectSlug }: { projectSlug: string }) {
  const project = useQuery(api.projects.get, { slug: projectSlug });
  
  const apiConfigs = useQuery(api.configs.listApis, {})?.filter(c => project?.apiConfigSlugs?.includes(c.slug));
  const pipelineConfigs = useQuery(api.configs.listPipelines, {});
  const pipelineConfig = pipelineConfigs?.find(c => c.slug === project?.pipelineConfigSlug);
  const ontologyConfigs = useQuery(api.configs.listOntologies, {});
  const ontologyConfig = ontologyConfigs?.find(c => c.slug === project?.ontologyConfigSlug);

  const [publishing, setPublishing] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  if (!project) {
    return <div className="flex h-full items-center justify-center"><div className="animate-pulse">Loading GitHub...</div></div>;
  }

  const isLinked = !!project.github;

  const handlePublish = async () => {
    const files = [
      ...(apiConfigs || []).map((c) => ({
        path: `configs/apis/${c.slug}.yaml`,
        content: c.content,
      })),
      ...(pipelineConfig ? [{
        path: `configs/pipelines/${pipelineConfig.slug}.yaml`,
        content: pipelineConfig.content,
      }] : []),
      ...(ontologyConfig ? [{
        path: `configs/ontology/${ontologyConfig.slug}.yaml`,
        content: ontologyConfig.content,
      }] : []),
    ].filter(Boolean);

    if (files.length === 0) {
      alert("No configurations found to publish.");
      return;
    }

    setPublishing(true);
    setLogs(prev => [...prev, `Preparing ${files.length} files for synchronization...`]);

    try {
      setLogs(prev => [...prev, `Connecting to repository: ${project.github}...`]);
      const res = await github.publish({
        project_slug: project.slug,
        files,
        commit_message: "chore: sync project configurations [automated]",
      });
      setLogs(prev => [...prev, `Successfully published ${res.published} files.`]);
      setLogs(prev => [...prev, `Branch: ${project.defaultBranch || "main"}`]);
      alert(`Synchronized ${res.published} files to GitHub.`);
    } catch (err: any) {
      console.error(err);
      setLogs(prev => [...prev, `Error: ${err.message || String(err)}`]);
      alert(`Sync failed: ${err.message || String(err)}`);
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="flex flex-col gap-8 max-w-5xl mx-auto w-full p-10 pb-20">
      <div className="flex justify-between items-end">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Github className="w-5 h-5 text-[--primary]" />
            <h1 className="text-2xl font-bold tracking-tight uppercase">GitHub Integration</h1>
          </div>
          <p className="text-sm text-muted-foreground">Synchronize your project configurations with a version-controlled repository.</p>
        </div>
        {isLinked && (
          <Button variant="outline" className="h-9 gap-2 border-[--primary]/20 hover:bg-[--primary]/5" asChild>
            <a href={`https://github.com/${project.github}`} target="_blank" rel="noreferrer">
              View Repository <ExternalLink size={14} />
            </a>
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card className="bg-[--card]/40 backdrop-blur-sm border-[--border] shadow-lg">
            <CardHeader>
              <div className="flex justify-between items-start">
                <div>
                  <CardTitle className="text-lg">Repository Status</CardTitle>
                  <CardDescription>Connection between project and GitHub.</CardDescription>
                </div>
                <Badge className={isLinked ? "bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/10 border-emerald-500/20" : "bg-slate-500/10 text-slate-500 hover:bg-slate-500/10"}>
                  {isLinked ? "Connected" : "Disconnected"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              {isLinked ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-4 p-4 rounded-xl bg-white/5 border border-white/10">
                    <div className="w-10 h-10 rounded-lg bg-black flex items-center justify-center border border-white/10">
                      <Github size={20} />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">{project.github}</p>
                      <p className="text-[10px] text-muted-foreground font-mono">Branch: {project.defaultBranch || "main"}</p>
                    </div>
                  </div>
                  <div className="pt-2">
                    <p className="text-xs font-medium mb-3">Included Files:</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {apiConfigs?.map(c => (
                        <div key={c._id} className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted/30 border border-border text-[10px] font-mono">
                           <CheckCircle2 size={10} className="text-emerald-500" />
                           <span className="truncate">configs/apis/{c.slug}.yaml</span>
                        </div>
                      ))}
                      {pipelineConfig && (
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted/30 border border-border text-[10px] font-mono">
                           <CheckCircle2 size={10} className="text-emerald-500" />
                           <span>configs/pipelines/{pipelineConfig.slug}.yaml</span>
                        </div>
                      )}
                      {ontologyConfig && (
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted/30 border border-border text-[10px] font-mono">
                           <CheckCircle2 size={10} className="text-emerald-500" />
                           <span>configs/ontology/{ontologyConfig.slug}.yaml</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  <AlertCircle className="w-12 h-12 text-muted-foreground mb-4 opacity-20" />
                  <p className="text-sm font-medium mb-1">No repository linked</p>
                  <p className="text-xs text-muted-foreground max-w-[300px] mb-6">Link a GitHub repository in project settings to enable version-controlled configuration sync.</p>
                  <Button variant="outline" className="h-8" asChild>
                    <a href={`/${projectSlug}/settings`}>Go to Settings</a>
                  </Button>
                </div>
              )}
            </CardContent>
            {isLinked && (
              <CardFooter className="bg-white/5 border-t border-white/5 flex justify-between items-center py-4">
                <p className="text-[10px] text-muted-foreground">Last sync: {project.lastHydratedAt ? formatDistanceToNow(project.lastHydratedAt, { addSuffix: true }) : 'Never'}</p>
                <Button onClick={handlePublish} disabled={publishing} size="sm" className="gap-2">
                  <RefreshCw size={14} className={publishing ? "animate-spin" : ""} />
                  {publishing ? "Syncing..." : "Sync to GitHub"}
                </Button>
              </CardFooter>
            )}
          </Card>

          <Card className="bg-black/20 border-[--border]">
            <CardHeader className="py-4">
              <CardTitle className="text-sm font-bold flex items-center gap-2 uppercase tracking-wider opacity-60">
                <GitPullRequest size={14} />
                Recent Activity
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                 {logs.length > 0 ? (
                   logs.slice().reverse().map((log, i) => (
                     <div key={i} className="flex items-start gap-2 text-[10px] font-mono">
                        <span className="text-muted-foreground shrink-0">[{new Date().toLocaleTimeString()}]</span>
                        <span className={log.startsWith('Error') ? "text-red-400" : log.startsWith('Success') ? "text-emerald-400" : "text-foreground opacity-80"}>
                          {log}
                        </span>
                     </div>
                   ))
                 ) : (
                   <p className="text-[10px] text-muted-foreground italic">No sync activity in this session.</p>
                 )}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="bg-gradient-to-br from-[--primary]/10 to-[--accent]/10 border-[--primary]/20">
            <CardHeader>
              <CardTitle className="text-sm">Why Version Control?</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex gap-3">
                  <div className="mt-1"><CheckCircle2 size={14} className="text-[--primary]" /></div>
                  <p className="text-xs leading-relaxed"><span className="font-semibold">Review:</span> Peer review changes to your ontology and data connectors.</p>
                </div>
                <div className="flex gap-3">
                  <div className="mt-1"><CheckCircle2 size={14} className="text-[--primary]" /></div>
                  <p className="text-xs leading-relaxed"><span className="font-semibold">Rollback:</span> Instantly revert to any previous version of your configuration.</p>
                </div>
                <div className="flex gap-3">
                  <div className="mt-1"><CheckCircle2 size={14} className="text-[--primary]" /></div>
                  <p className="text-xs leading-relaxed"><span className="font-semibold">Collaboration:</span> Multiple team members can work on the same project via PRs.</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-[--border] bg-[--card]/50">
             <CardHeader className="py-4">
                <CardTitle className="text-xs font-bold uppercase opacity-50">Experimental</CardTitle>
             </CardHeader>
             <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                   <div className="flex items-center gap-2">
                      <GitMerge size={16} className="text-blue-400" />
                      <span className="text-xs font-medium">Auto-Sync</span>
                   </div>
                   <div className="w-8 h-4 rounded-full bg-slate-800 relative cursor-not-allowed opacity-50">
                      <div className="absolute left-0.5 top-0.5 w-3 h-3 rounded-full bg-slate-600" />
                   </div>
                </div>
                <p className="text-[10px] text-muted-foreground">Automatically publish changes to GitHub on every save. (Coming Soon)</p>
             </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default function ProjectGitHubPage({ params }: { params: Promise<{ project: string }> }) {
  const { project: projectSlug } = use(params);

  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center"><div className="animate-pulse text-[--primary]">Initializing Sync Engine...</div></div>}>
      <GitHubContent projectSlug={projectSlug} />
    </Suspense>
  );
}
