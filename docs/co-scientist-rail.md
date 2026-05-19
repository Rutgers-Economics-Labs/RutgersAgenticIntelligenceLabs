# Co-Scientist Mode in RAIL

This document explains the hypothesis-first additions for larger end-to-end research runs.

## What was added

- **Hypothesis portfolio** in `research_plan/state/hypotheses.json`
- **Critic review loop** that writes blocker conflicts and claim candidates
- **Ranking and prioritization** signals for hypothesis-linked task selection
- **Research burst controls** in `rail.yaml` (`research_burst.enabled`, `max_parallel`, `max_cost_usd`)
- **Meta-synthesis template** at `artifacts/meta_synthesis.md`

## Hypothesis workflow

1. Create hypotheses via API (`POST /api/v1/projects/{slug}/hypotheses`) or Integrity UI panel.
2. Link each hypothesis to claim keys and task IDs.
3. Run critic review (`POST /api/v1/projects/{slug}/critic/review`) to identify blockers.
4. Resolve claim evidence gaps and update hypothesis status.
5. Use ranked hypotheses in closeout synthesis and next-task prioritization.

## Critic gate behavior

- Hypotheses marked `weakened` or `rejected` are treated as promotion blockers when linked claims appear in an artifact.
- Promotion gate reasons include critic blocker messaging until those hypotheses are resolved or archived.

## Research burst behavior

- Burst execution is capped by manifest limits.
- Each burst creates angle-specific draft hypotheses and corresponding research tasks.
- Session launch is bounded to configured maximum parallelism and never unbounded.

## E2E smoke run

Use:

```bash
./scripts/e2e_research_smoke.sh docs/validation/ontology-first-public
```

This validates manifest loading, required integrity state files, and verification script wiring.
