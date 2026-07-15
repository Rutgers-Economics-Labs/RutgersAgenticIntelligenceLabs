# KRAIL Runtime Migration Plan

Status: Wave 3 local single-node control plane and Explore/Evidence workspace integrated
Branch: `krail`
Target: KRAIL is the project source of truth; RAIL is the visual and operational platform.

## 1. Outcome

RAIL will stop owning ontology storage, source records, integrity indexes, task/workflow state,
graph/search behavior, and project-local runtime semantics. Those responsibilities move to the
published `krail` package and the KRAIL project directory.

RAIL will own:

- a multi-project visual interface;
- project registration and workspace location;
- authentication, authorization, and secret references;
- isolated runtime processes and their live events;
- schedules and hosted execution infrastructure;
- a stable HTTP boundary for the web application;
- operational health, logs, budgets, and administrative controls.

The platform database must not become a second representation of KRAIL records. Durable project
content is read from and written through KRAIL. Operational records may point to KRAIL identifiers
and repo paths but may not redefine them.

### Current implementation checkpoint

Implemented and verified on `krail`:

- published `krail==0.2.2` compatibility adapter with namespace-shadowing protection and contract
  tests for health, manifest, find, graph, sources, integrity, workflows, approvals, and dry runs;
- single-node managed/linked-local project registry with canonical path and Git baseline policy;
- versioned project and read-only knowledge APIs for find, graph, sources, integrity, workflows,
  and approvals;
- `/krail-preview` design foundation and `/krail-live` server-rendered M2/M3 client path;
- local execution-control foundation with durable run/event metadata, explicit permission snapshots,
  restart reconciliation, cancellation, isolated Git worktrees, and atomic retained integration refs.
- mounted project-scoped workflow run API with bounded local supervision, durable event snapshots,
  reconnectable SSE, cancellation, read-only enforcement, and server-owned permission profiles;
- fail-closed macOS `sandbox-exec` provider for restricted commands, including filesystem and network
  enforcement, environment filtering, timeout/cancellation, and explicit portability metadata;
- `/krail-explore` live Explore/Evidence workspace with URL-stable find filters, an accessible graph
  and relationship list, source impact, integrity/workflow/approval capability states, and provenance.

Restricted command profiles require an injected sandbox that enforces filesystem and network policy
at the OS boundary; the raw subprocess runner accepts only the explicit unrestricted `full-access`
profile. Non-dry KRAIL workflow execution is likewise limited to operator-enabled `full-access` until
KRAIL exposes an enforcing execution hook. This is a security invariant, not a temporary UI
restriction. The current macOS provider uses Apple-deprecated `sandbox-exec`; Linux bwrap/container
providers remain required before hosted Linux execution.

Known remaining foundation gaps are workflow run/SSE UI, approval decisions, operator-defined
fine-grained profile configuration, Linux sandboxing, SQL/analysis fixture support, Analyze,
Workflows, and Control Plane workspaces, removal of legacy runtime packages, and existing legacy
frontend imports for removed planner/work-order API functions.

### Local control-plane configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `RAIL_PROJECT_REGISTRY_PATH` | `.rail/platform-projects.json` | RAIL-owned project registry metadata |
| `RAIL_MANAGED_WORKSPACE_ROOT` | `.rail/projects` | Platform-managed Git workspace root |
| `RAIL_LINKED_PROJECT_ROOTS` | empty | Path-separated operator-approved linked-directory roots |
| `RAIL_RUN_STORE_PATH` | `.rail/platform-runs.json` | Durable local run and event snapshots |
| `RAIL_RUN_MAX_WORKERS` | `4` | Local workflow supervisor size, constrained to 1–32 |
| `RAIL_FULL_ACCESS_ENABLED` | false | Explicit operator gate for unrestricted and non-dry execution |

Unknown or false-like `RAIL_FULL_ACCESS_ENABLED` values fail closed. If no enforcing restricted
sandbox is available, restricted command execution is rejected rather than falling back to a raw
subprocess. Application shutdown waits for accepted local jobs; interrupted persisted jobs are
marked failed during restart reconciliation.

## 2. Architectural invariants

1. A KRAIL project directory is the canonical state boundary.
2. All durable knowledge mutations go through the KRAIL Python API or an explicitly documented
   KRAIL CLI fallback.
