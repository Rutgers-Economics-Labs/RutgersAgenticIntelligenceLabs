# Frontend Command Center

This document is the implementation plan and product spec for the real RAIL
frontend that replaces the legacy Streamlit explorer.

The frontend should be a proper application built in React and Tailwind and
should treat the Python backend as the orchestrator for:

- planner chat
- project/repo state
- ontology and hydration state
- worker execution
- approvals
- review/adoption
- secrets-aware runner control

The frontend is not a second orchestrator. It is the human-facing command
center for repo truth plus live operational state.

## Product Goal

The UI should let a user:

- understand the full state of a project from the repo and live runtime
- see what the planner is doing and why
- see what each worker is doing right now
- inspect exactly which files each worker is editing
- inspect commands, diffs, verification, blockers, and approvals
- intervene when needed without losing the durable Git-backed history

The UI should feel like:

- a research operations console
- a repo-aware planning tool
- a review surface for agent work

It should not feel like:

- a CRUD admin panel
- a chat-only toy
- a log dump with no hierarchy

## Core Design Principles

### 1. Repo-first rendering

Durable project state should render from Git-backed files first.

Primary examples:

- `research_plan/current_plan.md`
- `research_plan/task_board.md`
- `research_plan/tasks/*.md`
- `research_plan/approvals.md`
- `research_plan/blockers.md`
- `research_plan/sessions/**/summary.md`
- `research_plan/sessions/**/diff.md`
- `research_plan/sessions/**/todos.md`
- `research_plan/sessions/**/verification.md`
- `.ontology/**`
- `topics/**`
- `specs/**`
- `artifacts/**`

### 2. Live runtime augmentation

The database and runner APIs should augment repo state with live information
that has not yet been mirrored into files.

Examples:

- active worker session handles
- current status
- latest streamed runner events
- reconnect metadata
- approval requests in progress
- current CLI/runner tool activity

### 3. Agent observability is first-class

The user explicitly wants to know more than the abstract task goal.

The UI must expose, per agent session:

- current task
- current status
- assigned repo paths
- active workspace path and branch
- files changed so far
- commands started/completed
- latest model messages and planner relays
- normalized runner events
- verification progress/results
- unresolved blockers/todos

### 4. Planning and execution are separate but connected

The planner is the top-level coordinator.
Workers are subordinate execution units.

The UI must make this distinction obvious:

- planner proposes and sequences
- workers execute inside bounded workspaces
- review/adoption is a separate phase

### 5. Thinking should be visible, but curated

We should expose enough of an agent's internal flow to build trust and enable
intervention, but not dump every token or create visual spam.

The UI should prioritize:

- planner summaries
- normalized reasoning checkpoints
- explicit “current focus”
- discrete events and actions
- command/file activity

It should avoid:

- raw unbounded token stream by default
- giant walls of console logs
- duplicate views of the same event

## Frontend Stack

Recommended stack:

- React
- Tailwind CSS
- TypeScript
- Next.js App Router or Vite + React Router
- TanStack Query for API state
- SSE or polling for live updates

Recommended near-term choice:

- Next.js

Reasons:

- route-based app shell is useful for multi-page command center flows
- server-side rendering can help repo-backed content pages
- easy local dev experience

## Top-Level Information Architecture

The app should have six primary surfaces:

1. Project Home
2. Planner
3. Runs
4. Review
5. Repo
6. Ontology and Data

Optional later surfaces:

- Artifacts
- Costs and Usage
- Admin/Secrets

## Page Plan

### 1. Project Home

Route:

- `/projects/:slug`

Purpose:

- landing page for one project
- high-signal project summary
- immediate understanding of active work

Primary panels:

- planner summary card
- active task board snapshot
- active worker sessions
- latest review-ready runs
- blockers and approvals
- latest artifacts
- repo summary

Must show:

- current plan summary from `research_plan/current_plan.md`
- current board summary from `research_plan/task_board.md`
- latest planner message
- all active sessions, including planner and worker roles
- next required human action

Key widgets:

- `Current Plan`
- `Next Action`
- `Active Sessions`
- `Awaiting Approval`
- `Review Queue`
- `Recent Artifacts`
- `Repo Health`

### 2. Planner Page

Route:

- `/projects/:slug/planner`

Purpose:

- the main planner chat and orchestration console

Layout:

- left: planner thread and composer
- center: task board and selected task details
- right: live context and escalation panel

Must show:

- planner messages
- tool calls made by planner
- planner-created tasks
- task transitions
- approval requests
- planner-visible worker questions

Task board columns:

