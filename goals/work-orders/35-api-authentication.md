# Work Order 35 — API Authentication

## Layer
8 — Infrastructure and Scale

## Goal
Add token-based API authentication to the FastAPI backend so that the platform can be safely deployed publicly or shared with collaborators, without exposing pipeline configs, ontology data, or agent capabilities to unauthenticated requests.

## Steps

### 1. Auth config
Add to `packages/api/app/core/config.py`:
```python
auth_enabled: bool = False           # set True in production
api_key_header: str = "X-API-Key"   # header name
api_keys: list[str] = []            # comma-separated list in env
jwt_secret: str = ""                 # for session tokens (optional, for future)
```

When `auth_enabled=False`, all routes are open (development mode — existing behavior preserved).

### 2. API key dependency
File: `packages/api/app/core/auth.py`

```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name=settings.api_key_header, auto_error=False)

async def require_api_key(key: str = Security(api_key_header)) -> str:
    if not settings.auth_enabled:
        return "dev"
    if key not in settings.api_keys:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return key
```

### 3. Apply to all routers
Add `dependencies=[Depends(require_api_key)]` to every router registration in `main.py`:

```python
app.include_router(sql_router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(agent_router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
# ... all routers
```

Exception: `GET /health` and `GET /api/v1/agent/models` may remain public.

### 4. Convex → API authentication
The Convex backend calls the FastAPI API (e.g., to trigger jobs). Pass the API key via an environment variable in Convex:

In `packages/web/convex/http.ts` (or action files), read `RAIL_API_KEY` from `process.env` and include it in the `X-API-Key` header.

Document in `specs/api.md` and use a root `.env` entry:
```
RAIL_API_KEY=your-secret-key
```

### 5. Frontend API key injection
In `packages/web/lib/api.ts`, read `NEXT_PUBLIC_RAIL_API_KEY` from `process.env` and inject into all fetch calls as `X-API-Key` header.

Note: This is a server-side Next.js app so the key can be kept server-only using `RAIL_API_KEY` (not `NEXT_PUBLIC_`) in API route handlers if the app adds server-side fetch wrappers in the future.

### 6. Docs / OpenAPI
FastAPI's auto-generated OpenAPI docs (`/docs`) should show the API key security scheme. FastAPI handles this automatically with `APIKeyHeader`.

### 7. Rate limiting (optional, configurable)
Add optional per-key rate limiting using `slowapi`:
```python
rate_limit_per_minute: int = 60    # 0 = disabled
```

When enabled, each API key is limited to `rate_limit_per_minute` requests per minute. Returns `HTTP 429 Too Many Requests` when exceeded.

Add `slowapi>=0.1.9` to `packages/api/pyproject.toml` if rate limiting is enabled.

## Affected Files
- `packages/api/app/core/config.py` — add auth settings
- `packages/api/app/core/auth.py` — **create**
- `packages/api/app/main.py` — apply `require_api_key` dependency to all routers
- `packages/web/lib/api.ts` — inject API key header
- `packages/web/convex/*.ts` (action files) — inject API key header
- Root `.env` — set `AUTH_ENABLED`, `API_KEYS`, `RAIL_API_KEY`
- `specs/api.md` — document authentication scheme and env vars

## Acceptance Criteria
- [ ] `AUTH_ENABLED=false` (default) — all requests succeed without a key (no behavior change)
- [ ] `AUTH_ENABLED=true` with no key header → `401 Unauthorized`
- [ ] `AUTH_ENABLED=true` with valid key → request succeeds
- [ ] `GET /health` returns 200 without a key even when auth is enabled
- [ ] OpenAPI docs (`/docs`) shows "Authorize" button with API key input
- [ ] Convex job triggers include the API key header when `RAIL_API_KEY` is set
