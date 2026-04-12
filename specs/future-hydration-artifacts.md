# Future Hydration Artifacts

This document defines how RAIL tracks hydrated ontology artifacts across devices so the platform can avoid unnecessary rehydration.

## Problem

The backend may run on multiple devices.

A project may already be hydrated on one device but not another. The platform needs to know:

- what was hydrated
- from which repo state
- on which device
- where the resulting artifacts live
- whether those artifacts are still valid

Without this, the system will waste time and compute repeatedly hydrating the same project state.

## Goals

- make hydration reuse explicit
- support device-aware artifact lookup
- avoid rehydrating when a valid local artifact already exists
- show users whether a project is hydrated on the current device, another device, or nowhere

## Artifact Identity

A hydrated ontology artifact should be identified by:

- `project_id`
- `commit_sha`
- `manifest_version` or manifest fingerprint
- `pipeline_slug`
- `device_id`

Optional additions:

- ontology config fingerprint
- sources fingerprint
- hydration mode

## Device Model

Each backend environment should have a stable `device_id`.

Suggested properties:

- generated once per machine or server environment
- stored outside the repo
- readable by the backend service

Suggested device metadata:

- `device_id`
- `label`
- `hostname`
- `platform`
- `created_at`
- `last_seen_at`

## Hydration Registry

The platform should maintain an operational hydration artifact registry in the database.

Suggested table: `hydration_artifacts`

Suggested fields:

- `id`
- `project_id`
- `device_id`
- `commit_sha`
- `manifest_fingerprint`
- `pipeline_slug`
- `hydration_mode`
- `ontology_artifact_path`
- `duckdb_artifact_path`
- `status`
- `created_at`
- `last_validated_at`

## Artifact Paths

The registry should store local device paths for hydrated artifacts.

Examples:

- local ontology database path
- local DuckDB path
- local exported OWL path

These paths are device-local operational paths, not repository paths.

## Reuse Rules

The backend should reuse an existing local hydration artifact when:

- `project_id` matches
- `device_id` matches the current device
- `commit_sha` matches the currently loaded repo commit
- `pipeline_slug` matches the requested hydration target
- the artifact status is valid
- the artifact files still exist on disk

If any of these fail, the backend should rehydrate.

## Validation Rules

A hydration artifact should be marked stale when:

- the repo commit changes
- `rail.yaml` changes in a way that affects hydration inputs
- `.ontology/` files affecting the target pipeline change
- the artifact files no longer exist
- the artifact was produced by an incompatible package version

## Frontend UX

The frontend should surface hydration state like this:

- hydrated on this device
- hydrated on another device
- stale on this device
- not hydrated yet

The UI should not imply that hydration on another device is immediately reusable if the artifact is only local to that other device.

## Git vs DB

Hydration artifacts should not be tracked in Git.

Git stores the declarative inputs.
The database stores operational artifact metadata.
The filesystem on each device stores the actual hydrated outputs.

## Related Manifest Support

`rail.yaml` does not need to store device-specific hydration state.

It may later include optional defaults like:

- preferred pipeline slug
- hydration profile name

But device-aware artifact caching belongs in operational metadata, not the manifest.

