# RAIL Command Center

Initial scaffold for the React + Tailwind frontend that replaces the legacy
Streamlit explorer.

## Purpose

This app is the command-center frontend described in:

- [`specs/frontend-command-center.md`](../../specs/frontend-command-center.md)

It is wired to the Python backend and focuses on the first four routes:

- `/projects/:slug`
- `/projects/:slug/planner`
- `/projects/:slug/runs`
- `/projects/:slug/runs/:sessionId`

## Development

```bash
cd apps/web
npm install
npm run dev
```

By default it reads from:

- `http://127.0.0.1:8000/api/v1`

Override with:

```bash
NEXT_PUBLIC_RAIL_API_URL=http://127.0.0.1:8000/api/v1
```
