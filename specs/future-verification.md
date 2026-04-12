# Future Verification

This document defines the deterministic verification contract for future RAIL agents and tasks.

## Principles

- deterministic checks come first
- LLM review supports but does not replace deterministic verification
- every write-capable task must have explicit completion checks
- verification status should be visible in both the DB and the planner's Git-visible plan state

## Verification Layers

### 1. Config Verification

Used for:

- `rail.yaml`
- agent YAML files
- ontology YAML
- source YAML
- pipeline YAML

Checks:

- parse succeeds
- schema validates
- required fields exist
- paths are valid and repo-relative

### 2. Path Policy Verification

Used for:

- all write-capable roles

Checks:

- modified files are inside allowed write roots
- denied paths were not modified

### 3. Hydration Verification

Used for:

- data agent tasks

Checks:

- YAML validates
- dry run succeeds
- target pipeline resolves
- expected artifact outputs exist

### 4. Execution Verification

Used for:

- coding agent tasks

Checks:

- scripts run without unhandled errors
- expected output files exist
- outputs are written to allowed paths

### 5. Artifact Verification

Used for:

- artifact agent tasks

Checks:

- required artifact files exist
- declared formats are renderable
- artifact paths match policy

### 6. Health Verification

Used for:

- health agent tasks

Checks:

- no disallowed file writes
- cleanup only touches approved paths
- skill audit status recorded

## Role Completion Matrix

### Planner

Completion requires:

- plan file updated
- task board snapshot updated
- operational DB task state updated

### Research

Completion requires:

- output files exist in allowed topic paths
- citation checklist passes
- task notes linked in planner state

### Data

Completion requires:

- YAML validation passes
- dry hydration run passes
- outputs land in allowed ontology paths

### Coding

Completion requires:

- execution completes without fatal error
- required outputs exist
- output paths are valid

### Artifact

Completion requires:

- renderable artifact files exist
- manifest/index metadata is updated if required
- outputs land in allowed artifact paths

### Health

Completion requires:

- verification report exists
- cleanup log exists
- any skill review actions are recorded

## Recording Verification

Verification should be recorded in:

- task events in the database
- runner/session metadata when useful
- planner-visible Git state under `research_plan/`

Suggested task event examples:

- `verification_started`
- `verification_passed`
- `verification_failed`

## Failure Behavior

If deterministic verification fails:

- the task should not move to `done`
- the task should move to `blocked` or `review`
- the planner should decide whether to retry, revise, or escalate

