"""
Tests for project secrets and agent secret policy storage (WO-F3.5).
Covers: admin management endpoints, runtime resolver, and delete operations.
"""
import json
import os

import httpx
import pytest
from cryptography.fernet import Fernet

pytestmark = pytest.mark.asyncio

# Use a stable test key so encrypt/decrypt round-trips work in tests.
TEST_FERNET_KEY = "9Zqz24eLhTvUa_N4Ty8DyPimlOh8_zQEIyRiJa2Ggok="
os.environ.setdefault("RAIL_SECRET_FERNET_KEY", TEST_FERNET_KEY)

PROJECT_ID = "project-id-secrets-test"
PROJECT_SLUG = "secrets-project"

PROJECT_DOC = {
    "_id": PROJECT_ID,
    "name": "Secrets Project",
    "slug": PROJECT_SLUG,
    "status": "ready",
    "localRepoPath": None,
    "apiConfigSlugs": [],
}

POLICY_DATA_ROLE = {
    "_id": "policy-id-data",
    "projectId": PROJECT_ID,
    "agentRole": "data",
    "allowedSecretNames": ["FRED_API_KEY", "CENSUS_API_KEY"],
    "createdAt": 1000,
    "updatedAt": 1000,
}


def _make_encrypted_secret(key_name: str, plaintext: str) -> dict:
    fernet = Fernet(TEST_FERNET_KEY.encode())
    return {
        "_id": f"secret-id-{key_name}",
        "projectId": PROJECT_ID,
        "keyName": key_name,
        "encryptedValue": fernet.encrypt(plaintext.encode()).decode(),
        "createdAt": 1000,
        "updatedAt": 1000,
    }


FRED_SECRET = _make_encrypted_secret("FRED_API_KEY", "fred-abc123")
CENSUS_SECRET = _make_encrypted_secret("CENSUS_API_KEY", "census-xyz789")
OTHER_SECRET = _make_encrypted_secret("INTERNAL_DB_PASS", "should-not-see")