3. RAIL never writes ontology, topic, source, integrity, task, workflow, or artifact metadata by
   editing their backing files directly.
4. Derived UI indexes are disposable caches and can be rebuilt from a project.
5. The API exposes RAIL-owned contracts. KRAIL response dictionaries do not leak directly into
   browser code.
6. Workflow execution occurs in an isolated project workspace with a bounded environment,
   timeout, cancellation, and auditable event stream.
7. A successful runtime mutation is durable before the API reports success.
8. Git integration versions project state; Git is not required for every read operation.
9. KRAIL package upgrades are deliberate, pinned, and protected by adapter contract tests.
10. The Python distribution is named `krail` but imports as `rail`; the existing in-repo
    `packages/rail-py` package must be removed before production dependency installation to avoid
    namespace shadowing.
11. Concurrent workflows never mutate the same working tree. Each receives an isolated Git
    worktree and branch created from a recorded base commit.
12. A coordinated batch may publish several successful workflow branches as one atomic project
    commit only after conflict detection and full KRAIL validation.

## 3. Target system

```text
Browser (Next.js)
  -> RAIL Platform API (FastAPI)
       -> Project registry / auth / policies / secrets / run metadata
       -> KrailRuntime adapter
            -> import rail; rail.local(project_path)
            -> KRAIL project files and .krail runtime state
       -> isolated workflow worker pool
            -> KRAIL execute_workflow / run_workflow
            -> normalized run events
       -> batch integration coordinator
            -> conflict detection / policy gates / KRAIL validation
            -> one combined project commit
  -> optional Git remote for versioning and collaboration
```

### Parallel workflow and commit model

Multiple AI workflows may run concurrently against one project, but they may not share a mutable
working tree. RAIL creates a batch with a fixed base commit and gives every workflow its own branch
and worktree:

```text
canonical project branch at commit B
  -> workflow A worktree / branch (B -> A1)
  -> workflow B worktree / branch (B -> B1)
  -> workflow C worktree / branch (B -> C1)
  -> integration worktree at B
       -> apply A1, B1, C1 without committing
       -> detect semantic and textual conflicts
       -> run KRAIL doctor, graph/source/integrity checks, and project tests
       -> create one batch commit C, or publish nothing
```

Each worker may make local checkpoint commits on its private branch. Those commits remain referenced
by the workflow run record for auditability. The integration coordinator applies the approved
changes into a dedicated integration worktree and creates one combined commit containing workflow
IDs, source commit hashes, validation results, and the batch ID in its metadata.

Only dependency-independent workflows may share a batch. If workflow B consumes files or records
produced by workflow A, the scheduler creates a DAG dependency and starts B from the integrated
commit containing A. Concurrency is never used to hide a real data dependency.

Automatic integration is allowed only when:

- every included workflow succeeded and passed its own verification;
- no workflow remains at an approval gate;
- changed-path policy allows the union of changes;
- textual patches apply cleanly;
- KRAIL-owned records remain schema-valid;
- no semantic conflict is detected in shared manifests, workflow definitions, ontology records,
  source records, claims, or integrity indexes;
- final project-wide verification passes.

Overlapping edits are not resolved with last-writer-wins. The coordinator may use a configured
domain-aware merge rule for known append-only records; otherwise the batch becomes
`integration_blocked` and requires a repair workflow or operator decision. The canonical branch is
locked only during final integration, not for the duration of every workflow.

### Workspace registration modes

RAIL supports both requested project-placement models:

- **Managed workspace:** RAIL creates or clones the Git repository under a configured platform
  workspace root and owns its worktrees, lifecycle, and cleanup.
- **Linked local workspace:** an operator registers an explicit directory at any location the RAIL
  service account can access. RAIL stores the canonical resolved path and never silently moves it.

A linked directory that is not a Git repository can be inspected read-only. Before write-capable
or concurrent workflows run, the operator must explicitly choose to initialize Git in place or
import the project into a managed workspace. A linked Git repository must have a recorded baseline;
pre-existing uncommitted changes are preserved and either committed by the operator or excluded by
creating a managed clone. RAIL never folds unrelated dirty-tree changes into an agent batch.

### Ownership map

