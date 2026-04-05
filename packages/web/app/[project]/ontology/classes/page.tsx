"use client";
import { useState, useEffect, useCallback, Suspense } from "react";

import { ontology, type OntologyClass, type EntitySummary } from "@/lib/api";
import Link from "next/link";

const CLASS_COLORS: Record<string, string> = {
  State: "#F5A623", County: "#4A9EDD", Municipality: "#50C878",
  Individual: "#B07FD4", Measure: "#E05C5C",
};

function ExplorerContent({ projectSlug }: { projectSlug: string }) {


  const [classes, setClasses] = useState<OntologyClass[]>([]);
  const [selectedClass, setSelectedClass] = useState("");
  const [items, setItems] = useState<EntitySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchMode, setSearchMode] = useState<"keyword" | "semantic">("keyword");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    ontology.classes(projectSlug)
      .then((cls) => {
        const sorted = [...cls].sort((a, b) => b.instanceCount - a.instanceCount);
        setClasses(sorted);
        if (sorted.length) setSelectedClass(sorted[0].name);
      })
      .catch(() => setError("Could not connect to API. Is the FastAPI server running?"));
  }, [projectSlug]);

  const load = useCallback(async () => {
    if (!selectedClass) return;
    setLoading(true);
    setError("");
    try {
      if (searchMode === "semantic" && search.trim()) {
        const results = await ontology.semanticSearch(search, [selectedClass], 20, projectSlug);
        setItems(results);
        setTotal(results.length);
      } else {
        const res = await ontology.instances(selectedClass, page, 50, search, projectSlug);
        setItems(res.items);
        setTotal(res.total);
      }
    } catch {
      setItems([]);
      setTotal(0);
      setError(searchMode === "semantic" ? "Semantic search is unavailable." : "Failed to load instances");
    }
    finally { setLoading(false); }
  }, [page, search, searchMode, selectedClass, projectSlug]);

  useEffect(() => { load(); }, [load]);

  const totalPages = Math.ceil(total / 50);
  const color = CLASS_COLORS[selectedClass] ?? "#8b949e";

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">Ontology Explorer</h1>

      {error && (
        <div className="mb-4 p-3 rounded bg-red-900/30 border border-red-700 text-red-300 text-sm">{error}</div>
      )}

      {/* Controls */}
      <div className="flex gap-3 mb-6 flex-wrap">
        <div className="relative max-w-full">
          <div className="overflow-x-auto whitespace-nowrap -mx-2 px-2 py-1 [scrollbar-width:thin] [scrollbar-color:var(--border)_transparent] [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-[--border] [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:border-[3px] [&::-webkit-scrollbar-thumb]:border-transparent [&::-webkit-scrollbar-thumb]:bg-clip-content hover:[&::-webkit-scrollbar-thumb]:bg-[--muted-foreground]">
            <div className="inline-flex gap-2 items-center">
            {classes.map((c) => (
              <button
                key={c.name}
                onClick={() => { setSelectedClass(c.name); setPage(1); }}
                className="px-3 py-1.5 rounded text-sm font-medium transition-all shrink-0"
                style={{
                  background: selectedClass === c.name ? CLASS_COLORS[c.name] + "33" : "transparent",
                  color: CLASS_COLORS[c.name] ?? "#8b949e",
                  border: `1px solid ${selectedClass === c.name ? CLASS_COLORS[c.name] : "#30363d"}`,
                }}
              >
                {c.name} <span className="opacity-60 text-xs">({c.instanceCount.toLocaleString()})</span>
              </button>
            ))}
            </div>
          </div>
          <div className="pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-[--background] to-transparent" />
          <div className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-[--background] to-transparent" />
        </div>
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder={searchMode === "semantic" ? "Search by meaning…" : "Search by name…"}
          className="flex-1 min-w-48 px-3 py-1.5 rounded border border-[--border] bg-[--muted] text-sm text-[--foreground] placeholder:text-[--muted-foreground] outline-none focus:border-[--primary]"
        />
        <div className="inline-flex rounded-md border border-[--border] overflow-hidden">
          <button
            onClick={() => { setSearchMode("keyword"); setPage(1); }}
            className="px-3 py-1.5 text-sm transition-colors"
            style={{
              background: searchMode === "keyword" ? "var(--primary)" : "transparent",
              color: searchMode === "keyword" ? "var(--primary-foreground)" : "var(--foreground)",
            }}
          >
            Keyword
          </button>
          <button
            onClick={() => { setSearchMode("semantic"); setPage(1); }}
            className="px-3 py-1.5 text-sm transition-colors border-l border-[--border]"
            style={{
              background: searchMode === "semantic" ? "var(--primary)" : "transparent",
              color: searchMode === "semantic" ? "var(--primary-foreground)" : "var(--foreground)",
            }}
          >
            Semantic
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-[--border] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[--border] bg-[--muted]">
              <th className="text-left px-4 py-2.5 text-[--muted-foreground] font-medium">Name</th>
              <th className="text-left px-4 py-2.5 text-[--muted-foreground] font-medium">ID</th>
              <th className="text-left px-4 py-2.5 text-[--muted-foreground] font-medium">Details</th>
              <th className="w-20 px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-[--muted-foreground]">Loading…</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-[--muted-foreground]">No results.</td></tr>
            )}
            {!loading && items.map((item) => (
              <tr key={item.id} className="border-b border-[--border] hover:bg-white/[0.03] transition-colors">
                <td className="px-4 py-3 font-medium" style={{ color }}>
                  {String(item.properties.hasName ?? item.id)}
                </td>
                <td className="px-4 py-3 text-[--muted-foreground] font-mono text-xs">{item.id}</td>
                <td className="px-4 py-3 text-[--muted-foreground] text-xs">
                  {item.properties.hasPopulation != null && (
                    <span className="mr-3">Pop: {Number(item.properties.hasPopulation).toLocaleString()}</span>
                  )}
                  {item.properties.hasFIPS != null && (
                    <span className="mr-3">FIPS: {String(item.properties.hasFIPS)}</span>
                  )}
                  {item.properties.hasDate != null && (
                    <span className="mr-3">{String(item.properties.hasDate)}</span>
                  )}
                  {item.properties.hasValue != null && (
                    <span>{Number(item.properties.hasValue).toFixed(2)}</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <Link
                    href={`/explorer/${encodeURIComponent(item.id)}${projectSlug ? `?projectSlug=${projectSlug}` : ""}`}
                    className="text-xs text-[--primary] hover:underline"
                  >
                    View →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {searchMode === "keyword" && totalPages > 1 && (
        <div className="flex items-center gap-3 mt-4 text-sm text-[--muted-foreground]">
          <button
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
            className="px-3 py-1 rounded border border-[--border] hover:bg-[--muted] disabled:opacity-40 disabled:cursor-not-allowed"
          >← Prev</button>
          <span>Page {page} of {totalPages} ({total.toLocaleString()} total)</span>
          <button
            disabled={page === totalPages}
            onClick={() => setPage(p => p + 1)}
            className="px-3 py-1 rounded border border-[--border] hover:bg-[--muted] disabled:opacity-40 disabled:cursor-not-allowed"
          >Next →</button>
        </div>
      )}
    </div>
  );
}

export default async function ExplorerPage({ params }: { params: { project: string } }) {
  return (
    <Suspense fallback={<div className="p-8 text-[--muted-foreground]">Loading explorer...</div>}>
      <ExplorerContent projectSlug={params.project} />
    </Suspense>
  );
}
