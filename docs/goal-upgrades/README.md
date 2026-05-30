# Goal Upgrades

This folder defines the repo-first goal and control-plane migration for RAIL.

The guiding rule is:

`The repo is the only durable truth.`

Everything else should be either:

- a cached projection
- ephemeral runtime state
- or a derived view rebuilt from repo files

This upgrade path focuses on three linked changes:

1. goals become explicit repo-backed completion contracts
2. control-plane state becomes a repo-backed snapshot instead of ad hoc live assembly
3. autopilot becomes a repo-driven executor rather than a second durable state machine

Files in this folder:

- `spec-minimal-goal-mode.md`
  Defines the smallest architectural change needed to make RAIL behave more like durable goal mode.
- `spec-repo-first-goals.md`
  Defines the durable goal contract and the separation between project truth and execution truth.
- `spec-control-plane-snapshot.md`
  Defines `research_plan/state/control_plane_snapshot.json` as the canonical repo-backed control-plane projection.
- `spec-migration-plan.md`
  Breaks the migration into incremental implementation phases.