| Concern | Canonical owner | RAIL behavior |
| --- | --- | --- |
| Project manifest and paths | KRAIL project | Display and validate |
| Ontology and entities | KRAIL | Query and visualize |
| Sources and freshness | KRAIL | Display, trigger checks, explain impact |
| Topics and captures | KRAIL | Browse, capture, promote, edit through adapter |
| Graph and vector index | KRAIL | Trigger rebuilds and render results |
| Claims, evidence, assumptions, lineage | KRAIL | Review and invoke supported mutations |
| Tasks, workflows, approvals, schedules | KRAIL | Author through adapter and operate visually |
| Workflow process and live logs | RAIL operational layer | Launch, stream, cancel, retain summaries |
| Users, roles, organizations | RAIL | Authorize access to registered projects |
| Secret values | RAIL secret store | Inject references into isolated runs |
| Git credentials and remotes | RAIL operational layer | Sync/version project directories |

## 4. Repository target

```text
apps/
  web/                       # Next.js visual platform
packages/
  api/                       # thin FastAPI platform/control-plane API
    app/
      krail_runtime/         # the only KRAIL integration boundary
      projects/              # registry and workspace lifecycle
      execution/             # permissions, process lifecycle, worktrees, and events
      auth/                  # platform authorization
      secrets/               # secret references and injection
      api/                   # versioned HTTP routes and DTOs
  shared-contracts/          # optional generated TS/Python API contracts
examples/
  krail-project/             # one small, deterministic fixture
docs/
  KRAIL_MIGRATION_PLAN.md
```

The following are migration removals, not permanent platform components:

- `packages/engine`;
- `packages/rail-py`;
- `packages/mcp-server` (KRAIL supplies the agent-facing runtime);
- Convex-backed mirrors of project content;
- RAIL-owned ontology, hydration, graph, integrity, task, and workflow implementations;
- legacy autopilot/planner swarm code not needed to operate KRAIL workflows;
- one-off project repair, seeding, monitoring, and release-bundle scripts;
- historical specifications superseded by this architecture and the final API/UI contracts.

## 5. Dependency and adapter design

Declare a compatible KRAIL release range and commit an exact resolved lock:

```toml
dependencies = [
  "krail[local,analysis,embeddings]>=0.2.2,<0.3",
]
```

The lockfile records the exact version used by local development and production. KRAIL remains an
ordinary upstream dependency: dependency-update changes advance the lock, run the adapter contract
suite, and are merged when compatible. RAIL does not fork or copy KRAIL internals. The extras should
be revisited after measuring installation size and identifying which hosted capabilities are
actually enabled. Production images should use hashes from the lockfile.

The adapter must be the only application module allowed to import `rail`:

```python
class KrailRuntime(Protocol):
    def doctor(self, project: ProjectRef) -> ProjectHealth: ...
    def manifest(self, project: ProjectRef) -> ProjectManifest: ...
    def find(self, project: ProjectRef, query: FindQuery) -> FindResult: ...
    def graph(self, project: ProjectRef, query: GraphQuery) -> GraphResult: ...
    def sources(self, project: ProjectRef) -> SourceInventory: ...
    def integrity(self, project: ProjectRef) -> IntegritySummary: ...
    def workflows(self, project: ProjectRef) -> WorkflowInventory: ...
    def execute_workflow(self, project: ProjectRef, request: RunRequest) -> RunHandle: ...
```

The concrete local implementation opens a project with `rail.local(path)`. It maps KRAIL results
into versioned Pydantic DTOs, translates KRAIL exceptions into typed platform errors, and applies
the authenticated project path and permission context. CLI subprocesses are allowed only for a
feature not exposed by the Python package and must be tracked as temporary compatibility gaps.

Adapter contract tests must cover the KRAIL operations used by the UI, including:

- manifest and `doctor`;
- `find`, search, graph entities/edges/docs, and SQL query;
- sources list/check/affected;
- integrity summary, dependency graph, and verification history;
- task and workflow list/show/validate/run/status/resume;
- approval list/show/decide;
- capture, topic, and inbox operations;
- artifact and run record discovery.

## 6. HTTP surface

The initial API should be intentionally small:

