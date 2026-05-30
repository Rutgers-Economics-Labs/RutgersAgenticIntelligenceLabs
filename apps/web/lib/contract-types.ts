/**
 * contract-types.ts
 * TypeScript type definitions mirroring RAIL runner contract Pydantic models.
 * 
 * Source Pydantic models:
 * - WorkOrder: packages/api/app/runners/contracts/work_order.py
 * - SessionResult: packages/api/app/runners/contracts/session_result.py
 */

export type TaskType =
  | "data_ingestion"
  | "analysis"
  | "source_discovery"
  | "artifact_writing"
  | "health_repair"
  | "claim_extraction"
  | "verification";

export type Capability =
  | "edit_files"
  | "run_shell"
  | "fetch_remote_data"
  | "query_duckdb"
  | "execute_python"
  | "use_mcp_tools"
  | "browse_web"
  | "extract_pdf_tables"
  | "write_long_artifacts"
  | "handle_large_context"
  | "write_structured_output";

export interface TrustPolicy {
  output_trust_state: string;
  promotion_requires: string[];
}

export interface FailurePolicy {
  max_attempts: number;
  if_no_progress: string;
}

export interface ExpectedProgress {
  one_of: string[];
}

export interface WorkOrder {
  work_order_id: string;
  project_slug: string;
  task_type: TaskType;
  phase?: string | null;
  expected_progress?: ExpectedProgress;
  failure_policy?: FailurePolicy;
  idempotency_key?: string | null;
  input_hash?: string | null;
  capabilities_required: Capability[];
  runner_preferred?: string | null;
  runner_allowed?: string[] | null;
  allowed_paths: string[];
  inputs?: Record<string, string>;
  outputs_required?: string[];
  trust_policy?: TrustPolicy;
  cost_budget_usd?: number | null;
  wall_time_budget_minutes?: number | null;
  questions_allowed?: boolean;
  depends_on?: string[];
  created_at?: string;
  created_by: string;
}

export type SessionStatus =
  | "completed"
  | "failed"
  | "cancelled"
  | "blocked"
  | "needs_followup";

export type TrustState =
  | "draft"
  | "candidate"
  | "analysis_ready"
  | "partially_verified"
  | "verified"
  | "rejected"
  | "blocked_for_promotion"
  | "superseded";

export type SourceMaterializationState =
  | "candidate"
  | "admissible"
  | "configured"
  | "fetchable"
  | "fetched_extract"
  | "normalized_dataset"
  | "hydrated_dataset"
  | "analysis_ready_dataset"
  | "trusted_evidence_source";

export interface ClaimCandidate {
  claim_id: string;
  text: string;
  status: TrustState;
  evidence_refs?: string[];
  verification_status?: string;
  confidence?: number | null;
  notes?: string | null;
}

export interface SourceRecord {
  source_id: string;
  name: string;
  provider?: string | null;
  access_url?: string | null;
  access_method?: string | null;
  admissibility?: string;
  materialization_state?: SourceMaterializationState;
  materialized_path?: string | null;
  notes?: string | null;
}

export interface DatasetRecord {
  dataset_id: string;
  file_path: string;
  source_ids?: string[];
  row_count?: number | null;
  schema_summary?: string | null;
}

export interface Blocker {
  blocker_id?: string | null;
  category: string;
  summary: string;
  detail?: string | null;
  recommended_followup?: string | null;
  severity?: string | null;
  blocks?: string[];
  does_not_block?: string[];
  owner_lane?: string | null;
  allowed_resolutions?: string[];
  max_repair_attempts?: number | null;
  next_action?: string | null;
}

export interface VerificationRequest {
  command: string;
  expected_outputs?: string[];
  claims_to_verify?: string[];
}

export interface RecommendedTask {
  task_type: TaskType;
  reason: string;
  capabilities_hint?: string[];
}

export interface DomainProgress {
  new_sources?: number;
  new_datasets?: number;
  new_claim_candidates?: number;
  new_analysis_artifacts?: number;
  new_verified_claims?: number;
}

export interface TrustChange {
  object_type: string;
  object_id: string;
  from: string;
  to: string;
}

export interface SessionResult {
  session_id: string;
  work_order_id?: string | null;
  status: SessionStatus;
  summary: string;
  task_type: TaskType;
  runner_name: string;
  files_changed?: string[];
  claims?: ClaimCandidate[];
  sources?: SourceRecord[];
  datasets?: DatasetRecord[];
  blockers?: Blocker[];
  domain_progress?: DomainProgress;
  trust_changes?: TrustChange[];
  promotion_blockers?: string[];
  research_blockers?: string[];
  questions_asked?: string[];
  verification?: VerificationRequest | null;
  next_recommended_tasks?: RecommendedTask[];
  cost_recorded_usd?: number | null;
  duration_seconds?: number | null;
  completed_at?: string;
}

export interface DispatchDecision {
  work_order_id: string;
  selected_runner: string | null;
  timestamp: string;
  override: boolean;
  error?: string | null;
  eligible_scores?: Record<string, number>;
  rejection_reasons?: Record<string, string>;
}
