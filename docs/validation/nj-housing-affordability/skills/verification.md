# Verification

Use this skill when validating project outputs.

## Deterministic Verification
Run `scripts/run-verification.sh` to perform structural and data integrity checks. This includes row count validations, schema checks, file existence checks, placeholder-source detection, required-ledger checks, and analysis-readiness checks.

## Semantic Verification
Perform a manual (agentic) review of the content. Cross-check the "Claim Evidence" (`research_plan/claim_evidence.md`) against the final report. Ensure that no claim is made without a corresponding evidence record.

## State Transitions
- If verification passes: update `artifact_lineage.json` status to `verified` or `partially_verified`.
- If verification fails: mark as `blocked` and record the specific failure reason in `verification_runs.json`.

## Required Ledgers
Keep these repo-backed files current:
- `research_plan/assumptions.md`
- `research_plan/target_state.md`
- `research_plan/source_registry.md`
- `research_plan/data_gaps.md`
