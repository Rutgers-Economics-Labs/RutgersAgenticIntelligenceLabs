"use client";

import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import Link from "next/link";
import { 
  Plus, Search, Filter, ArrowUpRight, 
  FolderOpen, Activity, Database, Sparkles,
  ChevronRight, MoreVertical, GitFork, Trash2,
  Clock, Layers
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { 
  Dialog, DialogContent, DialogHeader, 
  DialogTitle, DialogTrigger, DialogFooter,
  DialogDescription
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Id } from "@/convex/_generated/dataModel";
import { formatDistanceToNow } from "date-fns";

const STATUS_STYLES: Record<string, string> = {
  hydrated: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
  ready: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  draft: "bg-slate-500/10 text-slate-500 border-slate-500/20",
};

const APPROACH_LABEL = {
  "data-first": "Data → Ontology",
  "ontology-first": "Ontology → Data",
};

export default function ProjectsPage() {
  const projects = useQuery(api.projects.list, {}) || [];
  const createProject = useMutation(api.projects.create);
  const removeProject = useMutation(api.projects.remove);
  const forkProject = useMutation(api.projects.forkProject);

  const [search, setSearch] = useState("");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [approach, setApproach] = useState<"data-first" | "ontology-first">("data-first");
  
  const [forkingProject, setForkingProject] = useState<{ id: Id<"projects">; name: string } | null>(null);
  const [forkName, setForkName] = useState("");

  const filtered = projects.filter(p => 
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.description?.toLowerCase().includes(search.toLowerCase())
  );

  const handleCreate = async () => {
    if (!newName) return;
    try {
      const slug = newName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
      await createProject({
        name: newName,
        slug,
        description: newDesc,
        approach,
      });
      setIsCreateOpen(false);
      setNewName("");
      setNewDesc("");
    } catch (err) {
      console.error(err);
      alert("Failed to create project");
    }
  };

  const handleFork = async () => {
    if (!forkingProject || !forkName) return;
    try {
      await forkProject({ projectId: forkingProject.id, newName: forkName });
      setForkingProject(null);
      setForkName("");
    } catch (err) {
      console.error(err);
      alert("Failed to fork project");
    }
  };

  const handleDelete = async (slug: string) => {
    if (!confirm("Are you sure you want to delete this project?")) return;
    try {
      await removeProject({ slug });
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex flex-col gap-10 max-w-7xl mx-auto w-full px-4 py-8 pb-20">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-xl bg-[--primary]/10 border border-[--primary]/20">
              <FolderOpen className="text-[--primary]" size={24} />
            </div>
            <h1 className="text-3xl font-extrabold tracking-tight">Projects</h1>
          </div>
          <p className="text-muted-foreground max-w-lg font-medium opacity-80">Research ontologies, data pipelines, and agent configurations.</p>
        </div>

        <div className="flex gap-3">
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button className="h-11 px-6 gap-2 bg-[--primary] hover:bg-[--accent] shadow-lg shadow-[--primary]/20">
                <Plus size={18} /> New Project
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[500px] bg-[--card] border-[--border]">
              <DialogHeader>
                <DialogTitle className="text-xl font-bold">Initialize Project</DialogTitle>
                <DialogDescription>Setup a new research context. Choose your architectural starting point.</DialogDescription>
              </DialogHeader>
              <div className="grid gap-6 py-4">
                <div className="space-y-2">
                  <label className="text-xs font-bold uppercase tracking-wider opacity-50">Project Name</label>
                  <Input
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    placeholder="e.g. Healthcare Supply Chain"
                    className="bg-black/20 border-[--border] focus-visible:ring-[--primary]"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-bold uppercase tracking-wider opacity-50">Description</label>
                  <Textarea
                    value={newDesc}
                    onChange={e => setNewDesc(e.target.value)}
                    placeholder="Briefly describe the research goals..."
                    rows={2}
                    className="bg-black/20 border-[--border] focus-visible:ring-[--primary]"
                  />
                </div>
                <div className="space-y-3">
                  <label className="text-xs font-bold uppercase tracking-wider opacity-50">Approach</label>
                  <div className="grid grid-cols-2 gap-3">
                    {(["data-first", "ontology-first"] as const).map((a) => (
                      <button
                        key={a}
                        onClick={() => setApproach(a)}
                        className={`p-4 rounded-xl border text-left transition-all ${
                          approach === a
                            ? "border-[--primary] bg-[--primary]/10 ring-1 ring-[--primary]/50"
                            : "border-[--border] bg-black/10 hover:border-[--primary]/40"
                        }`}
                      >
                        <p className={`text-xs font-bold mb-1 ${approach === a ? "text-[--primary]" : "text-[--foreground]"}`}>
                          {a === "data-first" ? "Data Driven" : "Ontology First"}
                        </p>
                        <p className="text-[10px] text-muted-foreground leading-relaxed">
                          {a === "data-first" ? "Start with data connectors." : "Start with schema definition."}
                        </p>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsCreateOpen(false)}>Cancel</Button>
                <Button onClick={handleCreate} disabled={!newName} className="bg-[--primary]">Create Project</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row items-center gap-4 py-2">
        <div className="relative flex-1 w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground opacity-50" size={16} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Filter projects by name or description..."
            className="w-full bg-[--card]/40 border border-[--border] rounded-xl pl-10 pr-4 py-2.5 text-sm outline-none focus:border-[--primary]/50 focus:ring-1 focus:ring-[--primary]/20 transition-all font-medium"
          />
        </div>
        <div className="flex gap-2 w-full sm:w-auto">
          <Button variant="outline" className="h-10 border-[--border] gap-2 flex-1 sm:flex-none">
            <Filter size={14} /> Sort
          </Button>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filtered.map((p) => (
          <div
            key={p._id}
            className="group relative flex flex-col p-6 rounded-2xl border border-[--border] bg-[--card]/40 backdrop-blur-sm hover:border-[--primary]/40 hover:bg-[--card]/60 transition-all duration-300 shadow-sm hover:shadow-xl hover:shadow-[--primary]/5"
          >
             <div className="flex items-start justify-between gap-4 mb-4">
                <div className="p-2.5 rounded-xl bg-gradient-to-br from-[--primary]/20 to-[--accent]/20 border border-[--primary]/20 text-[--primary] group-hover:scale-110 transition-transform">
                   <FolderOpen size={20} />
                </div>
                <div className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-widest border ${STATUS_STYLES[p.status]}`}>
                  {p.status}
                </div>
             </div>

             <div className="flex-1 mb-6">
                <Link href={`/${p.slug}`} className="block group/title">
                   <h3 className="text-lg font-bold tracking-tight mb-2 group-hover/title:text-[--primary] transition-colors flex items-center gap-1">
                      {p.name}
                      <ArrowUpRight size={14} className="opacity-0 group-hover/title:opacity-100 -translate-y-0.5 transition-all text-[--primary]" />
                   </h3>
                </Link>
                <p className="text-sm text-muted-foreground line-clamp-2 min-h-[40px] font-medium opacity-70">
                   {p.description || "No description provided for this research context."}
                </p>
                <div className="mt-4 flex items-center gap-3">
                   <div className="flex items-center gap-1 text-[10px] bg-white/5 border border-white/5 px-2 py-0.5 rounded uppercase tracking-tighter font-mono font-bold opacity-60">
                      <Layers size={10} /> {APPROACH_LABEL[p.approach]}
                   </div>
                </div>
             </div>

             <div className="grid grid-cols-2 gap-2 border-t border-[--border]/50 pt-5 mt-auto">
                <div className="flex flex-col gap-0.5">
                   <span className="text-[9px] uppercase tracking-wider font-bold opacity-30 flex items-center gap-1">
                      <Clock size={10} /> Updated
                   </span>
                   <span className="text-[10px] font-semibold opacity-60 truncate">
                      {formatDistanceToNow(p.updatedAt, { addSuffix: true })}
                   </span>
                </div>
                <div className="flex items-center justify-end gap-2">
                   <button 
                     onClick={() => { setForkingProject({ id: p._id, name: p.name }); setForkName(`${p.name} (fork)`); }}
                     className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center text-muted-foreground hover:text-[--primary] hover:bg-[--primary]/10 transition-all"
                     title="Fork Project"
                   >
                     <GitFork size={14} />
                   </button>
                   <button 
                     onClick={() => handleDelete(p.slug)}
                     className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-all"
                     title="Delete Project"
                   >
                     <Trash2 size={14} />
                   </button>
                   <Link 
                     href={`/${p.slug}`}
                     className="w-8 h-8 rounded-lg bg-[--primary]/10 border border-[--primary]/20 flex items-center justify-center text-[--primary] hover:bg-[--primary] hover:text-white transition-all shadow-sm"
                   >
                     <ChevronRight size={16} />
                   </Link>
                </div>
             </div>
          </div>
        ))}

        {filtered.length === 0 && (
          <div className="col-span-full py-24 text-center flex flex-col items-center border-2 border-dashed border-[--border] rounded-3xl opacity-40">
            <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
              <Search size={32} className="opacity-20" />
            </div>
            <h2 className="text-xl font-bold mb-1">No research contexts found</h2>
            <p className="text-sm text-muted-foreground max-w-xs">Create a new project to begin your agentic intelligence journey.</p>
          </div>
        )}
      </div>

      {/* Fork Dialog */}
      <Dialog open={!!forkingProject} onOpenChange={(open) => !open && setForkingProject(null)}>
        <DialogContent className="bg-[--card] border-[--border]">
          <DialogHeader>
            <DialogTitle>Fork Project</DialogTitle>
            <DialogDescription>Create a copy of this research context, including its ontology and pipeline settings.</DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <label className="text-xs font-bold uppercase tracking-wider opacity-50 block mb-2">New Name</label>
            <Input value={forkName} onChange={e => setForkName(e.target.value)} className="bg-black/20 border-[--border]" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setForkingProject(null)}>Cancel</Button>
            <Button onClick={handleFork} className="bg-[--primary]">Confirm Fork</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Footer Info */}
      <div className="flex items-center justify-center gap-6 mt-16 opacity-30 select-none">
        <div className="flex items-center gap-2">
          <Activity size={12} />
          <span className="text-[10px] font-bold uppercase tracking-[0.2em]">Live Registry</span>
        </div>
        <div className="w-1 h-1 rounded-full bg-foreground/50" />
        <div className="flex items-center gap-2">
          <Sparkles size={12} />
          <span className="text-[10px] font-bold uppercase tracking-[0.2em]">Research Optimized</span>
        </div>
      </div>
    </div>
  );
}
