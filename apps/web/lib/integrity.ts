import { ArtifactLineageRecord, AssumptionRecord, IntegrityIndexes } from "@/lib/types";

function normalizeReferenceKey(reference: string): string {
  const parts = reference.split("#");
  return (parts[parts.length - 1] ?? "").trim();
}

export function findArtifactsAffectedByAssumption(
  artifactLineage: ArtifactLineageRecord[],
  assumptionKey: string,
): ArtifactLineageRecord[] {
  return artifactLineage.filter((artifact) =>
    artifact.assumptions.some((reference) => normalizeReferenceKey(reference) === assumptionKey),
  );
}

export function validateIntegrityIndexes(value: unknown): value is IntegrityIndexes {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    Array.isArray(candidate.assumptions) &&
    Array.isArray(candidate.sources) &&
    Array.isArray(candidate.claims) &&
    Array.isArray(candidate.artifact_lineage) &&
    Array.isArray(candidate.verification_runs)
  );
}

export function readIntegrityIndexes(value: unknown): IntegrityIndexes {
  if (!validateIntegrityIndexes(value)) {
    throw new Error("Invalid integrity indexes payload");
  }
  return value;
}

export function updateAssumptionRecord(
  indexes: IntegrityIndexes,
  updatedAssumption: AssumptionRecord,
): IntegrityIndexes {
  return {
    ...indexes,
    assumptions: indexes.assumptions.map((assumption) =>
      assumption.assumption_key === updatedAssumption.assumption_key ? updatedAssumption : assumption,
    ),
  };
}

export function summarizeIntegrityIndexes(indexes: IntegrityIndexes): {
  assumptionCount: number;
  sourceCount: number;
  claimCount: number;
  artifactCount: number;
  staleArtifactCount: number;
  verificationRunCount: number;
} {
  return {
    assumptionCount: indexes.assumptions.length,
    sourceCount: indexes.sources.length,
    claimCount: indexes.claims.length,
    artifactCount: indexes.artifact_lineage.length,
    staleArtifactCount: indexes.artifact_lineage.filter((artifact) => artifact.promotion_state === "stale").length,
    verificationRunCount: indexes.verification_runs.length,
  };
}

export function buildAffectedArtifactMap(
  assumptions: AssumptionRecord[],
  artifactLineage: ArtifactLineageRecord[],
): Record<string, string[]> {
  return Object.fromEntries(
    assumptions.map((assumption) => [
      assumption.assumption_key,
      findArtifactsAffectedByAssumption(artifactLineage, assumption.assumption_key).map((artifact) => artifact.artifact_path),
    ]),
  );
}

export function rebuildIntegrityIndexes(indexes: IntegrityIndexes): IntegrityIndexes {
  return {
    ...indexes,
    assumptions: [...indexes.assumptions],
    sources: [...indexes.sources],
    claims: [...indexes.claims],
    artifact_lineage: [...indexes.artifact_lineage],
    verification_runs: [...indexes.verification_runs],
  };
}
