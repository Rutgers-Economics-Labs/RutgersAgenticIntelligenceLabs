# WO-5.3 — Schedule UI

**Status:** blocked  
**Spec:** `specs/schedule.md`, `specs/frontend.md`  
**Depends on:** WO-5.2  
**Blocks:** nothing  

---

## Goal

Add schedule controls to the frontend: a schedule modal on pipeline cards, active collection badges, and a schedule status section on the jobs page.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/app/[project]/pipelines/page.tsx` | **Modify** | Add schedule modal + active badge to pipeline cards |
| `packages/web/app/[project]/jobs/page.tsx` | **Modify** | Add schedule status section |
| `packages/web/components/schedules/ScheduleModal.tsx` | **Create** | Schedule creation/edit dialog |
| `packages/web/lib/api.ts` | **Modify** | Add `schedules` namespace |

---

## Steps

### 1. Create `ScheduleModal.tsx`

Dialog opened from a pipeline card's "Schedule" button.

```tsx
// Fields:
// - Frequency: radio buttons (Hourly / Daily / Weekly / Custom cron)
// - Custom cron: text input (shown when Custom selected)
// - Collection window: optional (None / 7 days / 14 days / 30 days / Custom)
// - Enable immediately: checkbox (default true)

// On submit: POST /api/v1/schedules
// {project_slug, pipeline_slug, frequency, window, enabled}
```

Show current schedule if one exists. "Remove schedule" button deletes it.

### 2. Active collection badge on pipeline cards

In the pipelines list, check if a `scheduledPipeline` exists for this pipeline:

```tsx
const schedules = useQuery(api.schedules.listByProject, { projectSlug: params.project })

// For each pipeline card:
const activeSchedule = schedules?.find(s => s.pipelineSlug === pipeline.slug && s.status === "active")

// Render badge:
{activeSchedule && (
  <Badge variant="outline" className="text-green-400 border-green-400">
    ● Collecting · {activeSchedule.frequency}
  </Badge>
)}
```

### 3. Schedule status section on jobs page

Below the job list, add a "Active Schedules" section:

```
Active Schedules
─────────────────────────────────────────────────
nj-live-unemployment    Hourly    Ends in 5d 3h    [Pause]  [Remove]
─────────────────────────────────────────────────
[+ Add Schedule]
```

Each row shows: pipeline name, frequency, time until window expires (or "Indefinite"), Pause and Remove buttons.

Clicking `[+ Add Schedule]` opens `ScheduleModal` with no pre-selected pipeline.

### 4. Add `schedules` namespace to `lib/api.ts`

```typescript
schedules: {
  list: (projectSlug: string) => GET(`/schedules?project=${projectSlug}`),
  create: (data: CreateScheduleRequest) => POST("/schedules", data),
  update: (id: string, data: Partial<Schedule>) => PUT(`/schedules/${id}`, data),
  remove: (id: string) => DELETE(`/schedules/${id}`),
  pause: (id: string) => POST(`/schedules/${id}/pause`, {}),
  resume: (id: string) => POST(`/schedules/${id}/resume`, {}),
}
```

---

## Acceptance

- [ ] Pipeline cards show an "Active Collection" badge when a schedule is running
- [ ] Clicking "Schedule" on a pipeline card opens the schedule modal
- [ ] Creating a schedule from the modal calls `POST /api/v1/schedules` and shows a success toast
- [ ] Jobs page shows active schedules with pause/remove buttons
- [ ] Pausing a schedule changes its status to `paused` and removes the active badge
