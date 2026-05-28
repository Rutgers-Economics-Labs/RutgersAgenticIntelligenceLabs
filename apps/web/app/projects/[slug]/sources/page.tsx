import { fetchPlannerHome, fetchProjectSources } from "@/lib/api";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { PageIntro } from "@/components/page-intro";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { InlineStatus, SourceInventoryTable } from "@/components/command-center";

export default async function SourcesPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ status?: string; provider?: string }>;
}) {
  const { slug } = await params;
  const filters = await searchParams;
  const home = await fetchPlannerHome(slug);
  const sourceSummaryFallback = home.controlPlane?.sourceSummary ?? { count: 0, statusCounts: {} };
  const sourceResult = await fetchProjectSources(slug)
    .then((value) => ({ ok: true as const, value }))
    .catch(() => ({ ok: false as const }));
  const sources = sourceResult.ok ? sourceResult.value.sources : [];
  const summary = sourceResult.ok ? sourceResult.value.summary : sourceSummaryFallback;
  const notes = sourceResult.ok ? sourceResult.value.notes : undefined;
  const statusCounts = (summary.statusCounts ?? {}) as Record<string, number>;
  const filtered = sources.filter((source) => {
    if (filters.status && source.status !== filters.status) return false;
    if (filters.provider && source.provider !== filters.provider) return false;
    return true;
  });
  const providers = Array.from(new Set(sources.map((source) => source.provider).filter(Boolean)));

  const rightRail = (
    <div>
      <SectionCard eyebrow="Inventory" noPad>
        <InlineStatus label="sources" value={sources.length} />
        {Object.entries(statusCounts).map(([status, count]) => (
          <InlineStatus key={status} label={status.replaceAll("_", " ")} value={count} />
        ))}
      </SectionCard>
      <SectionCard eyebrow="Providers" noPad>
        {providers.length ? providers.map((provider) => <InlineStatus key={provider} label={provider} value={sources.filter((s) => s.provider === provider).length} />) : <div className="empty-state">None</div>}
      </SectionCard>
    </div>
  );

  return (
    <ProjectShell slug={slug} title="Sources" section="sources" rightRail={rightRail}>
      <PageIntro
        title="See what evidence exists and what still needs to be found."
        detail="This page is for source inventory, provider coverage, and source notes. Use it to audit evidence quality before you ask the planner to build new work on top of it."
        actions={[
          { label: "Open Dashboard", href: `/projects/${slug}/dashboard` },
          { label: "Open Integrity", href: `/projects/${slug}/integrity` },
        ]}
      />
      <SectionCard eyebrow="Source Inventory" title={`${filtered.length} shown`} noPad>
        {!sourceResult.ok && (
          <div className="empty-state" style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-subtle)" }}>
            Detailed source records are temporarily unavailable. This page is falling back to the repo-backed planner summary.
          </div>
        )}
        <SourceInventoryTable sources={filtered} />
      </SectionCard>
      {notes && (
        <SectionCard eyebrow="Source Notes">
          <MarkdownRenderer content={notes} />
        </SectionCard>
      )}
    </ProjectShell>
  );
}