```text
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{project_id}
GET    /api/v1/projects/{project_id}/health
GET    /api/v1/projects/{project_id}/manifest

POST   /api/v1/projects/{project_id}/find
POST   /api/v1/projects/{project_id}/query
GET    /api/v1/projects/{project_id}/graph
GET    /api/v1/projects/{project_id}/sources
POST   /api/v1/projects/{project_id}/sources/check
GET    /api/v1/projects/{project_id}/integrity

GET    /api/v1/projects/{project_id}/workflows
GET    /api/v1/projects/{project_id}/workflows/{workflow_id}
POST   /api/v1/projects/{project_id}/workflows/{workflow_id}/validate
POST   /api/v1/projects/{project_id}/runs
GET    /api/v1/projects/{project_id}/runs
GET    /api/v1/projects/{project_id}/runs/{run_id}
POST   /api/v1/projects/{project_id}/runs/{run_id}/cancel
GET    /api/v1/projects/{project_id}/runs/{run_id}/events
GET    /api/v1/projects/{project_id}/runs/{run_id}/events/stream

GET    /api/v1/projects/{project_id}/approvals
POST   /api/v1/projects/{project_id}/approvals/{approval_id}/decision
```

Mutation endpoints for captures, topics, sources, workflows, and integrity records should be added
only when the corresponding KRAIL API semantics and authorization rules are covered by contract
tests.

## 7. User interface

The visual platform has five primary workspaces:

1. **Explore** — ontology graph, entity tables, document/topic navigation, search, and raw record
   inspection.
2. **Analyze** — SQL/query workbench, saved views, charts, analysis artifacts, and direct links to
   generating inputs.
3. **Evidence** — sources, freshness, assumptions, claims, conflicts, lineage, verification runs,
   and stale-output impact.
4. **Workflows** — workflow inventory, DAG visualization/editor, validation, run launch, live event
   timeline, retries, approvals, and outputs.
5. **Control Plane** — projects, health, Git/workspace state, users/roles, secret references,
   policies, schedules, runners, and resource usage.

Every analysis or artifact view must support a provenance drawer showing its source records,
upstream files or queries, assumptions, verification state, and affected downstream outputs.

## 8. Implementation slices

Each slice should land as an independently reviewable commit. Code-changing parallel tasks must use
separate worktrees. A child task owns the listed paths and must not edit another task's paths without
coordination.

### M0 — Decisions and destructive-cleanup gate

Owner: parent task
Dependencies: none

- Answer the open product decisions in section 11.
- Mark all legacy directories keep/remove/migrate.
- Record a baseline build/test result before runtime deletion.
- Confirm ignored local workspaces are excluded from deletion.

Acceptance: signed-off ownership table and cleanup manifest.

### M1 — KRAIL compatibility spike

Owner paths: `packages/api/app/krail_runtime/**`, `packages/api/tests/krail_runtime/**`, fixture only
Dependencies: M0
Implementation: complete for the currently used KRAIL 0.2.2 surface; capability gaps are documented
in `packages/api/app/krail_runtime/CAPABILITY_GAPS.md`.

- Pin KRAIL and remove the local `rail` package from Python resolution.
- Build a deterministic KRAIL example fixture.
- Implement adapter lifecycle, typed errors, and DTO mapping.
- Exercise the complete adapter contract against KRAIL 0.2.2.
- Produce a capability-gap list; do not copy missing KRAIL features into RAIL.

Acceptance: adapter contract suite passes without importing old engine/service modules.

### M2 — Platform API skeleton and project registry

Owner paths: `packages/api/app/api/**`, `packages/api/app/projects/**`, API bootstrap/config tests
Dependencies: M0; can run alongside M1 after DTO boundary agreement
Implementation: complete for the local single-node registry and project/health/manifest routes.

- Replace the router collection with a small versioned API.
- Implement project registration by stable ID and canonical workspace path.
- Support managed and linked-local workspace modes. Canonicalize symlinks, verify explicit access
  authorization, record Git/baseline state, and validate KRAIL project health on registration.
- Store only operational metadata.
- Add structured errors, request IDs, and health endpoints.

Acceptance: register/list/open/health works for the fixture; path traversal tests pass.

### M3 — Read-only knowledge API

Owner paths: KRAIL API routes and DTOs agreed with M1
Dependencies: M1 and M2
Implementation: complete for find, graph, sources, integrity, workflow inventory, and approvals.
SQL/query, pagination, OpenAPI snapshots, and run history remain follow-up work.

- Expose manifest, find/search, ontology graph, SQL query, sources, integrity, workflow inventory,
  approvals, and run history.
- Add pagination, bounded result sizes, and cancellation/timeouts.
- Add OpenAPI snapshots and frontend-generated types.

