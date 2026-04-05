"use client";

import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X, ChevronDown, ChevronUp } from "lucide-react";
import { configs } from "@/lib/api";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";

interface ConnectorCardProps {
  slug: string;
  name: string;
  description: string;
  version: string;
  tags: string[];
  usageCount?: number;
  content: string;
}

export function ConnectorCard({ slug, name, description, version, tags, usageCount, content }: ConnectorCardProps) {
  const [showYaml, setShowYaml] = useState(false);
  const [showFork, setShowFork] = useState(false);

  const projects = useQuery(api.projects.list, {});
  const [forkName, setForkName] = useState("");
  const [forkSlug, setForkSlug] = useState(`${slug}-fork`);
  const [forkProject, setForkProject] = useState("");
  const [forking, setForking] = useState(false);
  const [forkError, setForkError] = useState("");
  const [forkSuccess, setForkSuccess] = useState(false);

  async function handleFork(e: React.FormEvent) {
    e.preventDefault();
    if (!forkName || !forkSlug) return;

    setForking(true);
    setForkError("");
    setForkSuccess(false);

    try {
      const templateYaml = `extends: ${slug}\nparams: {}\n`;

      // Pass the selected project correctly to the API?
      // Current configs.create signature is: create(type, body)
      // Actually, if projects are scoped by API key/URL parameter or context, we might not need to send project ID in body. Let's check configs.ts
      await configs.create("apis", {
        name: forkName,
        slug: forkSlug,
        content: templateYaml,
        isPublic: false,
        tags: []
      }, forkProject);
      setForkSuccess(true);
      setTimeout(() => setShowFork(false), 2000);
    } catch (err: unknown) {
      setForkError(err instanceof Error ? err.message : "Failed to use template");
    } finally {
      setForking(false);
    }
  }

  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden flex flex-col">
      <div className="p-5 flex-1">
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-lg">{name}</h3>
            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-mono text-muted-foreground border border-border">
              v{version}
            </span>
          </div>
          {usageCount !== undefined && usageCount > 0 && (
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
              {usageCount} uses
            </span>
          )}
        </div>

        <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
          {description}
        </p>

        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {tags.map(t => (
              <span key={t} className="rounded-full border border-border bg-white/5 px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      {showYaml && (
        <div className="border-t border-border bg-muted p-4 text-xs font-mono overflow-x-auto">
          <pre className="text-muted-foreground">{content}</pre>
        </div>
      )}

      <div className="p-4 border-t border-border bg-muted/30 flex items-center justify-between">
        <button
          onClick={() => setShowYaml(!showYaml)}
          className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
        >
          {showYaml ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {showYaml ? "Hide YAML" : "View YAML"}
        </button>

        <Dialog.Root open={showFork} onOpenChange={(open) => {
          setShowFork(open);
          if (open) {
            setForkName(`My ${name}`);
            setForkSuccess(false);
            setForkError("");
            const initialProject = (projects && projects.length > 0 && !forkProject) ? projects[0]._id : forkProject;
            if (initialProject) setForkProject(initialProject);

            const pName = projects?.find(p => p._id === initialProject)?.name || "app";
            const pSuffix = pName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
            setForkSlug(`${slug}-${pSuffix}`);
          }
        }}>
          <Dialog.Trigger asChild>
            <button className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-[#0d1117] hover:opacity-90 transition-opacity">
              Use Template
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 bg-black/60 z-50 backdrop-blur-sm" />
            <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl z-50 p-6">
              <div className="flex items-center justify-between mb-5">
                <Dialog.Title className="text-lg font-semibold">Use Connector</Dialog.Title>
                <Dialog.Close className="text-muted-foreground hover:text-foreground">
                  <X size={18} />
                </Dialog.Close>
              </div>

              {forkSuccess ? (
                <div className="py-8 text-center space-y-4">
                  <div className="text-emerald-400 font-medium">Config created successfully!</div>
                  <a href={`/configs?projectId=${forkProject}`} className="text-sm text-[--primary] hover:underline block">
                    View in Configs →
                  </a>
                </div>
              ) : (
                <form onSubmit={handleFork} className="space-y-4">
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Project</label>
                    <select
                      value={forkProject}
                      onChange={(e) => {
                        const newProjectId = e.target.value;
                        setForkProject(newProjectId);
                        const pName = projects?.find(p => p._id === newProjectId)?.name || "app";
                        const pSuffix = pName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
                        setForkSlug(`${slug}-${pSuffix}`);
                      }}
                      className="w-full rounded-xl border border-border bg-muted px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                      required
                    >
                      <option value="" disabled>Select a project</option>
                      {projects?.map((p) => (
                        <option key={p._id} value={p._id}>{p.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Config Name</label>
                    <input
                      value={forkName}
                      onChange={(e) => {
                        setForkName(e.target.value);
                        setForkSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));
                      }}
                      className="w-full rounded-xl border border-border bg-muted px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Config Slug</label>
                    <input
                      value={forkSlug}
                      onChange={(e) => setForkSlug(e.target.value)}
                      className="w-full rounded-xl border border-border bg-muted px-3 py-2 text-sm text-foreground outline-none focus:border-primary font-mono text-xs"
                      required
                    />
                  </div>

                  {forkError && (
                    <div className="text-sm text-red-400 bg-red-400/10 p-2 rounded-lg border border-red-400/20">
                      {forkError}
                    </div>
                  )}

                  <div className="pt-2 flex justify-end gap-3">
                    <Dialog.Close type="button" className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground">
                      Cancel
                    </Dialog.Close>
                    <button
                      type="submit"
                      disabled={forking}
                      className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-[#0d1117] hover:opacity-90 disabled:opacity-50"
                    >
                      {forking ? "Creating..." : "Create Config"}
                    </button>
                  </div>
                </form>
              )}
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
    </div>
  );
}
