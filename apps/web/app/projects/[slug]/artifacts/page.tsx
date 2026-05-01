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
  const promotionCounts = (summary.promotionStateCounts ?? {}) as Record<string, number>;
  const verificationCounts = (summary.verificationStatusCounts ?? {}) as Record<string, number>;

  const rightRail = (
    <div>
      <SectionCard eyebrow="Artifacts" noPad>
        <InlineStatus label="total" value={artifacts.length} />
        <InlineStatus label="stale" value={Number(summary.staleCount ?? 0)} />
        {Object.entries(typeCounts).map(([type, count]) => (
          <InlineStatus key={type} label={type} value={count} />
        ))}
      </SectionCard>
      <SectionCard eyebrow="Promotion" noPad>
        {Object.entries(promotionCounts).length ? (
          Object.entries(promotionCounts).map(([state, count]) => (
            <InlineStatus key={state} label={state} value={count} />
          ))
        ) : (
          <div className="empty-state">No lineage states yet.</div>
        )}
      </SectionCard>
      <SectionCard eyebrow="Verification" noPad>
        {Object.entries(verificationCounts).length ? (
          Object.entries(verificationCounts).map(([state, count]) => (
            <InlineStatus key={state} label={state} value={count} />
          ))
        ) : (
          <div className="empty-state">No verification state yet.</div>
        )}
      </SectionCard>
    </div>
  );

  return (
    <ProjectShell slug={slug} title="Artifacts" section="artifacts" rightRail={rightRail}>
      <SectionCard eyebrow="Artifact Previews" noPad>
        {artifacts.length ? (
          artifacts.map((artifact) => <ArtifactPreview key={artifact.path} slug={slug} artifact={artifact} />)
        ) : (
          <div className="empty-state">Reports, tables, charts, decks, and dashboards will appear here.</div>
        )}
      </SectionCard>
    </ProjectShell>
  );
}
