"use client";
import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { quality as qualityApi } from "@/lib/api";
import {
  ShieldCheck, RefreshCw, Camera, GitCompare,
  AlertTriangle, CheckCircle2, Loader2, ChevronDown,
  ChevronRight, TrendingUp, TrendingDown, Minus,
  Table2, Database, ArrowUpRight, ArrowDownRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

type ColumnStat = {
  name: string; type: string;
  nullCount: number; nullRate: number;
  distinctCount: number; min?: string; max?: string; error?: string;
};
type TableReport = {
  table: string; rowCount: number;
  columns: ColumnStat[]; freshness?: { column: string; maxValue: string } | null;
};
type QualityReport = {
  projectId?: string; generatedAt: number;
  summary: { tableCount: number; totalRows: number; overallNullRate: number };
  tables: TableReport[];
  error?: string;
};
type ColumnDiff = {
  column: string; status: string;
  nullRateDrift?: number; distinctDelta?: number;
  newNullRate?: number; oldNullRate?: number;
};
type TableDiff = {
  table: string; status: string;
  newCount: number; oldCount: number; delta: number;
  columnDiffs: ColumnDiff[];
};
type DiffReport = {
  hasDiff: boolean; message?: string; snapshots?: number;
  newer?: { label: string; createdAt: number };
  older?: { label: string; createdAt: number };
  summary?: { tablesAdded: number; tablesRemoved: number; tablesGrew: number; tablesShrank: number; tablesUnchanged: number };
  tables?: TableDiff[];
};

// ─── Null rate bar ────────────────────────────────────────────────────────────

function NullBar({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100);
  const color = rate === 0 ? "bg-green-500" : rate < 0.05 ? "bg-yellow-500" : rate < 0.2 ? "bg-orange-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-1.5 bg-[--muted]/40 rounded-full overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className={cn("text-[10px] font-mono shrink-0 w-8 text-right",
        rate === 0 ? "text-green-500" : rate < 0.05 ? "text-yellow-500" : rate < 0.2 ? "text-orange-500" : "text-red-500"
      )}>
        {pct}%
      </span>
    </div>
  );
}

// ─── Table card ───────────────────────────────────────────────────────────────

