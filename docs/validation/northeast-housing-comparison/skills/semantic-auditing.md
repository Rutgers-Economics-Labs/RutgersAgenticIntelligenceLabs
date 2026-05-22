# Semantic Auditing

Use this skill to verify that generated reports and artifacts accurately reflect the evidence in the integrity ledger.

## Workflow

1.  **Extract Claims**: Identify the primary empirical claims in the artifact.
2.  **Cross-Reference**: For each claim, find the corresponding `ClaimRecord` in `research_plan/state/claims.json`.
3.  **Trace Evidence**: Verify that the `evidence_paths` and `source_keys` for that claim actually support the statement made in the artifact.
4.  **Check for Hallucinations**: Ensure no numbers or specific findings in the report are missing from the underlying sources.
5.  **Audit Citations**: Confirm that every citation in the report exists in `research_plan/state/sources.json`.

## Output

Record a `VerificationRunRecord` in `research_plan/state/verification_runs.json` with a check of type `semantic_audit`.
