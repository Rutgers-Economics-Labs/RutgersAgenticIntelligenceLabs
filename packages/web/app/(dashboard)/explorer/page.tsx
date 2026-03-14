"use client";
import { useState, useEffect, useCallback } from "react";
import { ontology, type OntologyClass, type EntitySummary } from "@/lib/api";
import Link from "next/link";

const CLASS_COLORS: Record<string, string> = {
  State: "#F5A623", County: "#4A9EDD", Municipality: "#50C878",
  Individual: "#B07FD4", Measure: "#E05C5C",
};

export default function ExplorerPage() {
  const [classes, setClasses] = useState<OntologyClass[]>([]);
  const [selectedClass, setSelectedClass] = useState("");
  const [items, setItems] = useState<EntitySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    ontology.classes()
      .then((cls) => { setClasses(cls); if (cls.length) setSelectedClass(cls[0].name); })
      .catch(() => setError("Could not connect to API. Is the FastAPI server running?"));
  }, []);

  const load = useCallback(async () => {
    if (!selectedClass) return;
    setLoading(true);
    try {
      const res = await ontology.instances(selectedClass, page, 50, search);
      setItems(res.items);
      setTotal(res.total);
    } catch { setError("Failed to load instances"); }
    finally { setLoading(false); }
  }, [selectedClass, page, search]);

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
        <div className="flex gap-2">
          {classes.map((c) => (
            <button
              key={c.name}
              onClick={() => { setSelectedClass(c.name); setPage(1); }}
              className="px-3 py-1.5 rounded text-sm font-medium transition-all"
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
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search by name…"
          className="flex-1 min-w-48 px-3 py-1.5 rounded border border-[--border] bg-[--muted] text-sm text-[--foreground] placeholder:text-[--muted-foreground] outline-none focus:border-[--primary]"
        />
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
                    href={`/explorer/${encodeURIComponent(item.id)}`}
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
      {totalPages > 1 && (
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
