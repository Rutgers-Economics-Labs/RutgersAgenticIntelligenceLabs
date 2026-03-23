"use client";

import { useRef, useState } from "react";
import {
  ChevronDown, ChevronRight, Download, Loader2,
  Play, Plus, Save, Terminal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { execute, ExecuteResult } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

const ACADEMIC_STARTER = `import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams.update({
    "figure.facecolor": "#0d1117", "axes.facecolor": "#161b22",
    "text.color": "white", "axes.labelcolor": "white",
    "xtick.color": "white", "ytick.color": "white",
})

# ── 1. Explore classes ────────────────────────────────────────────
tables = list_tables()
print("Available tables:", tables)

# ── 2. Load faculty and rank by h-index ──────────────────────────
faculty_df = get_table("Faculty")
faculty_df["hasHIndex"] = pd.to_numeric(faculty_df.get("hasHIndex"), errors="coerce")
faculty_df["hasPublicationCount"] = pd.to_numeric(faculty_df.get("hasPublicationCount"), errors="coerce")
top15 = faculty_df.dropna(subset=["hasHIndex"]).sort_values("hasHIndex", ascending=True).tail(15)

fig, ax = plt.subplots(figsize=(10, 6))
colors = {
    "Full Professor": "#3fb950", "Associate Professor": "#58a6ff",
    "Assistant Professor": "#f0883e", "Emeritus": "#8b949e",
}
bar_colors = [colors.get(r, "#8b949e") for r in top15.get("hasRank", [])]
ax.barh(top15["hasName"], top15["hasHIndex"], color=bar_colors)
ax.set_xlabel("h-index")
ax.set_title("Top 15 Faculty by h-index")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
for rank, color in colors.items():
    ax.barh([], [], color=color, label=rank)
ax.legend(loc="lower right", fontsize=8)
plt.tight_layout()

# ── 3. Publications by venue (SQL) ────────────────────────────────
venue_df = sql("""
    SELECT hasVenue AS venue,
           COUNT(*) AS publications,
           ROUND(AVG(CAST(hasCitationCount AS DOUBLE)), 1) AS avg_citations
    FROM "Publication"
    WHERE hasVenue IS NOT NULL
    GROUP BY hasVenue ORDER BY avg_citations DESC
""")
print("\\nPublications by venue:")
print(venue_df.to_string(index=False))

# ── 4. Summary stats ─────────────────────────────────────────────
h_mean = faculty_df["hasHIndex"].mean()
h_max  = faculty_df["hasHIndex"].max()
pub_total = get_table("Publication")
print(f"\\nFaculty: {len(faculty_df)}, avg h-index: {h_mean:.1f}, max: {h_max:.0f}")
print(f"Publications: {len(pub_total)}")
result_df = venue_df  # surfaces in the Dataframes panel below
`;

interface Props {
  jobId: string;
}

interface SavedArtifact {
  name: string;
  type: "image" | "text";
}

export function ScriptRunner({ jobId }: Props) {
  const [code, setCode] = useState(ACADEMIC_STARTER);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExecuteResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [saved, setSaved] = useState<SavedArtifact[]>([]);
  const [open, setOpen] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function runScript() {
    if (running || !code.trim()) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await execute.run(code, 120);
      setResult(res);
      if (res.error) setError(res.error);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  async function saveArtifact(
    name: string,
    type: "image" | "text",
    content: string,
    mimeType: string,
  ) {
    const key = `${type}:${name}`;
    setSaving(prev => ({ ...prev, [key]: true }));
    try {
      // Convert base64 to Blob for images, or text/plain for stdout
      let blob: Blob;
      if (type === "image") {
        const binary = atob(content);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        blob = new Blob([bytes], { type: mimeType });
      } else {
        blob = new Blob([content], { type: mimeType });
      }

      const form = new FormData();
      form.append("name", name);
      form.append("artifact_type", type === "image" ? "image" : "text");
      form.append("mime_type", mimeType);
      form.append("file", blob, name);

      const res = await fetch(`${API_BASE}/jobs/${jobId}/artifacts`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(await res.text());
      setSaved(prev => [...prev, { name, type }]);
    } catch (e) {
      console.error("Save artifact failed:", e);
    } finally {
      setSaving(prev => ({ ...prev, [key]: false }));
    }
  }

  async function saveStdout() {
    if (!result?.stdout) return;
    await saveArtifact("output.txt", "text", result.stdout, "text/plain");
  }

  const dataframeNames = result ? Object.keys(result.dataframes ?? {}) : [];

  return (
    <section className="space-y-3">
      {/* Header */}
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-2 text-sm font-semibold uppercase tracking-wide text-[--muted-foreground] hover:text-[--foreground] transition-colors"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Terminal size={14} />
        Script Runner
        <span className="ml-2 text-[10px] font-normal text-[--muted-foreground] normal-case tracking-normal">
          Python runs with access to{" "}
          <code className="font-mono text-[--foreground]">sql()</code>,{" "}
          <code className="font-mono text-[--foreground]">get_table()</code>,{" "}
          <code className="font-mono text-[--foreground]">pd</code>,{" "}
          <code className="font-mono text-[--foreground]">plt</code>
        </span>
      </button>

      {open && (
        <div className="space-y-3">
          {/* Editor */}
          <div className="relative rounded-xl border border-[--border] overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-[--muted]/50 border-b border-[--border]">
              <span className="text-[11px] text-[--muted-foreground] font-mono">analysis.py</span>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-[--muted-foreground]">⌘↵ to run</span>
                <button
                  onClick={runScript}
                  disabled={running || !code.trim()}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all",
                    running || !code.trim()
                      ? "bg-[--muted-foreground]/20 text-[--muted-foreground] cursor-not-allowed"
                      : "bg-[--primary] text-[--primary-foreground] hover:opacity-90"
                  )}
                >
                  {running
                    ? <><Loader2 size={12} className="animate-spin" /> Running…</>
                    : <><Play size={12} /> Run</>
                  }
                </button>
              </div>
            </div>
            <textarea
              ref={textareaRef}
              value={code}
              onChange={e => setCode(e.target.value)}
              onKeyDown={e => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                  e.preventDefault();
                  runScript();
                }
              }}
              spellCheck={false}
              rows={20}
              className="w-full bg-[#0d1117] px-4 py-3 font-mono text-xs text-[--foreground] focus:outline-none resize-none leading-relaxed"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-red-700/60 bg-red-900/20 p-3 font-mono text-xs text-red-300 whitespace-pre-wrap">
              {error}
            </div>
          )}

          {/* Results */}
          {result && !error && (
            <div className="space-y-4">
              {/* Stdout */}
              {result.stdout && (
                <div className="rounded-xl border border-[--border] overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 bg-[--muted]/40 border-b border-[--border]">
                    <span className="text-xs font-medium text-[--muted-foreground]">stdout</span>
                    <SaveButton
                      saved={saved.some(a => a.name === "output.txt")}
                      saving={saving["text:output.txt"]}
                      onClick={saveStdout}
                    />
                  </div>
                  <pre className="p-3 font-mono text-xs text-[--foreground] max-h-64 overflow-y-auto whitespace-pre-wrap">
                    {result.stdout}
                  </pre>
                </div>
              )}

              {/* Figures */}
              {result.figures && result.figures.length > 0 && (
                <div className="space-y-3">
                  {result.figures.map((fig, i) => {
                    const name = `figure_${i + 1}.png`;
                    const key = `image:${name}`;
                    return (
                      <div key={i} className="rounded-xl border border-[--border] overflow-hidden">
                        <div className="flex items-center justify-between px-3 py-2 bg-[--muted]/40 border-b border-[--border]">
                          <span className="text-xs font-medium text-[--muted-foreground]">{name}</span>
                          <div className="flex items-center gap-2">
                            <a
                              href={`data:image/png;base64,${fig}`}
                              download={name}
                              className="flex items-center gap-1 text-[10px] text-[--muted-foreground] hover:text-[--foreground]"
                            >
                              <Download size={11} /> Download
                            </a>
                            <SaveButton
                              saved={saved.some(a => a.name === name)}
                              saving={saving[key]}
                              onClick={() => saveArtifact(name, "image", fig, "image/png")}
                            />
                          </div>
                        </div>
                        <img
                          src={`data:image/png;base64,${fig}`}
                          alt={name}
                          className="max-w-full"
                        />
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Dataframes */}
              {dataframeNames.length > 0 && (
                <div className="space-y-3">
                  {dataframeNames.map(dfName => {
                    const df = result.dataframes[dfName];
                    return (
                      <div key={dfName} className="rounded-xl border border-[--border] overflow-hidden">
                        <div className="flex items-center justify-between px-3 py-2 bg-[--muted]/40 border-b border-[--border]">
                          <span className="text-xs font-medium text-[--muted-foreground]">
                            {dfName}{" "}
                            <span className="text-[--muted-foreground]/60">
                              ({df.rowCount} rows × {df.columns.length} cols)
                            </span>
                          </span>
                        </div>
                        <div className="overflow-x-auto max-h-72">
                          <table className="w-full text-xs border-collapse">
                            <thead className="sticky top-0 bg-[--muted]">
                              <tr>
                                {df.columns.map(c => (
                                  <th key={c} className="border-b border-[--border] px-3 py-2 text-left text-[--muted-foreground] font-medium whitespace-nowrap">
                                    {c}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {df.rows.slice(0, 50).map((row, i) => (
                                <tr key={i} className="border-b border-[--border]/40 hover:bg-[--muted]/20">
                                  {df.columns.map(c => (
                                    <td key={c} className="px-3 py-1.5 text-[--foreground] whitespace-nowrap max-w-xs truncate">
                                      {String(row[c] ?? "")}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {df.rows.length > 50 && (
                            <p className="px-3 py-2 text-[10px] text-[--muted-foreground]">
                              Showing 50 of {df.rowCount} rows
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Saved confirmation */}
              {saved.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {saved.map(a => (
                    <span key={a.name} className="flex items-center gap-1 px-2 py-1 rounded-full border border-green-700/40 bg-green-900/20 text-[10px] text-green-400">
                      <Save size={10} /> {a.name} saved to job
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function SaveButton({
  saved,
  saving,
  onClick,
}: {
  saved: boolean;
  saving?: boolean;
  onClick: () => void;
}) {
  if (saved) {
    return (
      <span className="flex items-center gap-1 text-[10px] text-green-400">
        <Save size={11} /> Saved
      </span>
    );
  }
  return (
    <button
      onClick={onClick}
      disabled={saving}
      className="flex items-center gap-1 text-[10px] text-[--muted-foreground] hover:text-[--primary] disabled:opacity-40 transition-colors"
    >
      {saving ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
      Save to Job
    </button>
  );
}
