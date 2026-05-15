import test from "node:test";
import assert from "node:assert/strict";

import {
  getArtifactTrustDisplay,
  getSourceFreshnessDisplay,
  getWorkflowDisplaySections,
} from "../lib/integrity-ui.ts";
import type { AgentWorkflowSummary, ProjectArtifact, ProjectSource } from "../lib/types.ts";

test("artifact trust display uses normalized trustState for trusted, stale, and blocked artifacts", () => {
  const trustedArtifact: ProjectArtifact = {
    name: "brief.md",
    path: "artifacts/brief.md",
    type: "markdown",
    sizeBytes: 10,
    modifiedAt: 1,
    previewable: true,
    promotionState: "verified",
    verificationStatus: "passed",
    trustState: { isTrusted: true, isBlocked: false, isStale: false },
  };
  const staleArtifact: ProjectArtifact = {
    ...trustedArtifact,
    path: "artifacts/stale.md",
    promotionState: "stale",
    trustState: { isTrusted: false, isBlocked: false, isStale: true },
    staleReasons: ["upstream source changed"],
  };
  const blockedArtifact: ProjectArtifact = {
    ...trustedArtifact,
    path: "artifacts/blocked.md",
    promotionState: "needs_evidence",
    verificationStatus: "blocked",
    trustState: { isTrusted: false, isBlocked: true, isStale: false },
  };

  assert.deepEqual(getArtifactTrustDisplay(trustedArtifact), {
    label: "trusted",
    tone: "trusted",
    detail: "Verified and passed; promotion verified.",
  });
  assert.deepEqual(getArtifactTrustDisplay(staleArtifact), {
    label: "stale",
    tone: "stale",
    detail: "Stale with 1 dependency warning.",
  });
  assert.deepEqual(getArtifactTrustDisplay(blockedArtifact), {
    label: "blocked",
    tone: "blocked",
    detail: "Blocked by needs evidence state; verification blocked.",
  });
});

test("source freshness display uses sourceState and freshness metadata directly", () => {
  const freshSource: ProjectSource = {
    id: "fred",
    name: "FRED",
    publisher: "Federal Reserve",
    provider: "fred",
    status: "validated",
    accessMethod: "api",
    geography: "",
    timeCoverage: "",
    updateFrequency: "",
    keyFields: [],
    qualityNotes: "",
    linkedFiles: [],
    freshnessStatus: "fresh",
    qualityStatus: "validated",
    sourceState: {
      freshnessStatus: "fresh",
      qualityStatus: "validated",
      isFresh: true,
      isStale: false,
      needsRefresh: false,
      isBlocked: false,
    },
  };
  const staleSource: ProjectSource = {
    ...freshSource,
    id: "bls",
    freshnessStatus: "stale",
    sourceState: {
      freshnessStatus: "stale",
      qualityStatus: "validated",
      isFresh: false,
      isStale: true,
      needsRefresh: false,
      isBlocked: false,
    },
  };
  const blockedSource: ProjectSource = {
    ...freshSource,
    id: "manual",
    freshnessStatus: "needs_refresh",
    qualityStatus: "blocked",
    sourceState: {
      freshnessStatus: "needs_refresh",
      qualityStatus: "blocked",
      isFresh: false,
      isStale: false,
      needsRefresh: true,
      isBlocked: true,
    },
  };

  assert.equal(getSourceFreshnessDisplay(freshSource).label, "fresh");
  assert.equal(getSourceFreshnessDisplay(staleSource).label, "stale");
  assert.deepEqual(getSourceFreshnessDisplay(blockedSource), {
    label: "blocked",
    tone: "blocked",
    detail: "Quality blocked; freshness needs refresh.",
  });
});

test("source freshness display prefers normalized sourceState when raw fields conflict", () => {
  const conflictingSource: ProjectSource = {
    id: "conflict",
    name: "Conflicting Source",
    publisher: "Provider",
    provider: "provider",
    status: "validated",
    accessMethod: "api",
    geography: "",
    timeCoverage: "",
    updateFrequency: "",
    keyFields: [],
    qualityNotes: "",
    linkedFiles: [],
    freshnessStatus: "fresh",
    qualityStatus: "validated",
    sourceState: {
      freshnessStatus: "stale",
      qualityStatus: "blocked",
      isFresh: false,
      isStale: true,
      needsRefresh: false,
      isBlocked: true,
    },
  };

  assert.deepEqual(getSourceFreshnessDisplay(conflictingSource), {
    label: "blocked",
    tone: "blocked",
    detail: "Quality blocked; freshness stale.",
  });
});

test("workflow display sections flatten repo-backed blocker lists for data, coding, artifact, and health", () => {
  const workflow: AgentWorkflowSummary = {
    research: {
      status: "ready",
      requirements: ["Separate facts from interpretation."],
    },
    data: {
      status: "blocked",
      requirements: ["Datasets must retain source provenance and freshness metadata."],
      datasetsMissingProvenance: ["artifacts/raw.csv"],
      datasetsMissingFreshness: ["artifacts/derived.csv"],
    },
    coding: {
      status: "blocked",
      requirements: ["Analysis outputs must declare inputs and scripts."],
      artifactsMissingLineage: ["artifacts/model.md"],
      artifactsMissingVerificationCommands: ["artifacts/model.md"],
      artifactsMissingVerification: ["artifacts/model.md"],
    },
    artifact: {
      status: "blocked",
      requirements: ["Artifacts with unsupported claims cannot be treated as trusted."],
      artifactsWithUnsupportedClaims: ["artifacts/memo.md"],
    },
    health: {
      status: "blocked",
      requirements: ["Detect missing evidence, stale sources, and reproducibility gaps."],
      missingEvidenceClaims: ["claim-1"],
      staleSources: ["source-1"],
      reproducibilityGaps: ["artifacts/model.md"],
      failedVerificationRuns: ["run-1"],
    },
  };

  const sections = getWorkflowDisplaySections(workflow);
  const byKey = Object.fromEntries(sections.map((section) => [section.key, section]));

  assert.equal(byKey.data.blockerCount, 2);
  assert.deepEqual(byKey.data.blockers, [
    "missing provenance: artifacts/raw.csv",
    "missing freshness: artifacts/derived.csv",
  ]);
  assert.equal(byKey.coding.blockerCount, 3);
  assert.deepEqual(byKey.artifact.blockers, ["unsupported claims: artifacts/memo.md"]);
  assert.deepEqual(byKey.health.blockers, [
    "missing evidence: claim-1",
    "stale source: source-1",
    "reproducibility gap: artifacts/model.md",
    "failed verification: run-1",
  ]);
});
