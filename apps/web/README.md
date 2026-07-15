# RAIL web platform

Next.js visual control plane for registered KRAIL projects.

```bash
npm ci
KRAIL_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

`KRAIL_API_BASE_URL` supplies server-rendered reads. Interactive workflow/project controls use
`NEXT_PUBLIC_KRAIL_API_URL` (default `http://127.0.0.1:8000/api/v1`) and the API's explicit
`RAIL_WEB_ORIGINS` allowlist. Product routes live under `/krail-*`; browser code never reads local
workspaces or calls removed legacy endpoints.
