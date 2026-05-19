import { getArtifactTrustDisplay, getSourceFreshnessDisplay, getWorkflowDisplaySections } from "./integrity-ui";
import type { IntegrityDisplay, WorkflowDisplaySection } from "./integrity-ui";
import type {
  ArtifactLineageRecord,
  ProjectIntegrityResponse,
  SourceRecord,
} from "./types.ts";

export type IntegritySourceRow = {
  sourceKey: string;
  title: string;
  sourceType: string;
  qualityStatus: string;
  freshness: IntegrityDisplay;
  urlOrPath: string;
  sourcePath: string;
};

export type IntegrityArtifactRow = {
  artifactPath: string;
  title: string;
  trust: IntegrityDisplay;
  promotionState: string;
  inputs: string[];
  verificationStatus: string;
  verificationRuns: string[];
};

function buildIntegritySourceRow(row: SourceRecord): IntegritySourceRow {
  const freshness = getSourceFreshnessDisplay({
    freshnessStatus: row.freshness_status,
    qualityStatus: row.quality_status,
    sourceState: row.sourceState,
  });
  return {
    sourceKey: row.source_key,
    title: row.title,
    sourceType: row.source_type,
    qualityStatus: row.sourceState?.qualityStatus ?? row.quality_status,
    freshness,
    urlOrPath: row.url_or_path,
    sourcePath: row.source_path,
  };
}

function buildIntegrityArtifactRow(row: ArtifactLineageRecord): IntegrityArtifactRow {
  const trust = getArtifactTrustDisplay({
    trustState: row.trustState,
    promotionState: row.promotion_state,
    verificationStatus: row.verificationStatus,
    staleReasons: row.stale_reasons,
  });
  return {
    artifactPath: row.artifact_path,
    title: row.title,
    trust,
    promotionState: row.promotion_state,
    inputs: row.inputs,
    verificationStatus: row.verificationStatus ?? "unverified",
    verificationRuns: row.verification_runs,
  };
}

export function buildIntegrityPageModel(response: ProjectIntegrityResponse): {
  sourceRows: IntegritySourceRow[];
  artifactRows: IntegrityArtifactRow[];
  workflowSections: WorkflowDisplaySection[];
} {
  return {
    sourceRows: response.indexes.sources.map(buildIntegritySourceRow),
    artifactRows: response.indexes.artifact_lineage.map(buildIntegrityArtifactRow),
    workflowSections: getWorkflowDisplaySections(response.agentWorkflow),
  };
}
