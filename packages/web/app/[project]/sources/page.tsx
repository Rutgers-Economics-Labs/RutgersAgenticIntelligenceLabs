"use client";

import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import { use, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Plus, Database, ChevronRight, Search } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import { Suspense } from "react";

function SourcesContent({ projectSlug }: { projectSlug: string }) {
  const project = useQuery(api.projects.get, { slug: projectSlug });
  const templates = useQuery(api.connectors.list, {});
  const apiConfigs = useQuery(api.configs.listApis, {});
  const updateProject = useMutation(api.projects.updateById);
  const createApi = useMutation(api.configs.createApi);

  const [selectedTemplate, setSelectedTemplate] = useState<any | null>(null);
  const [showEditor, setShowEditor] = useState(false);
  const [saving, setSaving] = useState(false);

  // Customization state for adding
  const [newName, setNewName] = useState("");
  const [newSlug, setNewSlug] = useState("");

  if (!project || templates === undefined || apiConfigs === undefined) {
    return <div className="flex h-full items-center justify-center"><div className="animate-pulse">Loading sources...</div></div>;
  }

  const activeSources = apiConfigs.filter(c => project.apiConfigSlugs.includes(c.slug));

  const handleAddSource = async () => {
    if (!selectedTemplate || !newName || !newSlug) return;
    setSaving(true);
    try {
      // 1. Create a new API config that references the template
      const content = `extends: ${selectedTemplate.slug}\nparams: {}\n`;

      await createApi({
        name: newName,
        slug: newSlug,
        content: content,
        parsedSpec: { extends: selectedTemplate.slug, params: {} },
        sourceType: "connector",
        isPublic: false,
        tags: ["project-source", selectedTemplate.slug],
      });

      // 2. Attach it to the project
      await updateProject({
        projectId: project._id,
        apiConfigSlugs: [...project.apiConfigSlugs, newSlug],
      });

      setSelectedTemplate(null);
    } catch (err) {
      console.error(err);
      alert("Failed to add source");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-full gap-6 max-w-7xl mx-auto w-full pb-10">
      {/* Left Panel: Active Data Sources */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-border pr-6">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Data Sources</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Active connections feeding data to this project.
            </p>
          </div>
        </div>

        <div className="space-y-4 flex-1 overflow-y-auto">
          {activeSources.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 border border-dashed border-border rounded-lg bg-muted/10 text-center">
              <Database className="w-8 h-8 text-muted-foreground mb-3" />
              <p className="text-sm font-medium">No active sources</p>
              <p className="text-xs text-muted-foreground mt-1 mb-4 max-w-[250px]">
                Add a data source from the connector gallery to start ingesting data.
              </p>
            </div>
          ) : (
            activeSources.map((source) => (
              <Card key={source._id}>
                <CardHeader className="py-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <CardTitle className="text-base font-semibold">{source.name}</CardTitle>
                      <p className="text-xs font-mono text-muted-foreground mt-1">{source.slug}</p>
                    </div>
                    <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20">
                      Active
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="py-0 pb-4">
                  <div className="flex justify-between items-center text-xs text-muted-foreground">
                    <span>Added {formatDistanceToNow(source.createdAt, { addSuffix: true })}</span>
                    <Button variant="ghost" size="sm" className="h-7 text-xs">
                      Configure <ChevronRight className="w-3 h-3 ml-1" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </div>

      {/* Right Panel: Connector Gallery */}
      <div className="w-[400px] shrink-0 flex flex-col">
        <div className="mb-4">
          <h2 className="text-lg font-bold">Connector Gallery</h2>
          <p className="text-xs text-muted-foreground mt-1">Available templates to add to your project.</p>
        </div>

        <div className="relative mb-4">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            placeholder="Search connectors..."
            className="w-full h-9 bg-background border border-border rounded-md pl-9 pr-3 text-sm outline-none focus:border-primary transition-colors"
          />
        </div>

        <div className="space-y-3 flex-1 overflow-y-auto pr-2">
          {templates.map((tpl: any) => (
            <Card
              key={tpl._id}
              className={`cursor-pointer transition-colors hover:border-primary/50 ${selectedTemplate?._id === tpl._id ? "border-primary" : ""}`}
              onClick={() => {
                setSelectedTemplate(tpl);
                setNewName(`${tpl.name} Source`);
                setNewSlug(`${project.slug}-${tpl.slug}`);
              }}
            >
              <CardContent className="p-4">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold">{tpl.name}</h3>
                    <p className="text-xs text-muted-foreground line-clamp-2 mt-1">{tpl.description}</p>
                  </div>
                  <Badge variant="secondary" className="ml-2 text-[10px]">{tpl.version}</Badge>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Add Source Modal Overlay (when a template is selected for addition) */}
      {selectedTemplate && (
        <>
          <div className="fixed inset-0 bg-black/50 z-40" onClick={() => setSelectedTemplate(null)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] bg-background border border-border rounded-lg shadow-2xl z-50 overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-border">
              <h2 className="text-lg font-semibold">Add Source: {selectedTemplate.name}</h2>
              <p className="text-xs text-muted-foreground mt-1">Configure your instance of this connector.</p>
            </div>

            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Source Name</label>
                <input
                  value={newName}
                  onChange={(e) => {
                    setNewName(e.target.value);
                    setNewSlug(`${project.slug}-${e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`);
                  }}
                  className="w-full h-9 bg-background border border-border rounded-md px-3 text-sm outline-none focus:border-primary transition-colors"
                  placeholder="My Data Source"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Source Slug</label>
                <input
                  value={newSlug}
                  onChange={(e) => setNewSlug(e.target.value)}
                  className="w-full h-9 bg-muted border border-border rounded-md px-3 text-sm font-mono outline-none focus:border-primary transition-colors"
                />
              </div>
              <div>
                 <label className="block text-xs font-medium text-muted-foreground mb-1">Overrides (YAML parameters)</label>
                 <div className="p-3 bg-muted rounded-md border border-border text-xs font-mono text-muted-foreground">
                    extends: {selectedTemplate.slug}<br/>
                    params:<br/>
                    &nbsp;&nbsp;# Will be editable after creation
                 </div>
              </div>
            </div>

            <div className="px-5 py-4 border-t border-border bg-muted/30 flex justify-end gap-3">
              <Button variant="outline" onClick={() => setSelectedTemplate(null)}>Cancel</Button>
              <Button onClick={handleAddSource} disabled={saving || !newName || !newSlug}>
                {saving ? "Adding..." : "Add Source"}
              </Button>
            </div>
          </div>
        </>
      )}

    </div>
  );
}

export default function ProjectSourcesPage({ params }: { params: Promise<{ project: string }> }) {
  const { project: projectSlug } = use(params);

  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center"><div className="animate-pulse">Loading sources...</div></div>}>
      <SourcesContent projectSlug={projectSlug} />
    </Suspense>
  );
}