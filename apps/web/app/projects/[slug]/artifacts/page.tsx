import { fetchPlannerHome, fetchProjectArtifacts } from "@/lib/api";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { PageIntro } from "@/components/page-intro";
import { ArtifactPreview, InlineStatus } from "@/components/command-center";

export default async function ArtifactsPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const home = await fetchPlannerHome(slug);
  const artifactResult = await fetchProjectArtifacts(slug)
    .then((value) => ({ ok: true as const, value }))
    .catch(() => ({ ok: false as const }));
  const artifacts = artifactResult.ok ? artifactResult.value.artifacts : home.controlPlane?.recentArtifacts ?? [];
  const summary = artifactResult.ok
    ? artifactResult.value.summary
    : {
        typeCounts: {},
        promotionStateCounts: {},
        verificationStatusCounts: {},
        staleCount: Number(home.controlPlane?.integritySummary?.staleArtifactCount ?? 0),
      };
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
      <PageIntro
        title="Browse the outputs this project has produced."
        detail="Artifacts are the things the research system created: reports, dashboards, tables, charts, and supporting files. Use Integrity when you want to check trust, lineage, or verification."
        actions={[
          { label: "Check Integrity", href: `/projects/${slug}/integrity` },
          { label: "Open Review", href: `/projects/${slug}/review` },
        ]}
      />
      <SectionCard eyebrow="Artifact Previews" noPad>
        {!artifactResult.ok && (
          <div className="empty-state" style={{ padding: "12px 16px", borderBottom: artifacts.length ? "1px solid var(--border-subtle)" : "none" }}>
            Detailed artifact inventory is temporarily unavailable. Showing repo-backed recent artifacts from the control-plane snapshot.
          </div>
        )}
        {artifacts.length ? (
          artifacts.map((artifact) => <ArtifactPreview key={artifact.path} slug={slug} artifact={artifact} />)
        ) : (
          <div className="empty-state">Reports, tables, charts, decks, and dashboards will appear here.</div>
        )}
      </SectionCard>
    </ProjectShell>
  );
}
