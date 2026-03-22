# Work Order 07 — Workspace Persistence

## Goal
Persist agent sessions across page refreshes and expose a session list so researchers can return to prior conversations.

## Current State
The Workspace page keeps conversation history only in a `useRef` — it is lost on refresh. The `agentSessions` and `workspaces` Convex tables exist but are not used by the frontend.

## Steps

### 1. Session creation on first message
When the user sends their first message (history is empty), call `createSession` before streaming:
```typescript
const { sessionId } = await useMutation(api.agent.createSession)({
  title: message.slice(0, 60),  // first 60 chars as title
  model: selectedModel,
})
```
Store `sessionId` in component state.

### 2. Persist messages after each agent turn
In the `done` event handler, call `appendMessages` with `event.new_messages` to save to Convex.

### 3. Session list sidebar
Add a collapsible left panel to the Workspace page listing recent sessions from `useQuery(api.agent.listSessions, { limit: 20 })`.

Each session shows:
- Title (first message, truncated)
- Model badge
- Relative timestamp

Clicking a session loads it: fetch full session via `api.agent.getSession`, reconstruct `messages` display and populate `historyRef` from `session.messages`.

### 4. Load session on mount from URL
Support `/workspace?session={sessionId}` — on mount, if this param is present, load that session automatically. Update URL when a new session is created: `router.push(\`/workspace?session=${sessionId}\`)`.

### 5. Auto-title update
After the first assistant response, update the session title to a better summarization using the first assistant text (truncated to 80 chars).

```typescript
await appendMessages(sessionId, newMessages)
if (isFirstResponse) {
  await updateTitle(sessionId, firstAssistantText.slice(0, 80))
}
```

### 6. Delete session
Add a delete button (trash icon) on each session list item. Calls `deleteSession`. Clears current view if it was the active session.

## Affected Files
- `packages/web/app/(dashboard)/workspace/page.tsx` — add session management
- `packages/web/convex/agent.ts` — already complete, no changes needed

## Acceptance Criteria
- [ ] First message creates a Convex session record
- [ ] Refreshing the page and selecting a prior session restores the full conversation
- [ ] Session list updates reactively when new sessions are created
- [ ] Deleting a session removes it from the list
- [ ] URL reflects current session ID
