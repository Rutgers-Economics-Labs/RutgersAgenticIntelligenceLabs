"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { useState } from "react";

type Tab = "apis" | "ontologies" | "pipelines";

export default function ConfigsPage() {
  const [tab, setTab] = useState<Tab>("apis");
  const apiConfigs = useQuery(api.configs.listApis, {});
  const ontologyConfigs = useQuery(api.configs.listOntologies, {});
  const pipelineConfigs = useQuery(api.configs.listPipelines, {});

  const tabs: { id: Tab; label: string; count: number | undefined }[] = [
    { id: "apis", label: "Data Sources", count: apiConfigs?.length },
    { id: "ontologies", label: "Ontologies", count: ontologyConfigs?.length },
    { id: "pipelines", label: "Pipelines", count: pipelineConfigs?.length },
  ];

  const items =
    tab === "apis" ? apiConfigs :
    tab === "ontologies" ? ontologyConfigs :
    pipelineConfigs;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Configs</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-[--border]">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === t.id
                ? "border-[--primary] text-[--primary]"
                : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
            }`}
          >
            {t.label}
            {t.count !== undefined && (
              <span className="ml-2 text-xs opacity-60">({t.count})</span>
            )}
          </button>
        ))}
      </div>

      {items === undefined && <p className="text-[--muted-foreground] text-sm">Loading…</p>}

      {items?.length === 0 && (
        <div className="flex items-center justify-center h-48 border border-dashed border-[--border] rounded-lg text-[--muted-foreground] text-sm">
          No {tab} configs yet. Seed from the engine defaults or add one manually.
        </div>
      )}

      {items && items.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map((cfg) => (
            <div key={cfg._id} className="p-4 rounded-lg border border-[--border] bg-[--card] hover:border-[--primary]/40 transition-colors">
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-medium text-sm">{cfg.name}</h3>
                {cfg.isPublic && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[--accent]/20 text-[--primary]">public</span>
                )}
              </div>
              <p className="text-xs font-mono text-[--muted-foreground] mb-3">{cfg.slug}</p>
              {"tags" in cfg && cfg.tags.length > 0 && (
                <div className="flex gap-1 flex-wrap">
                  {(cfg.tags as string[]).map((tag) => (
                    <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-[--muted] text-[--muted-foreground]">{tag}</span>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-[--muted-foreground] mt-3">
                Updated {new Date(cfg.updatedAt).toLocaleDateString()}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
