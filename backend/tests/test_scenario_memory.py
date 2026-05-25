"""
Scenario memory isolation tests.
These tests hit the actual /api/v1/query route and verify that the
is_ephemeral flag controls whether add_turn() is invoked in production code.
External dependencies (DB, Ollama, RAG, SQL agent) are mocked so the test
exercises the routing/branching logic without needing a live stack.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.routes.auth import create_access_token


def _auth_headers():
    token = create_access_token("test-tenant-abc")
    return {"Authorization": f"Bearer {token}"}


def _fake_session():
    session = MagicMock()
    session.id = uuid.uuid4()
    session.messages = []
    session.context_summary = None
    session.turn_count = 0
    session.active_dataset_ids = []
    session.active_document_ids = []
    return session


def _fake_synthesis_result():
    return {
        "recommendation": {
            "action": "Increase premium by 10%",
            "confidence": "high",
            "confidence_rationale": "Strong signal",
            "document_evidence": [],
            "sql_evidence": [],
            "conflicts": [],
            "reasoning_steps": ["Analyzed claims data"],
            "uncertainty_sources": [],
        },
        "raw_model_output": '{"action":"Increase premium by 10%"}',
        "retrieved_chunks": [],
        "sql_queries": [],
        "prompt_version": "v1.0",
        "llm_model": "llama3.1:8b",
        "embed_model": "nomic-embed-text",
    }


@pytest.mark.asyncio
async def test_ephemeral_query_does_NOT_call_add_turn():
    """
    When is_ephemeral=True, the route must skip add_turn() entirely.
    This is what guarantees scenario assumptions never contaminate
    the conversational memory timeline.
    """
    fake_session = _fake_session()

    with patch("app.api.routes.query.get_or_create_session", new=AsyncMock(return_value=fake_session)), \
         patch("app.api.routes.query.get_session_context", new=AsyncMock(return_value="")), \
         patch("app.api.routes.query.synthesize", new=AsyncMock(return_value=_fake_synthesis_result())), \
         patch("app.api.routes.query.add_turn", new=AsyncMock()) as mock_add_turn, \
         patch("app.db.session.AsyncSessionLocal") as mock_session_local:

        # Make the dependency injected db a no-op committer
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/query",
                json={
                    "question": "What happens if claims rise 25%?",
                    "scenario_assumptions": {"claims_increase": 0.25},
                    "scenario_label": "Stress test",
                    "is_ephemeral": True,
                },
                headers=_auth_headers(),
            )

    # Gate on success first - otherwise call_count == 0 could be a false pass
    # caused by 401/422/500 short-circuiting the route before the ephemeral branch.
    assert resp.status_code == 200, f"Route returned {resp.status_code}: {resp.text}"

    # The critical assertion: add_turn was NEVER called for an ephemeral query
    assert mock_add_turn.call_count == 0, \
        "add_turn() must not be called when is_ephemeral=True - scenario would contaminate memory"


@pytest.mark.asyncio
async def test_normal_query_DOES_call_add_turn():
    """
    Sanity check the inverse: a normal (non-ephemeral) query persists to memory.
    Without this, a bug could silently break conversational continuity for real queries.
    """
    fake_session = _fake_session()

    with patch("app.api.routes.query.get_or_create_session", new=AsyncMock(return_value=fake_session)), \
         patch("app.api.routes.query.get_session_context", new=AsyncMock(return_value="")), \
         patch("app.api.routes.query.synthesize", new=AsyncMock(return_value=_fake_synthesis_result())), \
         patch("app.api.routes.query.add_turn", new=AsyncMock()) as mock_add_turn:

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/query",
                json={"question": "What is the average premium for under-25 drivers?"},
                headers=_auth_headers(),
            )

    # Gate on success first - call_count == 1 alone would not prove the
    # ephemeral branch was reached if the route had failed earlier.
    assert resp.status_code == 200, f"Route returned {resp.status_code}: {resp.text}"

    assert mock_add_turn.call_count == 1, \
        "add_turn() must be called exactly once for a normal conversational turn"


@pytest.mark.asyncio
async def test_ephemeral_does_not_update_active_dataset_ids():
    """
    Ephemeral queries also must not change the session's active datasets,
    because that would persist scenario context into future real queries.
    """
    fake_session = _fake_session()

    with patch("app.api.routes.query.get_or_create_session", new=AsyncMock(return_value=fake_session)), \
         patch("app.api.routes.query.get_session_context", new=AsyncMock(return_value="")), \
         patch("app.api.routes.query.synthesize", new=AsyncMock(return_value=_fake_synthesis_result())), \
         patch("app.api.routes.query.add_turn", new=AsyncMock()):

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/query",
                json={
                    "question": "Scenario q",
                    "dataset_ids": ["ds-scenario-only"],
                    "is_ephemeral": True,
                },
                headers=_auth_headers(),
            )

    # Gate on success - an early failure would leave active_dataset_ids
    # untouched for the wrong reason (route never executed).
    assert resp.status_code == 200, f"Route returned {resp.status_code}: {resp.text}"

    # Active datasets must NOT have been mutated by an ephemeral call
    assert fake_session.active_dataset_ids == [], \
        "Ephemeral queries must not mutate session.active_dataset_ids"
