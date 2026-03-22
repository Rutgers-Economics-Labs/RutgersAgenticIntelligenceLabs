# Work Order 08 — Job Detail Page

## Goal
Implement `/jobs/[id]` as a full job detail page showing step timeline, streaming logs, and links to the output data.

## Current State
`/jobs` lists jobs but "View →" links to `/jobs/{_id}` which returns 404. `GET /api/v1/jobs/{id}` and `GET /api/v1/jobs/{id}/logs` both work.

## Steps

### 1. Create the page file
`packages/web/app/(dashboard)/jobs/[id]/page.tsx`

### 2. Fetch job data
- `useQuery(api.jobs.get, { jobId: id })` — reactive job record
- `useQuery(api.jobs.getLogs, { jobId: id, limit: 500 })` — reactive logs

### 3. Header
- Pipeline slug (monospace) + status badge
- Started at / finished at / duration
- "Cancel" button if status is `queued` or `running` (calls `DELETE /jobs/{id}`)

### 4. Step timeline
Horizontal or vertical timeline of `stepResults`:
- Each step shows: name, status icon (pending/running/done/failed), row count, duration
- Running step pulses/animates
- Failed step shows `errorMessage` inline

### 5. Log viewer
Scrollable log panel with:
- Level-colored lines: `info` = default, `warn` = yellow, `error` = red
- Step name badge when step changes
- Auto-scroll to bottom while job is running (pause on manual scroll up)
- Line count shown in header

### 6. Output links (on success)
If `status === "success"`:
- "Explore Data →" button → navigates to `/explorer`
- "Open SQL →" button → navigates to `/sql`
- "Open in Workspace →" button → navigates to `/workspace` with a prefilled message like "The pipeline just finished. What's in the data?"

### 7. Error display
If `status === "failed"`, show `errorMessage` in a red callout above the logs.

## Affected Files
- `packages/web/app/(dashboard)/jobs/[id]/page.tsx` — **create**
- `packages/web/app/(dashboard)/jobs/page.tsx` — update "View →" link to use `_id`

## Acceptance Criteria
- [ ] Clicking "View →" on the Jobs list opens the detail page
- [ ] Step timeline shows correct statuses and row counts
- [ ] Logs stream in real time while job is running
- [ ] Log level coloring works correctly
- [ ] Success state shows output links
- [ ] Failed state shows error message prominently
