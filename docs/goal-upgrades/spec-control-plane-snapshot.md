# Spec: Control-Plane Snapshot

## Purpose

The current command-center path rebuilds project state live from several services. That makes the UI slow and allows multiple truth systems to drift apart.

This spec introduces a repo-backed snapshot file:

- `research_plan/state/control_plane_snapshot.json`

Its job is to provide a deterministic, Git-visible control-plane projection built from repo truth.

## Snapshot Role

The snapshot is:

- repo-backed
- machine-generated
- replaceable
- not canonical domain truth

Canonical truth still lives in domain files such as:

- task files
- task board snapshot
- session state files
- artifact lineage
- verification runs
- source and claim registries
- ontology artifacts and hydration metadata

The control-plane snapshot is a projection of that truth.

## Initial Snapshot Contents

The first migration slice should include:

- `currentPlan`
- `missionBrief`
- `goal`
- `nextAction`
- `taskCounts`
- `recentArtifacts`
- `sourceSummary`
- `skillSummary`
- `integritySummary`
- `hypothesisTaskLinks`
- `ontologyFollowUps`
- `auditedTruth`
- `recentAudits`
- `lifecyclePhase`
- `closeoutCertificate`
- `currentBlocker`
- `blockerSummary`
- `repairQueue`
- `recommendedRepairTask`
- `projectReality`
- `auditors`
- `repoHealth`

Envelope fields:

- `snapshotVersion`
- `generatedAt`
- `commandCenter`

## Read Model

The command-center route should:

1. read the repo-backed snapshot if present and valid
2. merge in ephemeral runtime-only state where needed
3. fall back to live rebuild only when the snapshot is missing or invalid

Ephemeral runtime overlays include:

- active sessions
- pending approvals
- immediate next-action derivation based on current runtime state

## Write Model

The snapshot should be written during reconciliation.

That means:

1. reconcile repo truth
2. rebuild the control-plane snapshot from repo state
3. persist it to `research_plan/state/control_plane_snapshot.json`

This keeps the snapshot aligned with the repo-first model.

## Non-Goals For The First Slice

The first slice does not need to:

- move all command-center logic into the reconciler
- eliminate all live fallbacks
- replace every API route
- remove Convex entirely

The goal of the first slice is to establish the repo-backed snapshot path and make it authoritative where feasible.
