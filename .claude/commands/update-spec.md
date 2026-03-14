You are updating the RAIL platform spec files to accurately reflect the current state of the code. Spec files must never contain aspirational content — only what is actually implemented.

## Spec file locations

- `specs/architecture.md` — monorepo layout, data flows, env vars, design decisions
- `specs/api.md` — FastAPI service: routes, services, config settings
- `specs/frontend.md` — Next.js/Convex: schema, functions, pages, lib/api.ts
- `packages/engine/specs/architecture.md` — engine-only directory layout and data flow
- `packages/engine/specs/yaml-config.md` — all three YAML config schemas
- `packages/engine/specs/engine.md` — engine module function signatures
- `packages/engine/specs/plugins.md` — transform and analysis plugin contracts
- `packages/engine/specs/ui.md` — Streamlit app tabs and CLI entry point

## Your task

1. **Determine what changed.** Run `git diff HEAD~1..HEAD --stat` and `git diff HEAD~1..HEAD` to see which files were modified in the last commit. If the user told you what changed, focus on those files first.

2. **Read the changed source files** in full. Do not rely on memory — re-read every file that was modified.

3. **Read the relevant spec files** that need updating.

4. **For each spec file that is now stale:**
   - Update function signatures, field names, and behavior descriptions to match the actual code.
   - Add new sections for new modules/routes/pages/schemas.
   - Remove sections that describe deleted code.
   - Never invent behavior — if you are unsure about something, read the source file again.

5. **Verify correctness** by re-reading the spec section you just wrote alongside the source code one more time.

6. **Commit** the spec changes: `git add specs/ packages/engine/specs/ && git commit -m "docs: Update specs to match [describe what changed]"`

## Rules

- No aspirational or roadmap content in spec files.
- Table of function signatures must exactly match the Python/TypeScript signatures in source.
- Route tables must exactly match the FastAPI router decorators.
- Convex schema tables must exactly match `convex/schema.ts`.
- If a file was not changed by the recent commits, do not modify its spec unless you have confirmed it is stale by reading both the spec and the source.
