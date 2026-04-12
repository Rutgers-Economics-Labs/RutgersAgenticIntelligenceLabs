# Future Bootstrap

This document defines how a new RAIL project is initialized.

## Goals

- create a valid repository contract from day one
- install starter project skills
- create starter agent configuration files
- produce the initial planner-visible project state

## Bootstrap Outputs

The setup flow should create:

- `rail.yaml`
- `.ontology/` directory with starter files
- `topics/`
- `specs/`
- `research_plan/`
- `agents/`
- `skills/`
- `artifacts/`

It should also create starter contents:

- starter manifest
- starter planner and worker agent YAML files
- starter prompt/checklist files
- starter global skills copied into the project
- initial `research_plan/current_plan.md`
- initial `research_plan/task_board.md`

## Bootstrap Interfaces

The platform may expose bootstrap through:

- CLI
- dashboard action
- API endpoint

V1 can support any one of these first, but the output contract should be the same.

## Minimal Starter Files

Recommended starter files:

```text
rail.yaml
.ontology/ontology.yaml
research_plan/current_plan.md
research_plan/task_board.md
agents/planner.yaml
agents/research.yaml
agents/data.yaml
agents/coding.yaml
agents/artifact.yaml
agents/health.yaml
```

## Starter Skills

The platform should copy a baseline global skill set into the project.

Suggested starter topics:

- repo contract rules
- citation formatting
- YAML style and validation
- verification norms
- artifact naming conventions

## Initial Planner State

The bootstrap process should seed:

- a long-lived planner thread in the database
- a first board in the database
- mirrored planner files in `research_plan/`

## V1 Constraints

Bootstrap should assume:

- project-scoped secrets only
- Jules as the default runner
- sequential worker execution
- human approval required for write-capable tasks