- backlog
- ready
- awaiting approval
- running
- blocked
- review
- done
- cancelled

Task detail drawer must show:

- description
- assigned role
- runner
- approval state
- acceptance criteria
- assigned repo paths
- latest run summary
- links to session folder and review files

### 3. Runs Page

Route:

- `/projects/:slug/runs`
- `/projects/:slug/runs/:sessionId`

Purpose:

- show all planner and worker sessions across the project
- make agent activity legible in real time

This is where “what every agent is working on” becomes explicit.

Runs list columns:

- session id
- role
- runner
- status
- task
- started at
- workspace branch
- review status
- last event

Session detail layout:

- top summary strip
- activity timeline
- workspace/files panel
- commands panel
- messages/thinking panel
- verification panel

The session detail page is the most important agent observability page.

It must show:

- current role and runner
- current workspace path
- current branch/worktree
- normalized event timeline
- list of changed files
- latest commands
- tool results
- latest agent messages
- approval requests
- planner relays
- verification state

### 4. Review Page

Route:

- `/projects/:slug/review`
- `/projects/:slug/review/:sessionId`

Purpose:

- diff/review/adoption surface for completed worker sessions

Must show:

- changed files
- diff summary
- unresolved todos
- failed checks
- review status
- verification output
- archive/adopt/merge controls

Review queue list:

- session
- role
- task
- review status
- verification status
- changed file count
- last updated

Review detail:

- summary
- diff viewer
- todos list
- blockers list
- verification details
- session transcript summary
- adopt/archive controls

### 5. Repo Page

Route:

- `/projects/:slug/repo/*`

Purpose:

- browse repo-backed project content

Primary tree roots:

- `.ontology/`
- `specs/`
- `research_plan/`
- `topics/`
- `agents/`
- `skills/`
- `artifacts/`
- `scripts/`

Must support:

- syntax-aware file viewing
- Markdown rendering
- YAML rendering
- JSON rendering
- diff-aware links from sessions/tasks

Important deep links:

- task -> task markdown
- task -> assigned repo paths
- run -> session files
- review -> diff/todos/verification

### 6. Ontology and Data Page

Route:

- `/projects/:slug/ontology`

Purpose:

- replace the Streamlit ontology explorer with a real app surface

Must show:

- ontology file summary
- source inventory
- pipeline inventory
- hydration status
- latest hydration artifacts
- validation results
- entities and relationships explorer

Subtabs:

- Schema
- Sources
- Pipelines
- Hydration Runs
- Entity Explorer

### 7. Artifacts Page

Route:

- `/projects/:slug/artifacts`

Purpose:

- user-facing output browser

Must show:

- reports
- PDFs
- dashboards
- chart bundles
- output provenance back to tasks/sessions when possible

### 8. Approvals Page

Route:

- `/projects/:slug/approvals`

Purpose:

- central place for execution approvals and publish/adoption approvals

Must show:

- pending approvals
- resolved approvals
- approval type
- related task/session
- requested by role
- requested at / resolved at
- notes

## Agent Observability Spec

This is the critical requirement.

The UI should expose four layers of visibility for each agent session.

### Layer 1. Executive summary

Always visible.

Fields:

- role
- runner
- task title
- status
- workspace branch
- review status
- current focus
- last update time

`Current focus` should be derived from the latest meaningful event or message.

Examples:

- “Editing county labor source YAML”
- “Running verification script”
- “Waiting for planner approval”
- “Investigating failed income series fetch”

### Layer 2. Activity timeline

Chronological and normalized.

Event types to render:

- session created
- workspace created
- setup started/completed
- progress
- planner relays
- approval requested
- question asked
- command started/completed
- file change detected
- verification started/completed
- diff ready
- completed
- failed
- cancelled

Each timeline row should show:

- timestamp
- event label
- concise summary
- expandable raw details

### Layer 3. Workspace and file activity

This answers:

- what files is the agent editing?
- where is it working?

Required fields:

- workspace path
- workspace branch
- assigned repo paths
- changed files
- changed files grouped by folder
- diff summary

Each changed file should show:

- current status
- how it was discovered
- link to repo viewer
- link to diff segment if available

### Layer 4. Command and message detail

This answers:

- what is the agent actually doing right now?
- what did it say?
- what shell commands did it run?

Required surfaces:

- latest agent messages
- latest planner relays
- command executions
- command outputs
- stderr/stdout tails

For local CLI runners, command executions are especially important.

## “What The Agent Is Thinking”

The user wants to see more than the coarse task label.

We should implement this as a structured “Thought Process” panel, not raw chain
of thought.

