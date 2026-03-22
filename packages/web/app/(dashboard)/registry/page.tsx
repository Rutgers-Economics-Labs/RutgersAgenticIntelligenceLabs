"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { registry, type RegistryEntry } from "@/lib/api";

const PROVIDERS = [
  { id: "all", label: "All" },
  { id: "fred", label: "FRED" },
  { id: "census", label: "Census" },
  { id: "worldbank", label: "World Bank" },
  { id: "bls", label: "BLS" },
] as const;

const GEOGRAPHIES = [
  { id: "all", label: "All geographies" },
  { id: "national", label: "National" },
  { id: "state", label: "State" },
  { id: "county", label: "County" },
  { id: "msa", label: "MSA" },
] as const;

function providerTone(provider: string) {
  switch (provider) {
    case "fred":
      return "bg-emerald-500/10 text-emerald-300 border-emerald-500/30";
    case "census":
      return "bg-sky-500/10 text-sky-300 border-sky-500/30";
    case "worldbank":
      return "bg-amber-500/10 text-amber-300 border-amber-500/30";
    case "bls":
      return "bg-rose-500/10 text-rose-300 border-rose-500/30";
    default:
      return "bg-[--muted] text-[--muted-foreground] border-[--border]";
  }
}

export default function RegistryPage() {
  const [query, setQuery] = useState("unemployment");
  const [provider, setProvider] = useState("all");
  const [geography, setGeography] = useState("all");
  const [entries, setEntries] = useState<RegistryEntry[]>([]);
  const [selected, setSelected] = useState<RegistryEntry | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const results = await registry.search(query, provider, geography, 24);
        if (cancelled) return;
        setEntries(results);
        setSelected((current) => {
          if (current) {
            const next = results.find((item) => item.provider === current.provider && item.id === current.id);
            if (next) return next;
          }
          return results[0] ?? null;
        });
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load registry");
          setEntries([]);
          setSelected(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [query, provider, geography]);

  const useThisHref = useMemo(() => {
    if (!selected) return "/configs";
    const params = new URLSearchParams({
      prefillType: "apis",
      prefillName: selected.name,
      prefillSlug: `${selected.provider}-${selected.id.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
      prefillContent: selected.exampleYaml,
    });
    return `/configs?${params.toString()}`;
  }, [selected]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Registry</h1>
          <p className="mt-1 text-sm text-[--muted-foreground] max-w-2xl">
            Search known public series and variables before creating a new data source config.
          </p>
        </div>
        <Link
          href="/configs"
          className="rounded-lg border border-[--border] px-3 py-2 text-sm text-[--muted-foreground] hover:text-[--foreground]"
        >
          Open Configs
        </Link>
      </div>

      <div className="rounded-2xl border border-[--border] bg-[--card] p-4 space-y-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search unemployment, CPI, GDP, housing..."
            className="w-full rounded-xl border border-[--border] bg-[--muted] px-4 py-3 text-sm text-[--foreground] outline-none focus:border-[--primary]"
          />
          <select
            aria-label="Geography filter"
            value={geography}
            onChange={(e) => setGeography(e.target.value)}
            className="rounded-xl border border-[--border] bg-[--muted] px-3 py-3 text-sm text-[--foreground] outline-none focus:border-[--primary]"
          >
            {GEOGRAPHIES.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap gap-2">
          {PROVIDERS.map((item) => (
            <button
              key={item.id}
              onClick={() => setProvider(item.id)}
              className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
                provider === item.id
                  ? "border-[--primary] bg-[--primary]/10 text-[--primary]"
                  : "border-[--border] text-[--muted-foreground] hover:text-[--foreground]"
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

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <div className="rounded-2xl border border-[--border] bg-[--card]">
          <div className="flex items-center justify-between border-b border-[--border] px-4 py-3">
            <p className="text-sm font-medium">Results</p>
            <p className="text-xs text-[--muted-foreground]">
              {loading ? "Loading…" : `${entries.length} match${entries.length === 1 ? "" : "es"}`}
            </p>
          </div>

          <div className="divide-y divide-[--border]">
            {entries.map((entry) => {
              const active = selected?.provider === entry.provider && selected?.id === entry.id;
              return (
                <button
                  key={`${entry.provider}:${entry.id}`}
                  onClick={() => setSelected(entry)}
                  className={`w-full px-4 py-4 text-left transition-colors ${
                    active ? "bg-[--muted]" : "hover:bg-[--muted]/60"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-sm font-medium">{entry.name}</h2>
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${providerTone(entry.provider)}`}>
                          {entry.provider}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-[--muted-foreground] font-mono">{entry.id}</p>
                    </div>
                    <div className="text-right text-[10px] text-[--muted-foreground] uppercase tracking-wide">
                      <div>{entry.frequency}</div>
                      <div>{entry.geography}</div>
                    </div>
                  </div>
                  <p className="mt-2 text-sm text-[--muted-foreground]">{entry.description}</p>
                </button>
              );
            })}

            {!loading && entries.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-[--muted-foreground]">
                No sources matched those filters.
              </div>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-[--border] bg-[--card] p-4">
          {selected ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">{selected.name}</h2>
                  <p className="mt-1 text-xs font-mono text-[--muted-foreground]">
                    {selected.provider}/{selected.id}
                  </p>
                </div>
                <span className={`rounded-full border px-2 py-1 text-[10px] uppercase tracking-wide ${providerTone(selected.provider)}`}>
                  {selected.provider}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="rounded-xl border border-[--border] bg-[--muted] p-3">
                  <p className="text-[--muted-foreground]">Frequency</p>
                  <p className="mt-1 font-medium">{selected.frequency}</p>
                </div>
                <div className="rounded-xl border border-[--border] bg-[--muted] p-3">
                  <p className="text-[--muted-foreground]">Geography</p>
                  <p className="mt-1 font-medium">{selected.geography}</p>
                </div>
                <div className="rounded-xl border border-[--border] bg-[--muted] p-3">
                  <p className="text-[--muted-foreground]">Unit</p>
                  <p className="mt-1 font-medium">{selected.unit}</p>
                </div>
              </div>

              <div>
                <p className="text-sm text-[--muted-foreground]">{selected.description}</p>
                {selected.tags.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {selected.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full border border-[--border] bg-[--muted] px-2 py-1 text-[10px] uppercase tracking-wide text-[--muted-foreground]"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-xs uppercase tracking-wide text-[--muted-foreground]">Example YAML</p>
                  <Link
                    href={useThisHref}
                    className="rounded-lg bg-[--primary] px-3 py-1.5 text-xs font-semibold text-[#0d1117] hover:opacity-90"
                  >
                    Use this
                  </Link>
                </div>
                <pre className="overflow-x-auto rounded-xl border border-[--border] bg-[--muted] p-4 text-xs leading-5 text-[--foreground]">
                  {selected.exampleYaml}
                </pre>
              </div>
            </div>
          ) : (
            <div className="flex h-full min-h-64 items-center justify-center text-sm text-[--muted-foreground]">
              Select a source to inspect its YAML snippet.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
