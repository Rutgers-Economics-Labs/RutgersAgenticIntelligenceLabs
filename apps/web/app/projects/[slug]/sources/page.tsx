import { fetchProjectSources } from "@/lib/api";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
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
  const { sources, summary, notes } = await fetchProjectSources(slug);
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
      <SectionCard eyebrow="Source Inventory" title={`${filtered.length} shown`} noPad>
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
