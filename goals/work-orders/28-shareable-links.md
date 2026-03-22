# Work Order 28 — Shareable Workspace Links and Citation Generation

## Layer
6 — Reproducibility and Sharing

## Goal
Generate permanent shareable links to workspace sessions and auto-generate academic-style citations for analysis results, enabling researchers to reference their findings in papers and reports.

## Steps

### 1. Public workspace sharing
Add a `isPublic` flag and `shareToken` to the `workspaces` Convex table:

```ts
isPublic: v.optional(v.boolean()),
shareToken: v.optional(v.string()),  // random 24-char token for the share URL
```

New Convex functions in `workspaces.ts`:
- `enableSharing(workspaceId)` — generates `shareToken`, sets `isPublic: true`
- `disableSharing(workspaceId)` — clears `shareToken`, sets `isPublic: false`
- `getWorkspaceByToken(token)` — public read without auth (for share link access)

### 2. Read-only share page
File: `packages/web/app/share/[token]/page.tsx`

A read-only view of the workspace (no chat input, no edit controls):
- Shows the workspace title and all completed result cells
- Shows a "Created with RAIL" footer with a link to the platform
- No Convex auth required — uses `getWorkspaceByToken`

### 3. Share button in workspace
In the workspace header, add a "Share" button that:
1. Calls `enableSharing` if not already shared
2. Shows a modal with the shareable URL (e.g., `https://rail.app/share/abc123xyz`)
3. Includes a "Copy Link" button
4. Shows "Disable sharing" toggle to revoke

### 4. Citation generation
File: `packages/api/app/services/citation_service.py`

```python
def generate_citation(run: dict, style: str = "apa") -> str:
    """
    Generate a formatted citation for an analysis run.
    Styles: "apa", "chicago", "bibtex"

    APA example:
    RAIL Platform (2025). DiD Analysis: NJ Employment ~ Minimum Wage [Research output].
    Generated {date}. Data version: {hash[:8]}. https://rail.app/share/{token}

    BibTeX example:
    @misc{rail2025did,
      title  = {DiD Analysis: NJ Employment ~ Minimum Wage},
      author = {RAIL Platform},
      year   = {2025},
      note   = {Data version: {hash[:8]}},
      url    = {https://rail.app/share/{token}}
    }
    """
```

### 5. Citation API endpoint
```
POST /api/v1/citations
body: { run_id, style: "apa" | "chicago" | "bibtex", share_url: string }
```

Returns `{ citation: string }`.

### 6. Citation UI
In the workspace version history panel, add a "Cite" button that:
- Calls the citation endpoint
- Shows a modal with the formatted citation in all 3 styles
- "Copy" button per style
- Requires the workspace to have sharing enabled (prompts to enable if not)

## Affected Files
- `packages/web/convex/schema.ts` — add `isPublic`, `shareToken` to workspaces
- `packages/web/convex/workspaces.ts` — add sharing functions + `getWorkspaceByToken`
- `packages/web/app/share/[token]/page.tsx` — **create** (public, outside dashboard layout)
- `packages/api/app/services/citation_service.py` — **create**
- `packages/api/app/routers/citations.py` — **create**
- `packages/api/app/main.py` — register router
- `packages/web/app/(dashboard)/workspace/page.tsx` — share button + cite button

## Acceptance Criteria
- [ ] Share link opens a read-only workspace view without login
- [ ] Disabling sharing makes the share link return 404
- [ ] APA, Chicago, and BibTeX citation styles are generated correctly
- [ ] Citation includes data version hash and share URL
- [ ] Share token is cryptographically random (not sequential IDs)