def _project_query(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")
    if path in ("projects:get", "projects:getBySlug"):
        return httpx.Response(200, json={"value": PROJECT_DOC})
    return httpx.Response(200, json={"value": None})


def _secrets_query(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")
    if path in ("projects:get", "projects:getBySlug"):
        return httpx.Response(200, json={"value": PROJECT_DOC})
    if path == "projectSecrets:listByProject":
        return httpx.Response(200, json={"value": [FRED_SECRET, CENSUS_SECRET, OTHER_SECRET]})
    if path == "agentSecretPolicies:listByProject":
        return httpx.Response(200, json={"value": [POLICY_DATA_ROLE]})
    return httpx.Response(200, json={"value": None})


def _resolver_query(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")
    args = payload.get("args", {})
    if path in ("projects:get", "projects:getBySlug"):
        return httpx.Response(200, json={"value": PROJECT_DOC})
    if path == "agentSecretPolicies:getByRole":
        role = args.get("agentRole")
        if role == "data":
            return httpx.Response(200, json={"value": POLICY_DATA_ROLE})
        return httpx.Response(200, json={"value": None})
    if path == "projectSecrets:listByProject":
        return httpx.Response(200, json={"value": [FRED_SECRET, CENSUS_SECRET, OTHER_SECRET]})
    return httpx.Response(200, json={"value": None})


# ---------------------------------------------------------------------------
# Admin endpoints — list
# ---------------------------------------------------------------------------


async def test_list_secrets_returns_masked_values(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_secrets_query)

    resp = await client.get(f"/api/v1/projects/{PROJECT_SLUG}/settings/secrets")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["secrets"]) == 3
    # Values must be masked, not plaintext
    for s in data["secrets"]:
        assert s["maskedValue"] != ""
        assert "fred-abc123" not in s["maskedValue"]
        assert "census-xyz789" not in s["maskedValue"]

    assert len(data["policies"]) == 1
    assert data["policies"][0]["agentRole"] == "data"


async def test_list_agent_secret_policies(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_secrets_query)

    resp = await client.get(f"/api/v1/projects/{PROJECT_SLUG}/settings/agent-secret-policies")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["policies"]) == 1
    assert "FRED_API_KEY" in data["policies"][0]["allowedSecretNames"]


# ---------------------------------------------------------------------------
# Admin endpoints — upsert
# ---------------------------------------------------------------------------


async def test_upsert_secret(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_project_query)
    convex_mock.post("/api/mutation").mock(
        return_value=httpx.Response(200, json={"value": "secret-id-new"})
    )

    resp = await client.post(
        f"/api/v1/projects/{PROJECT_SLUG}/settings/secrets",
        json={"keyName": "NEW_API_KEY", "plaintextValue": "my-secret-value"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["keyName"] == "NEW_API_KEY"
    assert "secretId" in data


async def test_upsert_agent_secret_policy(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_project_query)
    convex_mock.post("/api/mutation").mock(
        return_value=httpx.Response(200, json={"value": "policy-id-new"})
    )

    resp = await client.post(
        f"/api/v1/projects/{PROJECT_SLUG}/settings/agent-secret-policies",
        json={"agentRole": "research", "allowedSecretNames": ["WEB_SEARCH_KEY"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agentRole"] == "research"
    assert "policyId" in data


async def test_upsert_agent_secret_policy_normalizes_role_alias(client, convex_mock):
    mutations_called = []

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        mutations_called.append((payload.get("path"), payload.get("args", {})))
        return httpx.Response(200, json={"value": "policy-id-new"})

    convex_mock.post("/api/query").mock(side_effect=_project_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    resp = await client.post(
        f"/api/v1/projects/{PROJECT_SLUG}/settings/agent-secret-policies",
        json={"agentRole": "developer", "allowedSecretNames": ["WEB_SEARCH_KEY"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agentRole"] == "coding"
    _, args = next((p, a) for p, a in mutations_called if p == "agentSecretPolicies:upsert")
    assert args["agentRole"] == "coding"


async def test_upsert_agent_secret_policy_rejects_unknown_role(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_project_query)

    resp = await client.post(
        f"/api/v1/projects/{PROJECT_SLUG}/settings/agent-secret-policies",
        json={"agentRole": "writer", "allowedSecretNames": ["WEB_SEARCH_KEY"]},
    )
    assert resp.status_code == 422
    assert "Agent secret policy role must be one of" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Admin endpoints — delete
# ---------------------------------------------------------------------------


async def test_delete_secret(client, convex_mock):
    mutations_called = []

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        mutations_called.append((payload.get("path"), payload.get("args", {})))
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_project_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    resp = await client.delete(
        f"/api/v1/projects/{PROJECT_SLUG}/settings/secrets/FRED_API_KEY"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True
    assert data["keyName"] == "FRED_API_KEY"

    paths = [p for p, _ in mutations_called]
    assert "projectSecrets:deleteByKey" in paths

    _, args = next((p, a) for p, a in mutations_called if p == "projectSecrets:deleteByKey")
    assert args["keyName"] == "FRED_API_KEY"


async def test_delete_agent_secret_policy(client, convex_mock):
    mutations_called = []

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        mutations_called.append((payload.get("path"), payload.get("args", {})))
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_project_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    resp = await client.delete(
        f"/api/v1/projects/{PROJECT_SLUG}/settings/agent-secret-policies/data"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True
    assert data["agentRole"] == "data"

    paths = [p for p, _ in mutations_called]
    assert "agentSecretPolicies:deleteByRole" in paths


async def test_delete_agent_secret_policy_normalizes_role_alias(client, convex_mock):
    mutations_called = []

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        mutations_called.append((payload.get("path"), payload.get("args", {})))
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_project_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    resp = await client.delete(
        f"/api/v1/projects/{PROJECT_SLUG}/settings/agent-secret-policies/auditor"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agentRole"] == "health"

    _, args = next((p, a) for p, a in mutations_called if p == "agentSecretPolicies:deleteByRole")
    assert args["agentRole"] == "health"


async def test_delete_agent_secret_policy_rejects_unknown_role(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_project_query)

    resp = await client.delete(
        f"/api/v1/projects/{PROJECT_SLUG}/settings/agent-secret-policies/writer"
    )
    assert resp.status_code == 422
    assert "Agent secret policy role must be one of" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Runtime resolver
# ---------------------------------------------------------------------------


async def test_resolve_secrets_for_role_returns_allowed_only(client, convex_mock):
    """The resolver should return only secrets in the role's allowlist."""
    convex_mock.post("/api/query").mock(side_effect=_resolver_query)

    resp = await client.get(
        f"/api/v1/projects/{PROJECT_SLUG}/secrets/resolve",
        params={"agentRole": "data"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agentRole"] == "data"

    secrets = data["secrets"]
    # FRED_API_KEY and CENSUS_API_KEY are in policy — should be returned decrypted
    assert secrets["FRED_API_KEY"] == "fred-abc123"
    assert secrets["CENSUS_API_KEY"] == "census-xyz789"
    # INTERNAL_DB_PASS is NOT in the data role policy — must not appear
    assert "INTERNAL_DB_PASS" not in secrets


async def test_resolve_secrets_for_role_normalizes_role_alias(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_resolver_query)

    resp = await client.get(
        f"/api/v1/projects/{PROJECT_SLUG}/secrets/resolve",
        params={"agentRole": "analyst"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agentRole"] == "data"
    assert data["secrets"]["FRED_API_KEY"] == "fred-abc123"


async def test_resolve_secrets_no_policy_returns_empty(client, convex_mock):
    """Unknown roles are rejected instead of being treated as arbitrary strings."""
    convex_mock.post("/api/query").mock(side_effect=_resolver_query)

    resp = await client.get(
        f"/api/v1/projects/{PROJECT_SLUG}/secrets/resolve",
        params={"agentRole": "unknown-role"},
    )
    assert resp.status_code == 422
    assert "Secrets resolve agentRole must be one of" in resp.json()["detail"]


async def test_resolve_secrets_service_unit(convex_mock):
    """Unit test: resolve_secrets_for_role respects the allowlist."""
    os.environ["RAIL_SECRET_FERNET_KEY"] = TEST_FERNET_KEY

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        path = payload.get("path")
        if path == "agentSecretPolicies:getByRole":
            return httpx.Response(200, json={"value": POLICY_DATA_ROLE})
        if path == "projectSecrets:listByProject":
            return httpx.Response(200, json={"value": [FRED_SECRET, CENSUS_SECRET, OTHER_SECRET]})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    from app.services.secret_service import resolve_secrets_for_role

    result = await resolve_secrets_for_role(PROJECT_ID, "data")
    assert result["FRED_API_KEY"] == "fred-abc123"
    assert result["CENSUS_API_KEY"] == "census-xyz789"
    assert "INTERNAL_DB_PASS" not in result


async def test_resolve_secrets_service_no_policy(convex_mock):
    """Unit test: returns empty dict when no policy exists for the role."""
    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "agentSecretPolicies:getByRole":
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    from app.services.secret_service import resolve_secrets_for_role

    result = await resolve_secrets_for_role(PROJECT_ID, "nonexistent")
    assert result == {}


async def test_resolve_secrets_service_empty_allowlist(convex_mock):
    """Unit test: returns empty dict when policy has an empty allowlist."""
    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "agentSecretPolicies:getByRole":
            return httpx.Response(200, json={"value": {
                "_id": "policy-id",
                "projectId": PROJECT_ID,
                "agentRole": "health",
                "allowedSecretNames": [],
            }})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    from app.services.secret_service import resolve_secrets_for_role

    result = await resolve_secrets_for_role(PROJECT_ID, "health")
    assert result == {}
