# Work Orders

Each work order is a self-contained implementation task. Complete them in dependency order. All items in a phase can be started as soon as their dependencies are done.

## Status Key

| Symbol | Meaning |
|--------|---------|
| ✅ | Done |
| 🔵 | In progress |
| ⬜ | Ready — no blockers |
| 🔒 | Blocked — depends on unfinished work |

---

## Phase 0 — Foundation (do these first)

| WO | Title | Status | Blocks |
|----|-------|--------|--------|
| [WO-0.1](WO-0.1-kernel-yaml.md) | Ontology Kernel YAML | ⬜ | WO-0.2, WO-1.2 |
| [WO-0.2](WO-0.2-connector-extends.md) | Connector `extends` Resolution | ⬜ | WO-1.1, WO-4.2 |
| [WO-0.3](WO-0.3-projects-schema.md) | Projects Schema Update | ⬜ | WO-1.2, WO-2.3, WO-3.1, WO-4.1 |

All three Phase 0 items are independent — they can be worked in parallel.

---

## Phase 1 — Connector & Template Registry

| WO | Title | Status | Depends on |
|----|-------|--------|------------|
| [WO-1.1](WO-1.1-connector-template-ui.md) | Connector Template UI | 🔒 | WO-0.2 |
| [WO-1.2](WO-1.2-ontology-templates.md) | Ontology Templates | 🔒 | WO-0.3 |

---

## Phase 2 — Project Navigation

| WO | Title | Status | Depends on |
|----|-------|--------|------------|
| [WO-2.1](WO-2.1-topbar-project-switcher.md) | Top Bar + Project Switcher | ⬜ | — |
| [WO-2.2](WO-2.2-project-scoped-routes.md) | Project-Scoped Route Layout | 🔒 | WO-2.1 |
| [WO-2.3](WO-2.3-new-project-pages.md) | New Project Pages | 🔒 | WO-2.2 |

WO-2.1 is independent and can start in parallel with Phase 0.

---

## Phase 3 — GitHub Sync

| WO | Title | Status | Depends on |
|----|-------|--------|------------|
| [WO-3.1](WO-3.1-github-app-service.md) | GitHub App Service | ⬜ | — |
| [WO-3.2](WO-3.2-github-webhook.md) | GitHub Webhook (GitHub → Platform) | 🔒 | WO-3.1, WO-0.3 |
| [WO-3.3](WO-3.3-publish-to-github.md) | Publish to GitHub (Platform → GitHub) | 🔒 | WO-3.1, WO-3.2 |

WO-3.1 is independent and can start in parallel with Phase 0.

---

## Phase 4 — Domain Agent Upgrade

| WO | Title | Status | Depends on |
|----|-------|--------|------------|
| [WO-4.1](WO-4.1-agent-context-snapshot.md) | Project-Scoped Agent Context | 🔒 | WO-0.3 |
| [WO-4.2](WO-4.2-agent-new-tools.md) | New Agent Tools | 🔒 | WO-0.2, WO-3.1, WO-4.1 |
| [WO-4.3](WO-4.3-agent-ui-upgrade.md) | Agent UI Upgrade | 🔒 | WO-4.1, WO-2.2 |

---

## Phase 5 — Scheduled Pipelines

| WO | Title | Status | Depends on |
|----|-------|--------|------------|
| [WO-5.1](WO-5.1-incremental-hydration.md) | Incremental Hydration Mode | ⬜ | — |
| [WO-5.2](WO-5.2-scheduler-service.md) | Scheduler Service | 🔒 | WO-5.1 |
| [WO-5.3](WO-5.3-schedule-ui.md) | Schedule UI | 🔒 | WO-5.2 |

WO-5.1 is independent — can start any time.

---

## Phase 6 — rail-py Package

| WO | Title | Status | Depends on |
|----|-------|--------|------------|
| [WO-6.1](WO-6.1-rail-py-skeleton.md) | Package Skeleton | ⬜ | — |
| [WO-6.2](WO-6.2-rail-py-ontology-agent.md) | OntologyView + AgentClient | 🔒 | WO-6.1 |

WO-6.1 is independent — can start any time.

---

## Recommended Starting Order

If working solo or in a small team, do these first — they're all independent and unblock the most:

1. **WO-0.1** (Kernel YAML) — 2–3 hours
2. **WO-0.2** (Connector extends) — 4–6 hours
3. **WO-0.3** (Projects schema) — 2–3 hours
4. **WO-2.1** (Top bar) — 2–3 hours
5. **WO-3.1** (GitHub service) — 3–4 hours
6. **WO-5.1** (Incremental hydration) — 2–3 hours
7. **WO-6.1** (rail-py skeleton) — 4–5 hours

After those 7 are done, everything else unlocks.
