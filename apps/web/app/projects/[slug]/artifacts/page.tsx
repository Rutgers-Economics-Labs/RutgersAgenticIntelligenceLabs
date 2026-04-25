import { fetchProjectArtifacts } from "@/lib/api";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { ArtifactPreview, InlineStatus } from "@/components/command-center";

export default async function ArtifactsPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { artifacts, summary } = await fetchProjectArtifacts(slug);
  const typeCounts = (summary.typeCounts ?? {}) as Record<string, number>;

  const rightRail = (
    <div>
      <SectionCard eyebrow="Artifacts" noPad>
        <InlineStatus label="total" value={artifacts.length} />
        {Object.entries(typeCounts).map(([type, count]) => (
          <InlineStatus key={type} label={type} value={count} />
        ))}
      </SectionCard>
    </div>
  );

  return (
    <ProjectShell slug={slug} title="Artifacts" section="artifacts" rightRail={rightRail}>
      <SectionCard eyebrow="Artifact Previews" noPad>
        {artifacts.length ? (
          artifacts.map((artifact) => <ArtifactPreview key={artifact.path} artifact={artifact} />)
        ) : (
          <div className="empty-state">Reports, tables, charts, decks, and dashboards will appear here.</div>
        )}
      </SectionCard>
    </ProjectShell>
  );
}
