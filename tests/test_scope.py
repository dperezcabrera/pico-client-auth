"""Tests for the agentic-RBAC additions: scope matching, AgentContext,
@requires_scope, and dual-token (X-Agent-Authorization) middleware.

The tests are split into three layers:
  - Pure scope matching (no I/O).
  - AgentContext lifecycle (set/get/clear, ContextVar isolation).
  - End-to-end middleware: validates the full request flow with both
    `Authorization` (service token) and `X-Agent-Authorization` (agent
    token) using the same `make_token` fixture as the existing e2e
    tests — only the header changes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from pico_client_auth.agent_context import AgentClaims, AgentContext
from pico_client_auth.config import AuthClientSettings
from pico_client_auth.configurer import AuthFastapiConfigurer
from pico_client_auth.decorators import allow_anonymous, requires_role
from pico_client_auth.jwks_client import JWKSClient
from pico_client_auth.revocation_cache import RevocationCache
from pico_client_auth.role_resolver import DefaultRoleResolver
from pico_client_auth.scope import (
    any_scope_matches,
    requires_scope,
    scope_matches,
)
from pico_client_auth.security_context import SecurityContext
from pico_client_auth.token_validator import TokenValidator


def _no_revocations() -> RevocationCache:
    """Disabled revocation cache (no endpoint → is_revoked() always False)."""
    return RevocationCache(AuthClientSettings())


# ============================================================
# Pure scope matching
# ============================================================


class TestScopeMatches:
    def test_exact_match(self):
        assert scope_matches("treasury:write:budget", "treasury:write:budget")

    def test_no_match_when_different(self):
        assert not scope_matches("treasury:write:budget", "treasury:read:budget")

    def test_global_wildcard_matches_anything(self):
        assert scope_matches("*", "anything:goes:here")
        assert scope_matches("*", "")

    def test_trailing_wildcard_matches_descendants(self):
        assert scope_matches("treasury:*", "treasury:read")
        assert scope_matches("treasury:*", "treasury:write:budget:opex")

    def test_trailing_wildcard_also_matches_exact_prefix(self):
        # "treasury:*" should match "treasury" (the bare prefix)
        # because conceptually the agent can do "anything under
        # treasury", including treasury itself.
        assert scope_matches("treasury:*", "treasury")

    def test_trailing_wildcard_does_not_match_unrelated(self):
        assert not scope_matches("treasury:*", "wallet:write")

    def test_mid_wildcard_not_supported(self):
        # "treasury:*:budget" is NOT supported — only trailing.
        assert not scope_matches("treasury:*:budget", "treasury:write:budget")

    def test_any_scope_matches_picks_first_hit(self):
        granted = ("treasury:read", "wallet:execute_payment:opex")
        required = frozenset({"treasury:write", "wallet:execute_payment:opex"})
        assert any_scope_matches(granted, required)

    def test_any_scope_matches_returns_false_when_no_overlap(self):
        granted = ("foo:read",)
        required = frozenset({"bar:write"})
        assert not any_scope_matches(granted, required)


# ============================================================
# AgentContext lifecycle
# ============================================================


class TestAgentContext:
    def setup_method(self):
        AgentContext.clear()

    def teardown_method(self):
        AgentContext.clear()

    def test_initial_state_is_empty(self):
        assert AgentContext.get() is None
        assert AgentContext.get_scopes() == ()
        assert not AgentContext.is_present()
        assert not AgentContext.has_scope("any")

    def test_set_and_read(self):
        agent = AgentClaims(
            sub="agent-1", scopes=("a:b", "c:*"),
            user_id="user-1",
        )
        AgentContext.set(agent)
        assert AgentContext.is_present()
        assert AgentContext.get_scopes() == ("a:b", "c:*")
        assert AgentContext.has_scope("a:b")
        assert not AgentContext.has_scope("a:c")

    def test_clear_resets(self):
        AgentContext.set(AgentClaims(sub="x"))
        AgentContext.clear()
        assert AgentContext.get() is None

    def test_from_claims_dict_extracts_fields(self):
        raw = {
            "sub": "agent-42",
            "task_type": "purchase",
            "task_id": "t-1",
            "user_id": "user:cfo",
            "session_id": "sess-x",
            "conversation_id": "conv-y",
            "org_id": "io.acme",
            "role": "purchaser",
            "spend_limit": "1000.00",
            "scopes": ["wallet:execute_payment:opex"],
            "parent_chain": ["io.acme.head-agent"],
            "iss": "irrelevant",
            "aud": "irrelevant",
        }
        agent = AgentClaims.from_claims_dict(raw)
        assert agent.sub == "agent-42"
        assert agent.task_type == "purchase"
        assert agent.user_id == "user:cfo"
        assert agent.scopes == ("wallet:execute_payment:opex",)
        assert agent.parent_chain == ("io.acme.head-agent",)
        assert agent.spend_limit == "1000.00"
        # raw_claims preserved verbatim (allows reading custom fields).
        assert agent.raw_claims["iss"] == "irrelevant"


# ============================================================
# Middleware end-to-end
# ============================================================


def _build_settings():
    return AuthClientSettings(
        enabled=True,
        issuer="https://auth.example.com",
        audience="my-api",
        jwks_ttl_seconds=300,
        jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
        accepted_algorithms=("RS256",),
    )


def _build_app(settings, jwk_dict):
    app = FastAPI()
    mock_jwks = AsyncMock(spec=JWKSClient)
    mock_jwks.get_key = AsyncMock(return_value=jwk_dict)
    validator = TokenValidator(settings=settings, jwks_client=mock_jwks, revocation_cache=_no_revocations())
    resolver = DefaultRoleResolver()
    configurer = AuthFastapiConfigurer(
        settings=settings, token_validator=validator, role_resolver=resolver,
    )
    configurer.configure_app(app)

    @app.get("/scoped")
    @requires_role("admin")
    @requires_scope("treasury:write:budget:opex")
    async def scoped(request: Request):
        # Echo back what the middleware materialised.
        agent = AgentContext.get()
        return {
            "service_sub": SecurityContext.require().sub,
            "agent_sub": agent.sub if agent else None,
            "scopes": list(agent.scopes) if agent else [],
        }

    @app.get("/wildcard-scope")
    @requires_role("admin")
    @requires_scope("treasury:*")
    async def wildcard_scope():
        return {"ok": True}

    @app.get("/role-only")
    @requires_role("admin")
    async def role_only():
        # Endpoint with @requires_role but NO @requires_scope:
        # the agent header is OPTIONAL. If present + valid the
        # AgentContext is populated; if absent the endpoint still works.
        agent = AgentContext.get()
        return {"agent_present": agent is not None}

    @app.get("/anon")
    @allow_anonymous
    async def anon():
        return {"ok": True}

    return app


@pytest.fixture
def app(jwk_dict):
    return _build_app(_build_settings(), jwk_dict)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ─── 401 paths ───────────────────────────────────────────────


class TestScopedEndpointMissingAgent:
    @pytest.mark.asyncio
    async def test_no_agent_header_401(self, client, make_token):
        # Service token only → @requires_scope still demands agent token.
        token = make_token(role="admin")
        resp = await client.get(
            "/scoped",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        assert "agent" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_agent_token_401(self, client, make_token):
        svc = make_token(role="admin")
        resp = await client.get(
            "/scoped",
            headers={
                "Authorization": f"Bearer {svc}",
                "X-Agent-Authorization": "Bearer not-a-real-jwt",
            },
        )
        assert resp.status_code == 401
        assert "agent" in resp.json()["detail"].lower()


# ─── 403 paths ───────────────────────────────────────────────


class TestScopedEndpointWrongScope:
    @pytest.mark.asyncio
    async def test_agent_with_wrong_scope_403(self, client, make_token):
        svc = make_token(role="admin")
        agent = make_token(
            sub="agent-1",
            extra_claims={"scopes": ["wallet:read:balance"]},
        )
        resp = await client.get(
            "/scoped",
            headers={
                "Authorization": f"Bearer {svc}",
                "X-Agent-Authorization": f"Bearer {agent}",
            },
        )
        assert resp.status_code == 403
        assert "scope" in resp.json()["detail"].lower()


# ─── 200 happy paths ─────────────────────────────────────────


class TestScopedEndpointHappy:
    @pytest.mark.asyncio
    async def test_exact_scope_match(self, client, make_token):
        svc = make_token(role="admin")
        agent = make_token(
            sub="agent-1",
            extra_claims={"scopes": ["treasury:write:budget:opex"]},
        )
        resp = await client.get(
            "/scoped",
            headers={
                "Authorization": f"Bearer {svc}",
                "X-Agent-Authorization": f"Bearer {agent}",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["agent_sub"] == "agent-1"
        assert body["scopes"] == ["treasury:write:budget:opex"]

    @pytest.mark.asyncio
    async def test_wildcard_scope_match(self, client, make_token):
        svc = make_token(role="admin")
        # Agent has "treasury:*" → endpoint requires "treasury:*" too.
        # Match by both being identical.
        agent = make_token(extra_claims={"scopes": ["treasury:*"]})
        resp = await client.get(
            "/wildcard-scope",
            headers={
                "Authorization": f"Bearer {svc}",
                "X-Agent-Authorization": f"Bearer {agent}",
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_specific_scope_satisfies_wildcard_endpoint(
        self, client, make_token,
    ):
        # Endpoint asks for "treasury:*" — agent has the more specific
        # "treasury:write:budget:opex". The endpoint required scope is
        # "treasury:*" and the agent's "treasury:write:budget:opex" must
        # match it. Since `scope_matches(granted, required)` interprets
        # the granted scope's wildcard, the call is
        # `scope_matches("treasury:write:budget:opex", "treasury:*")`
        # which is False (specific cannot satisfy wildcard).
        # That's correct: the endpoint's scope is the *required* shape
        # and the agent must declare a matching scope. The agent here
        # would need to declare "treasury:*" or "*" to access this
        # endpoint.
        svc = make_token(role="admin")
        agent = make_token(
            extra_claims={"scopes": ["treasury:write:budget:opex"]},
        )
        resp = await client.get(
            "/wildcard-scope",
            headers={
                "Authorization": f"Bearer {svc}",
                "X-Agent-Authorization": f"Bearer {agent}",
            },
        )
        # By matcher semantics, the agent's specific scope does NOT
        # satisfy a wildcard-shaped requirement — the agent would have
        # to declare the wildcard explicitly. This is intentional;
        # otherwise any specific scope would silently grant any wildcard.
        assert resp.status_code == 403


# ─── Endpoints WITHOUT @requires_scope ───────────────────────


class TestRoleOnlyEndpoint:
    @pytest.mark.asyncio
    async def test_no_agent_header_still_works(self, client, make_token):
        svc = make_token(role="admin")
        resp = await client.get(
            "/role-only",
            headers={"Authorization": f"Bearer {svc}"},
        )
        assert resp.status_code == 200
        assert resp.json()["agent_present"] is False

    @pytest.mark.asyncio
    async def test_with_agent_header_populates_context(
        self, client, make_token,
    ):
        svc = make_token(role="admin")
        agent = make_token(sub="agent-1", extra_claims={"scopes": ["x:y"]})
        resp = await client.get(
            "/role-only",
            headers={
                "Authorization": f"Bearer {svc}",
                "X-Agent-Authorization": f"Bearer {agent}",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["agent_present"] is True


# ─── Anonymous endpoint ignores both headers ─────────────────


class TestAnonymousEndpoint:
    @pytest.mark.asyncio
    async def test_anon_with_invalid_agent_header_still_200(self, client):
        resp = await client.get(
            "/anon",
            headers={"X-Agent-Authorization": "Bearer garbage"},
        )
        assert resp.status_code == 200


# ─── Context cleanup between requests ────────────────────────


class TestContextCleanup:
    @pytest.mark.asyncio
    async def test_agent_context_does_not_leak_between_requests(
        self, client, make_token,
    ):
        # Request 1: with agent token.
        svc = make_token(role="admin")
        agent = make_token(extra_claims={"scopes": ["treasury:write:budget:opex"]})
        r1 = await client.get(
            "/scoped",
            headers={
                "Authorization": f"Bearer {svc}",
                "X-Agent-Authorization": f"Bearer {agent}",
            },
        )
        assert r1.status_code == 200

        # Request 2: WITHOUT agent token, on /role-only — must see no agent.
        r2 = await client.get(
            "/role-only",
            headers={"Authorization": f"Bearer {svc}"},
        )
        assert r2.json()["agent_present"] is False
