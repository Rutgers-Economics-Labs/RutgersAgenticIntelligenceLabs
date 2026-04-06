"use client";

import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import { use, useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { agent } from "@/lib/api";

function SettingsContent({ projectSlug }: { projectSlug: string }) {
  const router = useRouter();

  const project = useQuery(api.projects.get, { slug: projectSlug });
  const updateProject = useMutation(api.projects.updateById);
  const deleteProjectConvex = useMutation(api.projects.remove);

  const apiConfigs = useQuery(api.configs.listApis, {})?.filter(c => project?.apiConfigSlugs?.includes(c.slug));
  const pipelineConfigs = useQuery(api.configs.listPipelines, {});
  const pipelineConfig = pipelineConfigs?.find(c => c.slug === project?.pipelineConfigSlug);
  const ontologyConfigs = useQuery(api.configs.listOntologies, {});
  const ontologyConfig = ontologyConfigs?.find(c => c.slug === project?.ontologyConfigSlug);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [model, setModel] = useState("gpt-4o");
  const [githubRepo, setGithubRepo] = useState("");
  const [githubBranch, setGithubBranch] = useState("main");

  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [models, setModels] = useState<any[]>([]);

  useEffect(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description || "");
      setModel(project.agentModel || "gpt-4o");
      setGithubRepo(project.github || "");
      setGithubBranch(project.defaultBranch || "main");
    }
  }, [project]);

  useEffect(() => {
    agent.models().then(res => setModels(res.models)).catch(console.error);
  }, []);

  if (!project) {
    return <div className="flex h-full items-center justify-center"><div className="animate-pulse">Loading settings...</div></div>;
  }

  const handleSaveGeneral = async () => {
    setSaving(true);
    try {
      await updateProject({
        projectId: project._id,
        name,
        description,
        agentModel: model,
        github: githubRepo || undefined,
        defaultBranch: githubBranch || "main",
      });
    } catch (err) {
      console.error(err);
      alert("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("Are you sure you want to reset this project? This will clear all data sources and set status to draft.")) return;
    try {
      await updateProject({
        projectId: project._id,
        apiConfigSlugs: [],
        pipelineConfigSlug: undefined,
        status: "draft",
        lastHydratedAt: undefined,
      });
      alert("Project reset.");
    } catch (err) {
      console.error(err);
      alert("Failed to reset project.");
    }
  };

  const handleDelete = async () => {
    if (!confirm("Are you ABSOLUTELY sure you want to delete this project? This cannot be undone.")) return;
    setDeleting(true);
    try {
      const res = await fetch(`/api/v1/projects/${projectSlug}`, { method: "DELETE" });
      if (!res.ok) {
        await deleteProjectConvex({ slug: projectSlug });
      }
      router.push("/projects");
    } catch (err) {
      console.error(err);
      alert("Failed to delete project");
      setDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-8 max-w-4xl mx-auto w-full p-10 pb-20">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Project Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage project details, agent configuration, and integration settings.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>General Settings</CardTitle>
          <CardDescription>Update your project's basic information.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Project Name</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full h-9 bg-background border border-border rounded-md px-3 text-sm outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Project Slug</label>
            <input
              value={project.slug}
              readOnly
              disabled
              className="w-full h-9 bg-muted border border-border rounded-md px-3 text-sm font-mono opacity-60"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={3}
              className="w-full bg-background border border-border rounded-md p-3 text-sm outline-none focus:border-primary"
            />
          </div>
        </CardContent>
        <CardFooter className="border-t border-border bg-muted/20 px-6 py-4">
          <Button onClick={handleSaveGeneral} disabled={saving || !name}>
            {saving ? "Saving..." : "Save Changes"}
          </Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>GitHub Integration</CardTitle>
          <CardDescription>Link this project to a GitHub repository.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
           <div className="flex items-center gap-4">
              <div className="flex-1">
                <label className="block text-sm font-medium mb-1">GitHub Repository</label>
                <input
                  value={githubRepo}
                  onChange={e => setGithubRepo(e.target.value)}
                  className="w-full h-9 bg-background border border-border rounded-md px-3 text-sm"
                  placeholder="owner/repo"
                />
              </div>
              <div className="w-1/3">
                <label className="block text-sm font-medium mb-1">Default Branch</label>
                <input
                  value={githubBranch}
                  onChange={e => setGithubBranch(e.target.value)}
                  className="w-full h-9 bg-background border border-border rounded-md px-3 text-sm"
                  placeholder="main"
                />
              </div>
            </div>
            <p className="text-[10px] text-muted-foreground">
               Ensure the repository belongs to an account or organization that has authorized the RAIL Platform.
            </p>
        </CardContent>
        <CardFooter className="border-t border-border bg-muted/20 px-6 py-4 flex gap-3">
          <Button onClick={handleSaveGeneral} disabled={saving}>
             {saving ? "Saving..." : "Save Repository Config"}
          </Button>
          {project.github && (
            <Button variant="outline" asChild className="h-9">
               <a href={`/${projectSlug}/github`}>Go to Sync</a>
            </Button>
          )}
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Agent Configuration</CardTitle>
          <CardDescription>Configure how the AI agent operates within this project.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Model Override</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full h-9 bg-background border border-border rounded-md px-3 text-sm outline-none focus:border-primary"
            >
              {models.length > 0 ? (
                models.map(m => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))
              ) : (
                <option value={model}>{model}</option>
              )}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Allowed Actions Checklist</label>
            <div className="space-y-2">
               <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" checked={true} disabled className="rounded border-border bg-background" />
                  <span>Read Ontology</span>
               </label>
               <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" checked={true} disabled className="rounded border-border bg-background" />
                  <span>Query Database</span>
               </label>
               <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" checked={false} disabled className="rounded border-border bg-background" />
                  <span>Execute Pipelines</span>
               </label>
            </div>
            <p className="text-xs text-muted-foreground mt-2 italic">Note: Granular permissions are read-only for now.</p>
          </div>
        </CardContent>
        <CardFooter className="border-t border-border bg-muted/20 px-6 py-4">
          <Button onClick={handleSaveGeneral} disabled={saving}>
            Save Agent Config
          </Button>
        </CardFooter>
      </Card>

      <Card className="border-red-500/20">
        <CardHeader>
          <CardTitle className="text-red-500">Danger Zone</CardTitle>
          <CardDescription>Irreversible actions for this project.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-4 border border-border rounded-lg">
            <div>
              <p className="font-medium text-sm">Reset Project</p>
              <p className="text-xs text-muted-foreground mt-1">Clears all data sources and pipeline link, sets status to draft.</p>
            </div>
            <Button variant="outline" onClick={handleReset} className="text-red-500 hover:text-red-600 hover:bg-red-500/10 border-red-500/20">
              Reset Project
            </Button>
          </div>
          <div className="flex items-center justify-between p-4 border border-border rounded-lg">
            <div>
              <p className="font-medium text-sm">Delete Project</p>
              <p className="text-xs text-muted-foreground mt-1">Permanently deletes this project and all its configurations.</p>
            </div>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? "Deleting..." : "Delete Project"}
            </Button>
          </div>
        </CardContent>
      </Card>

    </div>
  );
}

import { Suspense } from "react";

export default function ProjectSettingsPage({ params }: { params: Promise<{ project: string }> }) {
  const { project: projectSlug } = use(params);

  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center"><div className="animate-pulse">Loading settings...</div></div>}>
      <SettingsContent projectSlug={projectSlug} />
    </Suspense>
  );
}
