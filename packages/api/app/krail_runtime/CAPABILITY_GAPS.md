# KRAIL 0.2.2 Capability Gaps

These are tracked adapter limitations, not features to recreate in RAIL.

- **SQL query fixture:** KRAIL's SQL helper requires a hydrated ontology artifact.
  The deterministic markdown fixture intentionally has no generated database, so
  an artifact-backed SQL contract remains deferred.
- **Workflow process control:** KRAIL runs workflows locally but does not expose
  platform cancellation or a live event stream. M4 will add isolated execution
  and event normalization around KRAIL workflow calls.
- **Local integrity summary:** `Project.integrity_status()` in KRAIL 0.2.2
  imports retired RAIL service modules in local mode. The adapter uses the
  published `ResearchIntegrityRepo` record API for its read-only summary until
  KRAIL exposes a local summary method.