Acceptance: read API integration tests match the fixture's KRAIL state.

### M4 — Run service and event stream

Owner paths: `packages/api/app/execution/**`, run HTTP/SSE modules, worker entrypoint, run tests
Dependencies: M1 and M2
Implementation: execution-policy, durable-state, worktree, and atomic-combine foundation complete.
HTTP/SSE mounting, a concrete restricted sandbox, worker process supervision, and approval resume
remain follow-up work.

- Define queued/running/awaiting_approval/succeeded/failed/cancelled states.
- Execute KRAIL workflows concurrently in isolated processes, Git branches, and worktrees.
- Normalize stdout and KRAIL run state into sequenced events.
- Implement cancellation, timeout, restart reconciliation, log retention, and idempotency.
- Implement batch creation, fixed base commits, per-run checkpoint commits, changed-path manifests,
  conflict detection, and an integration worktree.
- Apply approved workflow commits without committing, run final validation, and create one atomic
  batch commit. Publish nothing when integration or validation fails.
- Keep durable workflow/run truth in KRAIL; retain only live operational handles and event cache in
  RAIL.

Acceptance: launch, stream, approve, cancel, fail, restart-reconcile, concurrent non-overlapping
batch commit, overlapping-edit block, and failed-validation rollback scenarios pass.

### M5 — Shared frontend foundation

Owner paths: `apps/web/lib/**`, app shell, design primitives; no feature pages
Dependencies: M3 contract
Implementation: `/krail-live` project, health, manifest, source, error, and provenance foundation
complete and smoke-tested against the real KRAIL fixture. Shared navigation and broader generated
contracts remain follow-up work.

- Replace legacy API contracts with generated/validated platform types.
- Build project selector, navigation, query client, loading/error states, and provenance drawer.
- Establish accessible layout, responsive behavior, and visual tokens.

Acceptance: fixture project loads through the new API with no legacy service calls.

### M6 — Explore and Evidence UI

Owner paths: Explore/Evidence routes and their feature components
Dependencies: M3 and M5

- Build ontology graph and entity/document inspectors.
- Build unified search/find results.
- Build sources/freshness, claims/evidence, assumptions, conflicts, lineage, and verification views.
- Deep-link every record to its KRAIL repo path/identifier.

Acceptance: users can trace a displayed claim or entity to underlying sources and affected outputs.

### M7 — Analyze UI

Owner paths: Analyze routes and components
Dependencies: M3 and M5

- Add bounded read-only SQL/query workbench first.
- Render tables and charts with query/source provenance.
- List and render KRAIL artifacts.
- Save analysis definitions through a KRAIL-supported durable representation only.

Acceptance: a saved or rendered analysis can be reproduced from its shown inputs.

### M8 — Workflows UI

Owner paths: Workflow/run/approval routes and components
Dependencies: M4 and M5

- Inventory and inspect workflow YAML through KRAIL.
- Render DAGs, validation errors, retry/timeout policy, and inputs.
- Launch runs, stream events, cancel, resume, and decide approvals.
- Add visual authoring only after a round-trip-safe KRAIL workflow mutation API exists.

Acceptance: a user can validate and operate the fixture workflow without touching the CLI.

### M9 — Control plane and security

Owner paths: auth, authorization, secret references, policy and admin UI
Dependencies: M2, M4, and deployment decision

- Implement organization/project roles and server-side authorization.
- Define KRAIL permission-context mapping.
- Store secret values outside project repos; expose names/metadata only.
- Implement named execution profiles ranging from `full_access` to path, command, network, secret,
  runtime, and resource-specific policies. A workflow selects a permitted profile; it cannot grant
  itself broader access.
- Compute effective permissions as the intersection of the platform execution profile, KRAIL
  project/record permissions, and the workflow request. No layer may broaden another layer's deny.
- Enforce workspace containment, configured command/network rules, resource limits, audit logs, and
  CSRF/session protections. Arbitrary commands are permitted only when the assigned profile allows
  them.
- Add Git sync policy and conflict handling if remote repositories are supported.

Acceptance: cross-project access, path escape, secret disclosure, and unauthorized execution tests
fail closed.

### M10 — Legacy deletion and dependency simplification

Owner: parent integration task
Dependencies: M3, M4, and at least one complete UI vertical slice

