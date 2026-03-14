"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { useState } from "react";
import { jobs } from "@/lib/api";

export default function PipelinesPage() {
  const pipelines = useQuery(api.configs.listPipelines, {});
  const [triggering, setTriggering] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ slug: string; text: string; ok: boolean } | null>(null);

  async function trigger(slug: string) {
    setTriggering(slug); setMsg(null);
    try {
      const res = await jobs.trigger(slug);
      setMsg({ slug, text: `Job ${res.jobId} queued`, ok: true });
    } catch (e) {
      setMsg({ slug, text: String(e), ok: false });
    } finally { setTriggering(null); }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">Pipelines</h1>
      {pipelines === undefined && <p className="text-[--muted-foreground] text-sm">Loading…</p>}
      {pipelines?.length === 0 && (
        <div className="flex items-center justify-center h-48 border border-dashed border-[--border] rounded-lg text-[--muted-foreground] text-sm">
          No pipeline configs yet.
        </div>
      )}
      <div className="grid gap-4">
        {pipelines?.map((p) => (
          <div key={p._id} className="p-5 rounded-lg border border-[--border] bg-[--card]">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="font-medium">{p.name}</h3>
                <p className="text-xs font-mono text-[--muted-foreground] mt-0.5">{p.slug}</p>
              </div>
              <button
                onClick={() => trigger(p.slug)}
                disabled={triggering === p.slug}
                className="px-4 py-1.5 rounded bg-[--primary] text-[--primary-foreground] text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {triggering === p.slug ? "Triggering…" : "▶ Run"}
              </button>
            </div>

            {p.referencedApiSlugs.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {p.referencedApiSlugs.map((slug) => (
                  <span key={slug} className="text-[10px] px-1.5 py-0.5 rounded bg-[--muted] text-[--muted-foreground] font-mono">{slug}</span>
                ))}
              </div>
            )}

            {msg?.slug === p.slug && (
              <p className={`text-xs mt-2 ${msg.ok ? "text-green-400" : "text-red-400"}`}>{msg.text}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
