You are writing and running tests for the RAIL platform. The platform has three layers: a Python engine, a FastAPI service, and a Next.js/Convex frontend.

## Test locations

- `packages/api/tests/` — pytest tests for FastAPI routes and services
- `packages/engine/tests/` — pytest tests for the engine modules
- `packages/web/__tests__/` or `packages/web/app/**/*.test.tsx` — Jest/React Testing Library for frontend

## Step 1 — Understand what to test

Read the source files for the component the user wants to test. If the user did not specify, default to:
1. All FastAPI routes in `packages/api/app/routers/`
2. `yaml_service.validate()` and `yaml_service.parse()`
3. `ontology_service` query functions (using a fixture quadstore)

## Step 2 — Check what tests already exist

```bash
find packages/api/tests packages/engine/tests -name "*.py" 2>/dev/null
find packages/web -name "*.test.*" -not -path "*/node_modules/*" 2>/dev/null
```

## Step 3 — Write the tests

### Python (pytest) guidelines

- Use `pytest` with `httpx.AsyncClient` for FastAPI route tests.
- Mount the FastAPI app with `app` from `app.main` and use `ASGITransport`.
- Mock external dependencies (Convex HTTP calls) with `unittest.mock.AsyncMock` or `respx`.
- For `ontology_service` tests, create a minimal in-memory owlready2 World as a fixture.
- For `yaml_service` tests, use inline YAML strings — no file I/O needed.
- Test both the happy path and error cases (missing fields, invalid YAML, 404s).
- Name test files `test_{module}.py`; name test functions `test_{what}_{condition}`.

Example fixture for mocking Convex:
```python
import respx, httpx
from unittest.mock import patch

@pytest.fixture
def mock_convex(respx_mock):
    respx_mock.post("https://colorless-elephant-150.convex.cloud/api/query").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    yield respx_mock
```

### TypeScript (Jest) guidelines

- Use `@testing-library/react` for component tests.
- Mock `convex/react` `useQuery` with `jest.mock`.
- Mock `lib/api.ts` functions for page-level tests.
- Focus on: Sidebar renders correct links; page renders empty/loading/error states.

## Step 4 — Run the tests

For Python:
```bash
cd packages/api && python -m pytest tests/ -v 2>&1 | head -100
```

For engine:
```bash
cd packages/engine && python -m pytest tests/ -v 2>&1 | head -100
```

For frontend:
```bash
cd packages/web && npm test -- --watchAll=false 2>&1 | head -100
```

## Step 5 — Fix failures

If tests fail:
1. Read the failure message carefully.
2. Read the source file for the failing test.
3. Fix the test if the test is wrong, or fix the source if the source is wrong.
4. Re-run the specific failing test: `python -m pytest tests/test_foo.py::test_bar -v`
5. Do NOT mark tests as xfail or skip to hide failures.

## Step 6 — Commit

```bash
git add packages/api/tests/ packages/engine/tests/ packages/web/__tests__/
git commit -m "test: Add tests for [component]"
```

## Rules

- Every new FastAPI route should have at least one test: happy path + one 4xx case.
- `yaml_service.validate()` must have tests for every config type and every required-field error.
- Do not write tests that mock the thing being tested (e.g., do not mock `yaml_service` in a test of `yaml_service`).
- Do not require a running Convex instance or internet access for tests — mock all external HTTP.
- If `packages/api/tests/` does not exist, create it with a `conftest.py` that sets up the test `app` and async client.
