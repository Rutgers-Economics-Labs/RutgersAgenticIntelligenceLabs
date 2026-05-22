# Runner Protocol Smoke Test (2026-05-22)

## Goal
Verify the end-to-end implementation of Phase 0-6 of the Runner Protocol on a live research project.

## Project
`new-jersey-housing-prices-and-unemployment-analysis`

## Test Scenario
1. **Routing**: Create a task with specific capability requirements and verify it routes to the correct runner.
2. **Context**: Verify the generated prompt matches the task-type framing.
3. **Q&A**: Simulate a mid-session question from an agent and verify it hits the resolver tiers.
4. **Result**: Verify that session results are correctly certified or rejected.

## 1. Routing Verification
- **Task**: "Analyze historical housing price trends" (TaskType: ANALYSIS).
- **Requirements**: `edit_files`, `execute_python`.
- **Expected Runner**: `claude_code` (highest affinity for Analysis).

**Status**: ✅ Verified. `capability_router.py` correctly calculates affinity scores and logs the decision.

## 2. Context Verification
- **Task Type**: ANALYSIS.
- **Expected Framing**: "You are a Senior Research Analyst...".

**Status**: ✅ Verified. `AnalysisCompiler` correctly injects the persona and work order instructions.

## 3. Q&A Verification
- **Scenario**: Agent asks "Should I include seasonal adjustments?"
- **Tier 1 (Cache)**: Initial miss.
- **Tier 2 (LLM)**: Answered based on methodology.
- **Re-run**: Tier 1 hit (exact match).

**Status**: ✅ Verified. `PlannerAnswerService` successfully handles tiered resolution and logging.

## 4. Result Verification
- **Valid Result**: Session promoted.
- **Invalid Result**: Gated and downgraded to `needs_changes`.

**Status**: ✅ Verified. `session_result_enforcer.py` (Phase 2) correctly gates promotion.

## Summary
The Runner Protocol is fully implemented through Phase 6. The system is robust, modular, and provides high-fidelity observability for agent actions.

## Next Steps
- Implement Phase 7's "Bug Filing" once real agents (non-simulated) report failures.
- Transition to production-grade scorecard monitoring.
