"""End-to-end middleware tests using a real FastAPI test app."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse
from starlette.routing import Match

from pico_client_auth.config import AuthClientSettings
from pico_client_auth.configurer import AuthFastapiConfigurer, _find_endpoint
from pico_client_auth.decorators import allow_anonymous, requires_role
from pico_client_auth.errors import AuthConfigurationError
from pico_client_auth.jwks_client import JWKSClient
from pico_client_auth.role_resolver import DefaultRoleResolver
from pico_client_auth.security_context import SecurityContext
from pico_client_auth.token_validator import TokenValidator


def _build_settings(**overrides):
    defaults = dict(
        enabled=True,
        issuer="https://auth.example.com",
        audience="my-api",
        jwks_ttl_seconds=300,
        jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
    )
    defaults.update(overrides)
    return AuthClientSettings(**defaults)


def _build_app(settings, jwk_dict):
    """Build a FastAPI app with auth middleware and test routes."""
    app = FastAPI()

    mock_jwks = AsyncMock(spec=JWKSClient)
    mock_jwks.get_key = AsyncMock(return_value=jwk_dict)

    validator = TokenValidator(settings=settings, jwks_client=mock_jwks)
    resolver = DefaultRoleResolver()
    configurer = AuthFastapiConfigurer(settings=settings, token_validator=validator, role_resolver=resolver)
    configurer.configure_app(app)

    @app.get("/protected")
    async def protected(request: Request):
        claims = SecurityContext.get()
        return {"sub": claims.sub, "email": claims.email}

    @app.get("/public")
    @allow_anonymous
    async def public():
        return {"message": "hello"}

    @app.get("/admin-only")
    @requires_role("admin")
    async def admin_only():
        claims = SecurityContext.require()
        return {"sub": claims.sub, "role": "admin"}

    @app.get("/editor-or-admin")
    @requires_role("editor", "admin")
    async def editor_or_admin():
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


class TestNoToken:
    @pytest.mark.asyncio
    async def test_401_without_token(self, client):
        resp = await client.get("/protected")
        assert resp.status_code == 401
        assert "Authorization" in resp.json()["detail"]


class TestValidToken:
    @pytest.mark.asyncio
    async def test_200_with_valid_token(self, client, make_token):
        token = make_token()
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sub"] == "user-123"
        assert data["email"] == "user@example.com"


class TestAllowAnonymous:
    @pytest.mark.asyncio
    async def test_public_without_token(self, client):
        resp = await client.get("/public")
        assert resp.status_code == 200
        assert resp.json()["message"] == "hello"

    @pytest.mark.asyncio
    async def test_public_with_token_also_works(self, client, make_token):
        token = make_token()
        resp = await client.get("/public", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestRequiresRole:
    @pytest.mark.asyncio
    async def test_403_without_required_role(self, client, make_token):
        token = make_token(role="viewer")
        resp = await client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_200_with_required_role(self, client, make_token):
        token = make_token(role="admin")
        resp = await client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["sub"] == "user-123"

    @pytest.mark.asyncio
    async def test_200_with_one_of_multiple_roles(self, client, make_token):
        token = make_token(role="editor")
        resp = await client.get("/editor-or-admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestSecurityContextInHandler:
    @pytest.mark.asyncio
    async def test_context_populated(self, client, make_token):
        token = make_token(sub="ctx-user", email="ctx@test.com")
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["sub"] == "ctx-user"


class TestExpiredToken:
    @pytest.mark.asyncio
    async def test_expired_returns_401(self, client, make_token):
        from datetime import timedelta

        token = make_token(expires_delta=timedelta(seconds=-60))
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()


class TestFailFastConfiguration:
    def test_missing_issuer_raises(self, jwk_dict):
        settings = _build_settings(issuer="")
        mock_jwks = AsyncMock(spec=JWKSClient)
        validator = TokenValidator(settings=settings, jwks_client=mock_jwks)
        resolver = DefaultRoleResolver()
        with pytest.raises(AuthConfigurationError, match="issuer"):
            AuthFastapiConfigurer(settings=settings, token_validator=validator, role_resolver=resolver)

    def test_missing_audience_raises(self, jwk_dict):
        settings = _build_settings(audience="")
        mock_jwks = AsyncMock(spec=JWKSClient)
        validator = TokenValidator(settings=settings, jwks_client=mock_jwks)
        resolver = DefaultRoleResolver()
        with pytest.raises(AuthConfigurationError, match="audience"):
            AuthFastapiConfigurer(settings=settings, token_validator=validator, role_resolver=resolver)

    def test_disabled_skips_validation(self, jwk_dict):
        settings = _build_settings(enabled=False, issuer="", audience="")
        mock_jwks = AsyncMock(spec=JWKSClient)
        validator = TokenValidator(settings=settings, jwks_client=mock_jwks)
        resolver = DefaultRoleResolver()
        # Should not raise
        configurer = AuthFastapiConfigurer(settings=settings, token_validator=validator, role_resolver=resolver)
        app = FastAPI()
        configurer.configure_app(app)  # Should log info, not add middleware