function TableCard({ t }: { t: TableReport }) {
  const [open, setOpen] = useState(false);
  const worstNullRate = Math.max(...t.columns.map(c => c.nullRate));
  const healthColor =
    worstNullRate === 0 ? "border-green-500/30 bg-green-500/5" :
    worstNullRate < 0.05 ? "border-yellow-500/30 bg-yellow-500/5" :
    worstNullRate < 0.2 ? "border-orange-500/30 bg-orange-500/5" :
    "border-red-500/30 bg-red-500/5";
  const healthIcon =
    worstNullRate === 0 ? <CheckCircle2 size={13} className="text-green-500" /> :
    worstNullRate < 0.05 ? <CheckCircle2 size={13} className="text-yellow-500" /> :
    <AlertTriangle size={13} className="text-orange-500" />;

  return (
    <div className={cn("rounded-xl border overflow-hidden transition-all", healthColor)}>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          {healthIcon}
          <span className="font-semibold text-sm text-[--foreground] truncate">{t.table}</span>
          {t.freshness && (
            <span className="text-[10px] text-[--muted-foreground] bg-[--muted]/30 px-2 py-0.5 rounded-full">
              latest: {t.freshness.maxValue}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 shrink-0 ml-4">
          <div className="text-right">
            <p className="text-sm font-bold text-[--foreground]">{t.rowCount.toLocaleString()}</p>
            <p className="text-[10px] text-[--muted-foreground]">rows</p>
          </div>
          <div className="text-right hidden sm:block">
            <p className="text-sm font-bold text-[--foreground]">{t.columns.length}</p>
            <p className="text-[10px] text-[--muted-foreground]">cols</p>
          </div>
          {open ? <ChevronDown size={15} className="text-[--muted-foreground]" /> : <ChevronRight size={15} className="text-[--muted-foreground]" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-[--border]/50 px-4 py-3 bg-[--card]/50">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[--muted-foreground] border-b border-[--border]/40">
                  <th className="text-left py-1.5 pr-4 font-semibold">Column</th>
                  <th className="text-left py-1.5 pr-4 font-semibold">Type</th>
                  <th className="text-left py-1.5 pr-4 font-semibold w-40">Null rate</th>
                  <th className="text-right py-1.5 pr-4 font-semibold">Distinct</th>
                  <th className="text-right py-1.5 font-semibold hidden md:table-cell">Min</th>
                  <th className="text-right py-1.5 font-semibold hidden md:table-cell pl-4">Max</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[--border]/20">
                {t.columns.map(c => (
                  <tr key={c.name} className="hover:bg-[--muted]/10 transition-colors">
                    <td className="py-1.5 pr-4 font-mono text-[--foreground]">{c.name}</td>
                    <td className="py-1.5 pr-4 text-[--muted-foreground] font-mono">{c.type}</td>
                    <td className="py-1.5 pr-4 w-40">
                      {c.error ? <span className="text-red-400 text-[10px]">error</span> : <NullBar rate={c.nullRate} />}
                    </td>
                    <td className="py-1.5 pr-4 text-right text-[--muted-foreground]">{c.distinctCount?.toLocaleString()}</td>
                    <td className="py-1.5 text-right text-[--muted-foreground] hidden md:table-cell truncate max-w-[80px]">{c.min ?? "—"}</td>
                    <td className="py-1.5 text-right text-[--muted-foreground] pl-4 hidden md:table-cell truncate max-w-[80px]">{c.max ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Diff view ────────────────────────────────────────────────────────────────

function DiffView({ diff }: { diff: DiffReport }) {
  if (!diff.hasDiff) {
    return (
      <div className="rounded-xl border border-[--border] bg-[--card] p-8 text-center">
        <GitCompare size={32} className="mx-auto mb-3 text-[--muted-foreground] opacity-40" />
        <p className="text-sm font-medium text-[--foreground] mb-1">No diff available</p>
        <p className="text-xs text-[--muted-foreground]">
          {diff.message ?? "Take at least 2 snapshots to compare."}
        </p>
      </div>
    );
  }

  const s = diff.summary!;
  const summaryItems = [
    { label: "Added", value: s.tablesAdded, color: "text-green-500", bg: "bg-green-500/10" },
    { label: "Grew", value: s.tablesGrew, color: "text-blue-500", bg: "bg-blue-500/10" },
    { label: "Shrank", value: s.tablesShrank, color: "text-orange-500", bg: "bg-orange-500/10" },
    { label: "Removed", value: s.tablesRemoved, color: "text-red-500", bg: "bg-red-500/10" },
    { label: "Unchanged", value: s.tablesUnchanged, color: "text-[--muted-foreground]", bg: "bg-[--muted]/20" },
  ].filter(i => i.value > 0);

  return (
    <div className="space-y-4">
      {/* Comparison header */}
      <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-[--border] bg-[--card] text-sm">
        <span className="text-[--muted-foreground] text-xs font-mono">{diff.older!.label}</span>
        <ChevronRight size={14} className="text-[--muted-foreground] shrink-0" />
        <span className="text-[--foreground] font-semibold text-xs font-mono">{diff.newer!.label}</span>
        <div className="ml-auto flex gap-2">
          {summaryItems.map(i => (
            <span key={i.label} className={cn("px-2 py-0.5 rounded-full text-[10px] font-semibold", i.bg, i.color)}>
              {i.value} {i.label}
            </span>
          ))}
        </div>
      </div>

      {/* Table diffs */}
      <div className="space-y-2">
        {diff.tables!.map(t => <TableDiffRow key={t.table} t={t} />)}
      </div>
    </div>
  );
}

function TableDiffRow({ t }: { t: TableDiff }) {
  const [open, setOpen] = useState(t.status !== "unchanged");
  const statusColor =
    t.status === "added" ? "border-green-500/40 bg-green-500/5" :
    t.status === "removed" ? "border-red-500/40 bg-red-500/5" :
    t.status === "grew" ? "border-blue-500/40 bg-blue-500/5" :
    t.status === "shrank" ? "border-orange-500/40 bg-orange-500/5" :
    "border-[--border] bg-[--card]";
  const DeltaIcon = t.delta > 0 ? TrendingUp : t.delta < 0 ? TrendingDown : Minus;
  const deltaColor = t.delta > 0 ? "text-green-500" : t.delta < 0 ? "text-orange-500" : "text-[--muted-foreground]";

  return (
    <div className={cn("rounded-xl border overflow-hidden", statusColor)}>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-3">
          <Table2 size={13} className="text-[--muted-foreground]" />
          <span className="font-semibold text-sm text-[--foreground]">{t.table}</span>
          <span className={cn(
            "text-[10px] font-semibold px-2 py-0.5 rounded-full",
            t.status === "added" ? "bg-green-500/15 text-green-500" :
            t.status === "removed" ? "bg-red-500/15 text-red-500" :
            t.status === "grew" ? "bg-blue-500/15 text-blue-500" :
            t.status === "shrank" ? "bg-orange-500/15 text-orange-500" :
            "bg-[--muted]/30 text-[--muted-foreground]"
          )}>
            {t.status}
          </span>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[--muted-foreground] text-xs">{t.oldCount.toLocaleString()}</span>
            <ChevronRight size={12} className="text-[--muted-foreground]" />
            <span className="text-[--foreground] text-xs font-semibold">{t.newCount.toLocaleString()}</span>
          </div>
          <div className={cn("flex items-center gap-1 text-xs font-bold", deltaColor)}>
            <DeltaIcon size={13} />
            {t.delta > 0 ? "+" : ""}{t.delta.toLocaleString()}
          </div>
          {open ? <ChevronDown size={14} className="text-[--muted-foreground]" /> : <ChevronRight size={14} className="text-[--muted-foreground]" />}
        </div>
      </button>

      {open && t.columnDiffs.length > 0 && (
        <div className="border-t border-[--border]/40 px-4 py-3 bg-[--card]/50 space-y-1">
          <p className="text-[10px] font-semibold text-[--muted-foreground] uppercase tracking-wide mb-2">Column changes</p>
          {t.columnDiffs.map(c => (
            <div key={c.column} className="flex items-center gap-3 text-xs">
              <span className="font-mono text-[--foreground] w-40 truncate">{c.column}</span>
              {c.status === "added" && <span className="text-green-500 text-[10px]">+ added</span>}
              {c.status === "removed" && <span className="text-red-500 text-[10px]">− removed</span>}
              {c.status === "changed" && (
                <>
                  {(c.nullRateDrift ?? 0) !== 0 && (
                    <span className={cn("flex items-center gap-0.5 text-[10px]", (c.nullRateDrift ?? 0) > 0 ? "text-orange-500" : "text-green-500")}>
                      {(c.nullRateDrift ?? 0) > 0 ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                      null {(c.nullRateDrift ?? 0) > 0 ? "+" : ""}{Math.round((c.nullRateDrift ?? 0) * 100)}%
                    </span>
                  )}
                  {(c.distinctDelta ?? 0) !== 0 && (
                    <span className={cn("flex items-center gap-0.5 text-[10px]", (c.distinctDelta ?? 0) > 0 ? "text-blue-500" : "text-orange-500")}>
                      {(c.distinctDelta ?? 0) > 0 ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                      distinct {(c.distinctDelta ?? 0) > 0 ? "+" : ""}{c.distinctDelta}
                    </span>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
      {open && t.columnDiffs.length === 0 && t.status !== "unchanged" && (
        <div className="border-t border-[--border]/40 px-4 py-2 text-[10px] text-[--muted-foreground] italic">No column-level changes detected</div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function QualityPage() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("projectId") ?? undefined;

  const snapshots = useQuery(api.quality.listSnapshots, { projectId: projectId as any, limit: 10 });

  const [report, setReport] = useState<QualityReport | null>(null);
  const [diff, setDiff] = useState<DiffReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [snapshotting, setSnapshotting] = useState(false);
  const [activeTab, setActiveTab] = useState<"quality" | "diff">("quality");
  const [error, setError] = useState<string | null>(null);

  const loadReport = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [r, d] = await Promise.all([
        qualityApi.report(projectId),
        qualityApi.diff(projectId),
      ]);
      setReport(r);
      setDiff(d);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { loadReport(); }, [loadReport]);

  const takeSnapshot = async () => {
    setSnapshotting(true);
    try {
      const label = `Snapshot ${new Date().toLocaleString()}`;
      await qualityApi.snapshot(projectId, label);
      const d = await qualityApi.diff(projectId);
      setDiff(d);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSnapshotting(false);
    }
  };

  const summary = report?.summary;
  const overallHealth =
    !summary ? null :
    summary.overallNullRate === 0 ? "excellent" :
    summary.overallNullRate < 0.05 ? "good" :
    summary.overallNullRate < 0.15 ? "fair" : "poor";

  const healthColors: Record<string, string> = {
    excellent: "text-green-500",
    good: "text-yellow-500",
    fair: "text-orange-500",
    poor: "text-red-500",
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[--foreground] flex items-center gap-3">
            <ShieldCheck size={24} className="text-[--primary]" />
            Data Quality
          </h1>
          <p className="text-sm text-[--muted-foreground] mt-1">
            Ontology health — null rates, entity counts, and schema changes
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={takeSnapshot}
            disabled={snapshotting || loading || !!report?.error}
            title="Save current state for diff comparison"
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[--border] text-xs font-semibold text-[--foreground] hover:bg-[--muted]/30 disabled:opacity-40 transition-colors"
          >
            {snapshotting ? <Loader2 size={13} className="animate-spin" /> : <Camera size={13} />}
            Snapshot
          </button>
          <button
            onClick={loadReport}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[--border] text-xs font-semibold text-[--foreground] hover:bg-[--muted]/30 disabled:opacity-40 transition-colors"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-500 text-sm">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !report && (
        <div className="flex items-center justify-center py-20 gap-3 text-[--muted-foreground]">
          <Loader2 size={20} className="animate-spin text-[--primary]" />
          <span className="text-sm">Running quality checks…</span>
        </div>
      )}

      {/* No DB */}
      {report?.error && (
        <div className="rounded-xl border border-[--border] bg-[--card] p-10 text-center">
          <Database size={36} className="mx-auto mb-3 text-[--muted-foreground] opacity-30" />
          <p className="text-sm font-medium text-[--foreground]">No database loaded</p>
          <p className="text-xs text-[--muted-foreground] mt-1">Run a hydration pipeline to generate the DuckDB ontology first.</p>
        </div>
      )}

      {report && !report.error && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="rounded-xl border border-[--border] bg-[--card] px-5 py-4">
              <p className="text-[10px] font-semibold text-[--muted-foreground] uppercase tracking-wide">Tables</p>
              <p className="text-3xl font-bold text-[--foreground] mt-1">{summary!.tableCount}</p>
            </div>
            <div className="rounded-xl border border-[--border] bg-[--card] px-5 py-4">
              <p className="text-[10px] font-semibold text-[--muted-foreground] uppercase tracking-wide">Total Rows</p>
              <p className="text-3xl font-bold text-[--foreground] mt-1">{summary!.totalRows.toLocaleString()}</p>
            </div>
            <div className="rounded-xl border border-[--border] bg-[--card] px-5 py-4">
              <p className="text-[10px] font-semibold text-[--muted-foreground] uppercase tracking-wide">Null Rate</p>
              <p className={cn("text-3xl font-bold mt-1", healthColors[overallHealth!])}>
                {Math.round(summary!.overallNullRate * 100)}%
              </p>
            </div>
            <div className="rounded-xl border border-[--border] bg-[--card] px-5 py-4">
              <p className="text-[10px] font-semibold text-[--muted-foreground] uppercase tracking-wide">Health</p>
              <p className={cn("text-2xl font-bold mt-1 capitalize", healthColors[overallHealth!])}>
                {overallHealth}
              </p>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-[--border] gap-1">
            {(["quality", "diff"] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  "px-4 py-2.5 text-xs font-semibold border-b-2 transition-all flex items-center gap-2 -mb-px",
                  activeTab === tab
                    ? "border-[--primary] text-[--foreground]"
                    : "border-transparent text-[--muted-foreground] hover:text-[--foreground]"
                )}
              >
                {tab === "quality" ? <ShieldCheck size={13} /> : <GitCompare size={13} />}
                {tab === "quality" ? "Table Health" : `Diff ${snapshots && snapshots.length > 0 ? `(${snapshots.length} snapshots)` : ""}`}
              </button>
            ))}
          </div>

          {/* Table health */}
          {activeTab === "quality" && (
            <div className="space-y-3">
              {report.tables.length === 0 && (
                <p className="text-sm text-[--muted-foreground] py-8 text-center">No tables found in this database.</p>
              )}
              {[...report.tables]
                .sort((a, b) => {
                  // Sort worst null rates first
                  const aWorst = Math.max(...a.columns.map(c => c.nullRate));
                  const bWorst = Math.max(...b.columns.map(c => c.nullRate));
                  return bWorst - aWorst;
                })
                .map(t => <TableCard key={t.table} t={t} />)
              }
            </div>
          )}

          {/* Diff */}
          {activeTab === "diff" && diff && <DiffView diff={diff} />}
        </>
      )}
    </div>
  );
}
