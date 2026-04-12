# Future Work Orders

This directory contains the granular work orders for the future architecture.

The current queue assumes:

- the frontend is a greenfield rebuild
- the Convex schema can be reset aggressively
- the ontology kernel is preserved and adapted rather than discarded
- one worker agent runs at a time in V1

## Dependency Outline

### Foundation

- `WO-F1.1` Manifest schema
- `WO-F1.2` Bootstrap generator
- `WO-F1.3` Starter project templates

### Agent Policy

- `WO-F2.1` Agent YAML schema
- `WO-F2.2` Prompt and checklist loader
- `WO-F2.3` Role policy resolver

### Database Reset

- `WO-F3.1` Convex schema reset
- `WO-F3.2` Project and planner-thread tables
- `WO-F3.3` Task board and approvals tables
- `WO-F3.4` Runner events and session tables
- `WO-F3.5` Project secrets and policy tables

### Runners

- `WO-F4.1` Runner abstraction
- `WO-F4.2` Jules session lifecycle
- `WO-F4.3` Jules approvals, questions, and event normalization

### Hydration Artifacts

- `WO-F5.1` Device registry
- `WO-F5.2` Hydration artifact registry
- `WO-F5.3` Artifact reuse and stale detection

### Planner System

- `WO-F6.1` Long-lived planner thread
- `WO-F6.2` Git-mirrored planner files
- `WO-F6.3` Planner task board sync

### Frontend Reset

- `WO-F7.1` Route reset and shell scaffold
- `WO-F7.2` Planner plane
- `WO-F7.3` Repo browser plane
- `WO-F7.4` Artifacts and timeline plane
- `WO-F7.5` Settings and sessions surfaces

### Kernel Adaptation

- `WO-F8.1` `rail.yaml` project loader
- `WO-F8.2` `.ontology` hydration alignment
- `WO-F8.3` Verification hooks

### Artifacts

- `WO-F9.1` Artifact indexing
- `WO-F9.2` Report and PDF rendering
- `WO-F9.3` Dashboard rendering

## Execution Principle

Complete the foundation, policy, and operational schema work before serious frontend implementation.

## Tooling

New machines should install agent CLI tools with:

- `make install`
- or `make install-agent-tools`

This installs `mgrep` and the Gemini CLI through the Makefile.

