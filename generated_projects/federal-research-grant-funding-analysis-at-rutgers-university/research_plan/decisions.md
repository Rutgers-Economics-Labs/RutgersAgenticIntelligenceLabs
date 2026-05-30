# Decisions

## Public-Data Scope

The local completion pass uses USAspending.gov as the broad cross-agency source and the NSF Awards API as a research-award detail cross-check. These public feeds are sufficient for an observed federal-award panel, but not for audited Rutgers department rankings.

## Department Ranking Guardrail

The project explicitly does not infer academic departments from award titles. A proper department dashboard requires an internal Rutgers sponsored-program account, PI appointment, department/campus, and faculty-headcount crosswalk.

## Verification Contract

`scripts/run-verification.sh` now builds artifacts, registers rail truth state through `ResearchIntegrityRepo`, and then runs `scripts/verify_project_state.py`. The verifier requires non-empty artifacts, source records, evidence-linked claims, promoted lineage, and a passed verification run.
