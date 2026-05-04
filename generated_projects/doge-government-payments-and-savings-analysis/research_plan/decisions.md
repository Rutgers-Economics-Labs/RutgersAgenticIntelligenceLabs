# Decisions

- 2026-05-03: Use the existing RAIL bootstrap path
  (`scripts/bootstrap_future_project.py` backed by
  `packages/rail-py/rail/bootstrap.py`) rather than hand-assembling the
  project scaffold.
- 2026-05-03: Start with a planner-first research workspace centered on DOGE
  payment endpoints because the user explicitly pointed to
  `/payments/statistics`.
- 2026-05-03: Treat savings feeds as adjacent inputs in phase one rather than
  forcing a premature linkage model between payments and savings.
- 2026-05-03: Keep ontology scope intentionally small until live payloads are
  sampled and field stability is validated.
