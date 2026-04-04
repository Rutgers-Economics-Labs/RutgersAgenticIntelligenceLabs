# WO-4.3 — Agent UI Upgrade

**Status:** blocked  
**Spec:** `specs/frontend.md`  
**Depends on:** WO-4.1, WO-2.2  
**Blocks:** nothing  

---

## Goal

Upgrade the agent page to show a session list panel on the left, a context snapshot card before the first message, and bind the conversation to the project via URL params.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/app/[project]/agent/page.tsx` | **Modify** | Add session list + context snapshot card |
| `packages/web/components/agent/SessionList.tsx` | **Create** | Left panel: previous conversations |
| `packages/web/components/agent/ContextSnapshot.tsx` | **Create** | "I have access to..." card |
| `packages/web/components/agent/AgentChat.tsx` | **Modify** | Handle `context_snapshot` SSE event |

---

## Steps

### 1. Create `SessionList.tsx`

Left panel showing previous `agentSessions` for the current project.

```tsx
// Uses: useQuery(api.agent.listByProject, { projectSlug: params.project })
// Each session shows: first message (truncated), relative date, message count
// Clicking a session loads it: replace current conversation with that session's history
// "+ New Chat" button at top clears current conversation

interface SessionListProps {
  projectSlug: string
  activeSessionId?: string
  onSelect: (sessionId: string) => void
  onNew: () => void
}
```

Layout: fixed-width left panel (~240px), scrollable list, collapsed on mobile.

### 2. Create `ContextSnapshot.tsx`

Shown as the first card in the conversation area when no messages exist yet.

```tsx
// Displayed after receiving the `context_snapshot` SSE event
// or fetched from GET /api/v1/projects/{slug}/context on page load

interface ContextSnapshotProps {
  context: {
    project: { name: string; status: string; last_hydrated: string }
    ontology: { classes: { name: string; instance_count: number }[] }
    data_sources: { slug: string; name: string }[]
    pipelines: { slug: string; name: string }[]
  }
}
```

Display as a card with sections:
```
📊 NJ Economic Analysis  [hydrated]
─────────────────────────────────────
I have access to:
  • 3 classes: County (3,142), State (50), LaborIndicator (48,600)
  • 2 data sources: nj_unemployment, census_counties
  • 1 pipeline: nj-hydration (last run: 2 hours ago)
─────────────────────────────────────
Ask me anything about this project's data.
```

### 3. Update `AgentChat.tsx`

Handle the `context_snapshot` event type in the SSE stream:

```tsx
case "context_snapshot":
  setContextSnapshot(event.data)
  break
```

Don't render this as a message — it feeds the `ContextSnapshot` component.

### 4. Update agent page layout

```tsx
// app/[project]/agent/page.tsx
<div className="flex h-full">
  <SessionList
    projectSlug={params.project}
    activeSessionId={activeSessionId}
    onSelect={setActiveSessionId}
    onNew={() => { setActiveSessionId(undefined); setMessages([]) }}
  />
  <div className="flex flex-1 flex-col">
    {messages.length === 0 && contextSnapshot && (
      <ContextSnapshot context={contextSnapshot} />
    )}
    <AgentChat
      projectSlug={params.project}
      sessionId={activeSessionId}
      messages={messages}
      onMessages={setMessages}
    />
  </div>
</div>
```

### 5. Persist sessions

When the first message is sent in a new conversation, create an `agentSession` in Convex:
```tsx
const sessionId = await convex.mutation(api.agent.createSession, {
  projectSlug: params.project,
  title: message.slice(0, 60),
})
setActiveSessionId(sessionId)
```

Subsequent messages append to the session.

---

## Acceptance

- [ ] Session list panel shows previous conversations for the project
- [ ] Clicking a past session loads its message history
- [ ] "New Chat" button clears the conversation
- [ ] `ContextSnapshot` card appears before the first message with correct class counts and data sources
- [ ] Context snapshot updates when a new `context_snapshot` SSE event is received
- [ ] Agent API calls include `?project={slug}`
