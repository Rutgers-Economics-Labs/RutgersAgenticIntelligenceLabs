# Generated Project Hygiene

## Purpose

`generated_projects/` is where RAIL keeps live project repos, runner workspaces, and
artifact-heavy research outputs. These directories are operational state, not normal
source code. Treating them like ordinary tracked app code creates noisy diffs,
confusing commits, and accidental coupling between platform changes and project data.

## Policy

1. Platform code and project state should be committed separately.
2. Changes under `generated_projects/` should only be committed when they are:
   - intentional fixture updates for tests or demos
   - canonical sample projects explicitly meant to live in the repo
   - documentation artifacts the team wants to preserve
3. Routine runner outputs should stay untracked:
   - `.rail/workspaces/`
   - `research_plan/sessions/`
   - transient logs
   - regenerated dashboards, datasets, and intermediate analysis files
4. Repo-first reconciliation must work even when project outputs are not committed.

## Operational Rules

- Use narrow `git add` commands for platform fixes.
- Never sweep `generated_projects/` into a platform commit by default.
- When a generated project is needed as a reproducible fixture, promote only the
  minimal stable files required for the fixture.
- Prefer screenshots, summaries, or exported reports in `docs/` over broad
  project-directory commits when the goal is demonstration rather than fixture setup.

## Recommended Ignore Boundaries

At minimum, local and transient project runtime state should be ignored:

- `generated_projects/**/.rail/workspaces/`
- `generated_projects/**/research_plan/sessions/`
- `generated_projects/**/research_plan/audits/`
- `generated_projects/**/research_plan/stuck_reports/`
- `generated_projects/**/.session.lock`
- `generated_projects/**/.commands.lock`

If a project needs tracked fixtures, add explicit allowlists instead of loosening
these defaults.

## Promotion Checklist

Before committing anything from `generated_projects/`, verify:

- Is this needed as a stable fixture?
- Can the same value be captured in `docs/` instead?
- Does this file contain transient runner state or machine-local paths?
- Will this make future platform diffs harder to review?

If any answer points to “transient,” do not commit it.

## Platform Follow-up

The long-term platform goal is to make generated-project hygiene enforceable:

- add default ignore coverage for transient runtime trees
- add fixture-specific allowlists
- add a pre-commit check that warns when broad `generated_projects/` changes are staged
