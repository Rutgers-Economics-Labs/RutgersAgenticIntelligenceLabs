"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { use, useState } from "react";
import { jobs } from "@/lib/api";
import { ScheduleModal } from "@/components/schedules/ScheduleModal";
import { Badge } from "@/components/ui/badge";

export default function PipelinesPage({ params }: { params: Promise<{ project: string }> }) {
  const { project: projectSlug } = use(params);
  const pipelines = useQuery(api.configs.listPipelines, {});
  const schedules = useQuery(api.schedules.listByProject, { projectSlug });

  const [triggering, setTriggering] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ slug: string; text: string; ok: boolean } | null>(null);

  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);
  const [selectedPipelineForSchedule, setSelectedPipelineForSchedule] = useState<string | undefined>();
  const [existingScheduleForModal, setExistingScheduleForModal] = useState<any>();

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
    <div className="p-10 pb-20 max-w-6xl mx-auto w-full">
      <h1 className="text-2xl font-semibold mb-6">Pipelines</h1>
      {pipelines === undefined && <p className="text-[--muted-foreground] text-sm">Loading…</p>}
      {pipelines?.length === 0 && (
        <div className="flex items-center justify-center h-48 border border-dashed border-[--border] rounded-lg text-[--muted-foreground] text-sm">
          No pipeline configs yet.
        </div>
      )}
      <div className="grid gap-4">
        {pipelines?.map((p) => {
          const activeSchedule = schedules?.find((s: any) => s.pipelineSlug === p.slug && s.status === "active");

          return (
            <div key={p._id} className="p-5 rounded-lg border border-[--border] bg-[--card]">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div>
                    <h3 className="font-medium">{p.name}</h3>
                    <p className="text-xs font-mono text-[--muted-foreground] mt-0.5">{p.slug}</p>
                  </div>
                  {activeSchedule && (
                    <Badge variant="outline" className="text-green-400 border-green-400">
                      ● Collecting · {activeSchedule.frequency}
                    </Badge>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setSelectedPipelineForSchedule(p.slug);
                      setExistingScheduleForModal(schedules?.find((s: any) => s.pipelineSlug === p.slug));
                      setIsScheduleModalOpen(true);
                    }}
                    className="px-4 py-1.5 rounded border border-[--border] bg-transparent text-[--foreground] text-sm font-medium hover:bg-[--muted] transition-colors"
                  >
                    Schedule
                  </button>
                  <button
                    onClick={() => trigger(p.slug)}
                    disabled={triggering === p.slug}
                    className="px-4 py-1.5 rounded bg-[--primary] text-[--primary-foreground] text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
                  >
                    {triggering === p.slug ? "Triggering…" : "▶ Run"}
                  </button>
                </div>
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
          );
        })}
      </div>

      <ScheduleModal
        isOpen={isScheduleModalOpen}
        onClose={() => setIsScheduleModalOpen(false)}
        projectSlug={projectSlug}
        pipelineSlug={selectedPipelineForSchedule}
        existingSchedule={existingScheduleForModal}
        onSuccess={() => {}}
      />
    </div>
  );
}
