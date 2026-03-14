You are helping plan a new feature or improvement to the RAIL platform. RAIL is a YAML-driven ontology hydration engine with a FastAPI backend, Next.js/Convex frontend, and owlready2 OWL quadstore.

## Architecture context

Read `specs/architecture.md`, `specs/api.md`, and `specs/frontend.md` before asking questions or generating a plan. Understanding the existing system is required before proposing changes.

## Step 1 — Ask clarifying questions

Before generating any plan, ask the user these questions (skip ones whose answers are obvious from context):

1. **What is the goal?** What should a user be able to do after this is implemented that they cannot do today?
2. **Where does this live?** Engine, API, frontend, Convex schema, all of the above?
3. **Data model** — does this require new Convex tables, new OWL classes/properties, or new YAML config fields?
4. **Scope** — is this a small addition to an existing route/page, or a new end-to-end feature?
5. **Constraints** — any performance, security, or compatibility concerns? Should it work with existing hydrated ontologies?
6. **Priority** — is there a specific part to implement first (e.g., backend before frontend)?

Wait for the user to answer before proceeding.

## Step 2 — Generate a plan

After the user responds, produce a structured plan:

```
## Goal
[one sentence]

## Affected files
[list every file that will be created or modified, with a one-line reason]

## Implementation steps
1. [Step title] — [what changes, why in this order]
2. ...

## Data model changes
[new Convex tables/fields, new OWL classes/properties, new YAML fields — or "none"]

## API changes
[new or modified FastAPI routes — or "none"]

## Frontend changes
[new pages, components, or Convex function calls — or "none"]

## Open questions
[anything still unclear that the user should decide before implementation starts]
```

## Rules

- Only plan what the user actually asked for. Do not add "nice to have" features.
- If a step touches the engine's hydration logic, note that it must be tested with `make hydrate` against a real pipeline.
- If a step changes the Convex schema, note that `npx convex deploy` must be run after.
- If a step changes FastAPI routes, note that the spec in `specs/api.md` must be updated afterward with `/update-spec`.
- Keep the plan concrete enough that any engineer (or Claude) can execute it without further clarification.
