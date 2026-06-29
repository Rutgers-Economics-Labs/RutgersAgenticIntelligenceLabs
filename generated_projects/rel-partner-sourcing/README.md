# REL Partner Sourcing

RAIL generated project for discovering net-new REL partner organizations, verifying contact routes, and drafting first-contact outreach.

## Purpose

This project is designed for Rutgers Economics Labs partner sourcing work:
- find organizations not already in the active REL KB
- verify the cleanest official contact route
- identify one or two plausible people when public staff pages allow it
- end every completed workflow with at least one draft outreach email and a concrete next step

## Runner defaults

- Runner: `codex_cli`
- Model: `gpt-5.4`

## Core workflow outputs

Every completed organization-sourcing run should produce:
- one markdown finding under `topics/findings/`
- at least one contact path with official evidence
- one draft email under `artifacts/emails/`
- one next-step recommendation

## Main tasks

- `research_plan/tasks/discover-net-new-organizations.md`
- `research_plan/tasks/verify-contact-route-and-draft-email.md`