- Delete `packages/engine`, `packages/rail-py`, and `packages/mcp-server`.
- Delete superseded API routers/services, Convex integration, planner/autopilot swarm, and runners.
- Delete obsolete scripts, docs, specs, environment variables, tests, and CI/release jobs.
- Rewrite README, AGENTS guide, install flow, Makefile, container config, and security guidance.
- Confirm no application code imports removed modules or writes KRAIL-owned files directly.

Acceptance: dead-code/import scans are clean and fresh setup uses the published KRAIL dependency.

### M11 — End-to-end hardening and release

Owner: integration task
Dependencies: M6–M10

- Run API unit/integration tests, web tests/build, and browser-visible end-to-end flows.
- Test KRAIL upgrade compatibility and corrupted/partial project behavior.
- Add backup, restore, Git conflict, interrupted run, and disaster-recovery tests.
- Stress concurrent workflow batches, overlapping KRAIL records, integration rollback, and
  canonical-branch lock recovery.
- Pin production dependencies and generate SBOM/vulnerability reports.
- Document local development and the chosen deployment topology.

Acceptance: a new operator can register the fixture, inspect provenance, run a workflow, approve a
gate, view analysis, restart services, and recover the same KRAIL-backed state.

## 9. Coordination waves

After M0, use at most three child tasks concurrently so the parent remains available to integrate.

| Wave | Child A | Child B | Child C | Parent gate |
| --- | --- | --- | --- | --- |
| 1 | M1 compatibility | M2 API skeleton | UI inventory/prototype within M5 | Approve DTOs and capability gaps |
| 2 | M3 read APIs | M4 run service | M5 frontend foundation | Run combined API contract tests |
| 3 | M6 Explore/Evidence | M7 Analyze | M8 Workflows | Resolve shared-component conflicts |
| 4 | M9 security/control plane | migration tooling | documentation/test harness | Threat-model and authorize deletion |
| 5 | M10 deletion | M11 backend hardening | M11 browser verification | Final integration and release decision |

Before creating tasks, the coordinator must resolve the current parent task ID. Every child prompt
must include the thread-coordinator completion protocol, its worktree/branch, exact owned paths,
dependencies, acceptance criteria, and the instruction to report back once.

## 10. Verification strategy

- Unit tests for adapter mappings and typed errors.
- Contract tests pinned to the supported KRAIL version.
- Fixture-based integration tests using a real local KRAIL project.
- API authorization and path-containment tests.
- Run-service lifecycle and crash-recovery tests.
- Frontend component tests for graph/table/provenance states.
- Browser end-to-end tests for the five primary workspaces.
- A static guard that fails if non-adapter application modules import `rail`.
- A static guard that fails on direct writes to KRAIL-owned project paths outside approved test
  fixtures.
- An upgrade job that runs the contract suite against the next candidate KRAIL version without
  changing the production pin.

## 11. Resolved product decisions

1. **Deployment:** use one platform API architecture for local and hosted operation. Ship local
   single-node first, then add hosted infrastructure without changing KRAIL ownership semantics.
2. **Project storage:** support platform-managed Git workspaces and operator-selected local
   directories at arbitrary locations. Canonicalize paths, record workspace type, and enforce
   configured path permissions rather than assuming every project is below one platform root.
   Non-Git linked directories remain read-only until explicitly initialized or imported.
3. **Execution trust:** workflows may execute arbitrary commands when their assigned permission
   profile grants it. Profiles can instead restrict paths, command families, network destinations,
   secrets, runtime, and resources. The workflow cannot expand its own profile.
4. **Collaboration:** no concurrent human record editing in the first release. Git remains the
   versioning and adoption boundary. Multiple AI workflows may run concurrently in isolated
   worktrees and publish through an atomic batch-integration commit.
5. **KRAIL dependency policy:** follow KRAIL as an upstream PyPI dependency. Use a compatible
   pre-`0.3` declaration, commit the exact resolved version, and run adapter contract tests for each
   dependency update. Do not fork or mirror KRAIL code in RAIL.

## 12. Explicit non-goals for the first release

- Reimplementing KRAIL features in RAIL.
- A general-purpose notebook hosting environment.
- Distributed workflow scheduling across many machines.
- Real-time collaborative editing of project files.
- A second graph database or mirrored ontology database.
- A bespoke RAIL MCP server when the KRAIL MCP server can expose the project directly.