The panel should contain:

- current focus
- recent decisions
- recent questions
- recent planner instructions
- recent tool/command actions

Allowed sources for this panel:

- agent progress messages
- planner relay messages
- normalized event summaries
- command descriptions

Not required:

- full private reasoning traces
- token-level hidden thoughts

In practice, the panel should feel like:

- “agent work log”
- “working notes”
- “execution narrative”

## Internal State Mapping

The frontend should reflect two classes of state.

### A. Durable repo state

Examples:

- plan docs
- tasks
- approvals index
- blockers
- session summaries
- review files
- ontology configs
- topics
- artifacts

### B. Operational live state

Examples:

- running agents
- current session status
- recent runner events not yet mirrored into files
- reconnect handles
- active verification progress

The UI should merge these into a unified view without hiding which source is
authoritative.

Recommended visual treatment:

- `Repo-backed`
- `Live`

Small badges or labels are enough.

## API And Data Surfaces Needed

The current backend already exposes much of the skeleton. The frontend needs a
clean read model for each page.

### Project Home read model

Should include:

- project metadata
- current plan path and rendered summary
- task board path and parsed task summary
- active sessions
- review queue
- approvals
- blockers
- recent artifacts

### Planner read model

Should include:

- planner thread messages
- current task board
- task detail metadata
- planner tools/actions
- approvals and blockers

### Runs read model

Should include:

- session list
- session detail
- event timeline
- workspace metadata
- review metadata
- command list
- changed files
- latest messages

### Review read model

Should include:

- `summary.md`
- `diff.md`
- `todos.md`
- `verification.md`
- changed files
- verification state
- adoption controls

### Repo read model

Should include:

- repo tree
- file content
- syntax kind
- optional blame/commit context later

### Ontology read model

Should include:

- schema file content
- source inventory
- pipeline inventory
- hydration status
- validation errors
- entity browser data

## Route-to-State Mapping

### `/projects/:slug`

Pull from:

- project summary API
- repo-backed plan/task board summary
- live sessions

### `/projects/:slug/planner`

Pull from:

- planner thread endpoint
- planner board endpoint
- approvals endpoint

### `/projects/:slug/runs`

Pull from:

- running sessions list

### `/projects/:slug/runs/:sessionId`

Pull from:

- session detail endpoint
- session files endpoint
- event timeline

### `/projects/:slug/review/:sessionId`

Pull from:

- session review metadata
- session summary/diff/todos/verification files

### `/projects/:slug/repo/*`

Pull from:

- repo content proxy or filesystem-backed API

### `/projects/:slug/ontology`

Pull from:

- ontology metadata API
- hydration inventory API
- validation API

## Interaction Model

### Planner interactions

Allowed actions:

- send planner message
- create task
- update task
- request approval
- launch worker

### Worker interactions

Allowed actions:

- inspect current status
- inspect event timeline
- send message
- approve
- cancel

### Review interactions

Allowed actions:

- inspect diff
- inspect verification
- adopt/merge
- archive
- return to planner as blocked

## Recommended Layout System

Desktop:

- three-column command center layout for planner-heavy screens
- split-pane detail layout for runs and review

Tablet:

- two-pane layout with collapsible right rail

Mobile:

- stacked layout focused on planner summary, active sessions, and review queue

## Visual Language

The frontend should look intentional and operational.

Use:

- clear neutral base
- strong accent for live execution state
- distinct colors for statuses
- restrained motion
- typography with strong hierarchy

Suggested status colors:

- backlog: muted slate
- ready: blue
- awaiting approval: amber
- running: cyan
- blocked: red
- review: violet
- done: green
- cancelled: gray

## Build Order

Implement in this order:

1. App shell and project routing
2. Project Home
3. Planner page
4. Runs list and session detail
5. Review queue and review detail
6. Repo browser
7. Ontology/data page
8. Artifacts page

## Acceptance Criteria

The frontend is successful when a user can:

1. open a project and immediately understand the current plan
2. see all active agents and what they are doing right now
3. see which files a worker is editing
4. inspect commands and meaningful progress messages
5. approve, block, or cancel work from the app
6. inspect verification and review artifacts before adoption
7. browse the repo and planner state without leaving the app
8. understand the difference between repo truth and live runtime state

## Immediate Next Step

Build the React app shell and implement these first four routes:

- `/projects/:slug`
- `/projects/:slug/planner`
- `/projects/:slug/runs`
- `/projects/:slug/runs/:sessionId`

Those four routes are enough to replace the current “planner plus Streamlit”
workflow with a real command center for planning and agent execution.
