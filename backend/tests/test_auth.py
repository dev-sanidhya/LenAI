"""
Auth endpoint tests.
Verifies JWT issuance, signature validation, claim extraction,
and that protected routes correctly reject missing/invalid tokens.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from jose import jwt
from app.main import app
from app.core.config import get_settings
from app.api.routes.auth import create_access_token, ALGORITHM


# --- Token creation and signature ---

def test_create_access_token_contains_tenant_id():
    token = create_access_token("tenant-123")
    settings = get_settings()
    decoded = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
    assert decoded["tenant_id"] == "tenant-123"
    assert decoded["sub"] == "tenant-123"
    assert "iat" in decoded
    assert "exp" in decoded


def test_token_signed_with_secret_rejects_wrong_secret():
    token = create_access_token("tenant-x")
    with pytest.raises(Exception):
        jwt.decode(token, "wrong-secret-key", algorithms=[ALGORITHM])


# --- /auth/token endpoint behaviour ---

@pytest.mark.asyncio
async def test_token_endpoint_issues_valid_jwt_for_correct_key():
    """The endpoint must return 200 and a decodable JWT when the API key is correct."""
    settings = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/token", json={"api_key": settings.api_key})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    # The returned token must decode and contain a tenant_id claim
    decoded = jwt.decode(body["access_token"], settings.app_secret_key, algorithms=[ALGORITHM])
    assert "tenant_id" in decoded
    assert len(decoded["tenant_id"]) == 16  # sha256 prefix derived in handler


@pytest.mark.asyncio
async def test_token_endpoint_rejects_wrong_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/token", json={"api_key": "definitely-not-the-key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_endpoint_rejects_missing_body():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/token", json={})
    assert resp.status_code == 422  # pydantic validation error


# --- Protected routes ---

@pytest.mark.asyncio
async def test_protected_route_rejects_missing_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/ingest/datasets")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_rejects_invalid_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ingest/datasets",
            headers={"Authorization": "Bearer not-a-real-jwt"}
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_rejects_token_with_wrong_signature():
    """A JWT signed with a different secret must be rejected."""
    forged = jwt.encode({"tenant_id": "attacker", "sub": "attacker"}, "wrong-secret", algorithm=ALGORITHM)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ingest/datasets",
            headers={"Authorization": f"Bearer {forged}"}
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_is_public():
    """Health check must not require auth - used by Docker healthcheck."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
