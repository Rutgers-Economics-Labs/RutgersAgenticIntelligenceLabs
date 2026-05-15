import type {
  AgentWorkflowSection,
  AgentWorkflowSummary,
  ProjectArtifact,
  ProjectSource,
} from "./types.ts";

type DisplayTone = "trusted" | "blocked" | "stale" | "fresh" | "warning" | "neutral";

export type IntegrityDisplay = {
  label: string;
  tone: DisplayTone;
  detail: string;
};

export type WorkflowDisplaySection = {
  key: keyof AgentWorkflowSummary;
  label: string;
  status: string;
  blockerCount: number;
  blockers: string[];
  requirements: string[];
};

function normalizeLabel(value: string | undefined | null, fallback: string): string {
  return (value ?? fallback).replaceAll("_", " ");
}

export function getArtifactTrustDisplay(artifact: Pick<ProjectArtifact, "trustState" | "promotionState" | "verificationStatus" | "staleReasons">): IntegrityDisplay {
  const trustState = artifact.trustState;
  const promotion = normalizeLabel(artifact.promotionState, "exploratory");
  const verification = normalizeLabel(artifact.verificationStatus, "unverified");

  if (trustState?.isBlocked) {
    return {
      label: "blocked",
      tone: "blocked",
      detail: `Blocked by ${promotion} state; verification ${verification}.`,
    };
  }
  if (trustState?.isStale) {
    const staleCount = artifact.staleReasons?.length ?? 0;
    return {
      label: "stale",
      tone: "stale",
      detail: staleCount ? `Stale with ${staleCount} dependency warning${staleCount === 1 ? "" : "s"}.` : `Marked ${promotion}.`,
    };
  }
  if (trustState?.isTrusted) {
    return {
      label: "trusted",
      tone: "trusted",
      detail: `Verified and passed; promotion ${promotion}.`,
    };
  }
  return {
    label: "untrusted",
    tone: "neutral",
    detail: `Promotion ${promotion}; verification ${verification}.`,
  };
}

export function getSourceFreshnessDisplay(source: Pick<ProjectSource, "sourceState" | "freshnessStatus" | "qualityStatus">): IntegrityDisplay {
  const state = source.sourceState;
  const freshness = normalizeLabel(state?.freshnessStatus ?? source.freshnessStatus, "unknown");
  const quality = normalizeLabel(state?.qualityStatus ?? source.qualityStatus, "candidate");

  if (state?.isBlocked || quality === "blocked" || quality === "rejected") {
    return {
      label: "blocked",
      tone: "blocked",
      detail: `Quality ${quality}; freshness ${freshness}.`,
    };
  }
  if (state?.isStale || freshness === "stale") {
    return {
      label: "stale",
      tone: "stale",
      detail: `Freshness ${freshness}; quality ${quality}.`,
    };
  }
  if (state?.needsRefresh || freshness === "needs refresh") {
    return {
      label: "needs refresh",
      tone: "warning",
      detail: `Freshness ${freshness}; quality ${quality}.`,
    };
  }
  if (state?.isFresh || freshness === "fresh") {
    return {
      label: "fresh",
      tone: "fresh",
      detail: `Freshness ${freshness}; quality ${quality}.`,
    };
  }
  return {
    label: freshness,
    tone: "neutral",
    detail: `Quality ${quality}.`,
  };
}

function workflowBlockers(sectionKey: keyof AgentWorkflowSummary, section: AgentWorkflowSection): string[] {
  switch (sectionKey) {
    case "data":
      return [
        ...(section.datasetsMissingProvenance ?? []).map((item) => `missing provenance: ${item}`),
        ...(section.datasetsMissingFreshness ?? []).map((item) => `missing freshness: ${item}`),
      ];
    case "coding":
      return [
        ...(section.artifactsMissingLineage ?? []).map((item) => `missing lineage: ${item}`),
        ...(section.artifactsMissingVerificationCommands ?? []).map((item) => `missing verification commands: ${item}`),
        ...(section.artifactsMissingVerification ?? []).map((item) => `missing verification run: ${item}`),
      ];
    case "artifact":
      return (section.artifactsWithUnsupportedClaims ?? []).map((item) => `unsupported claims: ${item}`);
    case "health":
      return [
        ...(section.missingEvidenceClaims ?? []).map((item) => `missing evidence: ${item}`),
        ...(section.staleSources ?? []).map((item) => `stale source: ${item}`),
        ...(section.reproducibilityGaps ?? []).map((item) => `reproducibility gap: ${item}`),
        ...(section.failedVerificationRuns ?? []).map((item) => `failed verification: ${item}`),
      ];
    case "research":
      return [];
  }
}

export function getWorkflowDisplaySections(agentWorkflow: AgentWorkflowSummary): WorkflowDisplaySection[] {
  return [
    ["research", "Research"],
    ["data", "Data"],
    ["coding", "Coding"],
    ["artifact", "Artifact"],
    ["health", "Health"],
  ].map(([key, label]) => {
    const sectionKey = key as keyof AgentWorkflowSummary;
    const section = agentWorkflow[sectionKey];
    const blockers = workflowBlockers(sectionKey, section);
    return {
      key: sectionKey,
      label,
      status: section.status,
      blockerCount: blockers.length,
      blockers,
      requirements: section.requirements,
    };
  });
}
