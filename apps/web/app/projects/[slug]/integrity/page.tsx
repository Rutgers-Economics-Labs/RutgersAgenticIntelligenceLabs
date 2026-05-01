import Link from "next/link";
import { fetchProjectIntegrity } from "@/lib/api";
import { InlineStatus } from "@/components/command-center";
import { ProjectShell } from "@/components/project-shell";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { IntegrityAssumptionsPanel } from "@/components/integrity-assumptions-panel";

function RepoLink({ slug, path, label }: { slug: string; path: string; label?: string }) {
  return (
    <Link href={`/projects/${slug}/repo?path=${encodeURIComponent(path)}`}>
      {label ?? path}
    </Link>
  );
}

function EmptyStateRow({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

export default async function IntegrityPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { indexes, summary, staleOutputs } = await fetchProjectIntegrity(slug);

  const rightRail = (
    <div>
      <SectionCard eyebrow="Integrity" noPad>
        <InlineStatus label="assumptions" value={summary.assumptionCount} />
        <InlineStatus label="sources" value={summary.sourceCount} />
        <InlineStatus label="claims" value={summary.claimCount} />
        <InlineStatus label="artifacts" value={summary.artifactCount} />
        <InlineStatus label="verification" value={summary.verificationRunCount} />
        <InlineStatus label="stale" value={summary.staleArtifactCount} />
      </SectionCard>
    </div>
  );

  return (
    <ProjectShell slug={slug} title="Integrity" section="integrity" rightRail={rightRail}>
      <SectionCard eyebrow="Assumptions" noPad>
        <div id="assumptions" className="integrity-section">
          <IntegrityAssumptionsPanel
            slug={slug}
            assumptions={indexes.assumptions}
            artifactLineage={indexes.artifact_lineage}
          />
        </div>
      </SectionCard>

      <SectionCard eyebrow="Provenance / Sources" noPad>
        <div id="sources" className="integrity-section">
          {indexes.sources.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Type</th>
                  <th>Quality</th>
                  <th>Path</th>
                </tr>
              </thead>
              <tbody>
                {indexes.sources.map((row) => (
                  <tr key={row.source_key}>
                    <td>
                      <strong>{row.title}</strong>
                      <div className="mono-muted">{row.url_or_path}</div>
                    </td>
                    <td>{row.source_type}</td>
                    <td><StatusPill value={row.quality_status} /></td>
                    <td className="mono-muted"><RepoLink slug={slug} path={row.source_path} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyStateRow text="No provenance records recorded yet." />
          )}
        </div>
      </SectionCard>

      <SectionCard eyebrow="Claim Evidence" noPad>
        <div id="claims" className="integrity-section">
          {indexes.claims.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Claim</th>
                  <th>Status</th>
                  <th>Evidence</th>
                  <th>Artifact</th>
                </tr>
              </thead>
              <tbody>
                {indexes.claims.map((row) => (
                  <tr key={row.claim_key}>
                    <td>
                      <strong>{row.claim_key}</strong>
                      <div>{row.claim_text}</div>
                    </td>
                    <td><StatusPill value={row.status} /></td>
                    <td className="mono-muted">{row.evidence_paths.join(", ") || "—"}</td>
                    <td className="mono-muted">{row.artifact_path ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyStateRow text="No claim-evidence mappings recorded yet." />
          )}
        </div>
      </SectionCard>

      <SectionCard eyebrow="Artifact Lineage" noPad>
        <div id="lineage" className="integrity-section">
          {indexes.artifact_lineage.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Artifact</th>
                  <th>Promotion</th>
                  <th>Inputs</th>
                  <th>Verification</th>
                </tr>
              </thead>
              <tbody>
                {indexes.artifact_lineage.map((row) => (
                  <tr key={row.artifact_path}>
                    <td>
                      <strong>{row.title}</strong>
                      <div className="mono-muted">{row.artifact_path}</div>
                    </td>
                    <td><StatusPill value={row.promotion_state} /></td>
                    <td className="mono-muted">{row.inputs.join(", ") || "—"}</td>
                    <td className="mono-muted">{row.verification_runs.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyStateRow text="No artifact lineage records recorded yet." />
          )}
        </div>
      </SectionCard>

      <SectionCard eyebrow="Verification Status" noPad>
        <div id="verification" className="integrity-section">
          {indexes.verification_runs.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Artifacts</th>
                  <th>Blockers</th>
                </tr>
              </thead>
              <tbody>
                {indexes.verification_runs.map((row) => (
                  <tr key={row.run_id}>
                    <td>
                      <strong>{row.run_id}</strong>
                      <div className="mono-muted"><RepoLink slug={slug} path={row.source_path} /></div>
                    </td>
                    <td><StatusPill value={row.status} /></td>
                    <td className="mono-muted">{row.artifact_paths.join(", ") || "—"}</td>
                    <td className="mono-muted">{row.blockers.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyStateRow text="No verification runs recorded yet." />
          )}
        </div>
      </SectionCard>

      <SectionCard eyebrow="Stale Outputs" noPad>
        <div id="stale-outputs" className="integrity-section">
          {staleOutputs.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Artifact</th>
                  <th>Reasons</th>
                  <th>Marked</th>
                </tr>
              </thead>
              <tbody>
                {staleOutputs.map((row) => (
                  <tr key={row.artifact_path}>
                    <td>
                      <strong>{row.title}</strong>
                      <div className="mono-muted">{row.artifact_path}</div>
                    </td>
                    <td className="mono-muted">{row.stale_reasons.join(", ") || "—"}</td>
                    <td>{row.stale_marked_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyStateRow text="No stale outputs detected." />
          )}
        </div>
      </SectionCard>
    </ProjectShell>
  );
}
