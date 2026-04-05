"use client";

import { useState, useEffect } from "react";
import { connectors, type ConnectorTemplate } from "@/lib/api";
import { ConnectorCard } from "@/components/registry/ConnectorCard";
import { ConnectorEditor } from "@/components/registry/ConnectorEditor";
import { Plus } from "lucide-react";

const PROVIDERS = [
  { id: "all", label: "All" },
  { id: "fred", label: "FRED" },
  { id: "census", label: "Census" },
  { id: "worldbank", label: "World Bank" },
  { id: "bls", label: "BLS" },
  { id: "generic", label: "Generic" },
] as const;

export default function ConnectorsPage() {
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("all");
  const [templates, setTemplates] = useState<ConnectorTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [showEditor, setShowEditor] = useState(false);
  const [refreshCount, setRefreshCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const results = await connectors.list(query);
        if (cancelled) return;

        let filtered = results;
        if (provider !== "all") {
          filtered = results.filter(r => r.tags.some(t => t.toLowerCase() === provider.toLowerCase()));
        }
        setTemplates(filtered);
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load connectors");
          setTemplates([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [query, provider, refreshCount]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Connectors</h2>
        <button
          onClick={() => setShowEditor(true)}
          className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-[#0d1117] hover:opacity-90"
        >
          <Plus size={16} />
          New Connector
        </button>
      </div>

      <div className="rounded-2xl border border-border bg-card p-4 space-y-4">
        <div className="grid gap-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search templates..."
            className="w-full rounded-xl border border-border bg-muted px-4 py-3 text-sm text-foreground outline-none focus:border-primary"
          />
        </div>

        <div className="flex flex-wrap gap-2">
          {PROVIDERS.map((item) => (
            <button
              key={item.id}
              onClick={() => setProvider(item.id)}
              className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
                provider === item.id
                  ? "border-primary bg-primary/10 text-[--primary]"
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-700/60 bg-red-900/20 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-muted-foreground">Loading templates...</div>
      ) : templates.length === 0 ? (
        <div className="text-sm text-muted-foreground">No templates found matching your criteria.</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {templates.map(t => (
            <ConnectorCard
              key={t.slug}
              slug={t.slug}
              name={t.name}
              description={t.description}
              version={t.version}
              tags={t.tags}
              usageCount={t.usageCount}
              content={t.content}
            />
          ))}
        </div>
      )}

      {showEditor && (
        <ConnectorEditor
          onClose={() => setShowEditor(false)}
          onSaved={() => {
            setShowEditor(false);
            setRefreshCount(c => c + 1);
          }}
        />
      )}
    </div>
  );
}
