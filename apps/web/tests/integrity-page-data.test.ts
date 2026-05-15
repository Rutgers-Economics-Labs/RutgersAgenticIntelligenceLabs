import test from "node:test";
import assert from "node:assert/strict";

import { buildIntegrityPageModel } from "../lib/integrity-page.ts";
import type { ProjectIntegrityResponse } from "../lib/types.ts";

test("integrity page view model uses normalized source and artifact state from repo-backed integrity response", () => {
  const response: ProjectIntegrityResponse = {
    indexes: {
      assumptions: [],
      sources: [
        {
          source_key: "source-1",
          source_type: "document",
          title: "Regional Queue Brief",
          url_or_path: "topics/queue.md",
          freshness_status: "fresh",
          quality_status: "validated",
          sourceState: {
            freshnessStatus: "stale",
            qualityStatus: "blocked",
            isFresh: false,
            isStale: true,
            needsRefresh: false,
            isBlocked: true,
          },
          source_path: "research_plan/state/sources.json",
        },
      ],
      claims: [],
      artifact_lineage: [
        {
          artifact_path: "artifacts/report.md",
          artifact_type: "report",
          title: "Report",
          promotion_state: "verified",
          inputs: ["topics/data.csv"],
          scripts: ["topics/analyze.py"],
          sources: ["research_plan/state/sources.json#source-1"],
          assumptions: [],
          claims: [],
          verification_runs: ["research_plan/state/verification_runs.json#run-1"],
          verificationStatus: "failed",
          trustState: {
            isTrusted: false,
            isBlocked: true,
            isStale: false,
          },
          stale_reasons: [],
        },
      ],
      verification_runs: [],
    },
    summary: {
      assumptionCount: 0,
      sourceCount: 1,
      sourceFreshnessCounts: { stale: 1 },
      claimCount: 0,
      artifactCount: 1,
      staleArtifactCount: 0,
      verificationRunCount: 0,
      verificationStatusCounts: { failed: 1 },
      promotionStateCounts: { verified: 1 },
    },
    agentWorkflow: {
      research: { status: "ready", requirements: ["Separate facts from interpretation."] },
      data: {
        status: "blocked",
        requirements: ["Datasets must retain source provenance and freshness metadata."],
        datasetsMissingFreshness: ["topics/data.csv"],
      },
      coding: { status: "ready", requirements: ["Analysis outputs must declare inputs and scripts."] },
      artifact: { status: "ready", requirements: ["Artifacts with unsupported claims cannot be treated as trusted."] },
      health: { status: "ready", requirements: ["Detect missing evidence, stale sources, and reproducibility gaps."] },
    },
    staleOutputs: [],
  };

  const model = buildIntegrityPageModel(response);

  assert.equal(model.sourceRows[0].freshness.label, "blocked");
  assert.equal(model.sourceRows[0].freshness.detail, "Quality blocked; freshness stale.");
  assert.equal(model.artifactRows[0].trust.label, "blocked");
  assert.equal(model.artifactRows[0].trust.detail, "Blocked by verified state; verification failed.");
  assert.deepEqual(model.workflowSections.find((section) => section.key === "data")?.blockers, [
    "missing freshness: topics/data.csv",
  ]);
});
