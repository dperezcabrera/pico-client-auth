"""Tests for JWKSClient — TTL cache, key rotation, and error handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pico_ioc import component

from pico_client_auth.config import AuthClientSettings
from pico_client_auth.jwks_client import JWKSClient


def _settings(**overrides):
    defaults = dict(
        enabled=True,
        issuer="https://auth.example.com",
        audience="my-api",
        jwks_ttl_seconds=300,
        jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
    )
    defaults.update(overrides)
    return AuthClientSettings(**defaults)


def _mock_http_client(jwks_data):
    """Create a mock httpx.AsyncClient that returns jwks_data."""
    mock_response = MagicMock()
    mock_response.json.return_value = jwks_data
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    ctx = AsyncMock()
    ctx.__aenter__.return_value = mock_client
    ctx.__aexit__.return_value = False
    return ctx, mock_client


@pytest.fixture
def jwks_data(jwk_dict):
    return {"keys": [jwk_dict]}


class TestGetKey:
    @pytest.mark.asyncio
    async def test_fetches_key_on_first_call(self, jwks_data, jwk_dict):
        client = JWKSClient(settings=_settings())
        ctx, mock_http = _mock_http_client(jwks_data)

        with patch("pico_client_auth.jwks_client.httpx.AsyncClient", return_value=ctx):
            key = await client.get_key("test-key-1")
            assert key["kid"] == "test-key-1"
            assert key["kty"] == "RSA"

    @pytest.mark.asyncio
    async def test_cache_hit_avoids_refetch(self, jwks_data):
        client = JWKSClient(settings=_settings())
        ctx, mock_http = _mock_http_client(jwks_data)

        with patch("pico_client_auth.jwks_client.httpx.AsyncClient", return_value=ctx):
            await client.get_key("test-key-1")
            await client.get_key("test-key-1")

            # Only one HTTP call (cache hit on second)
            assert mock_http.get.call_count == 1

    @pytest.mark.asyncio
    async def test_force_refresh_on_unknown_kid(self, jwks_data):
        client = JWKSClient(settings=_settings())
        ctx, mock_http = _mock_http_client(jwks_data)

        with patch("pico_client_auth.jwks_client.httpx.AsyncClient", return_value=ctx):
            await client.get_key("test-key-1")
            assert mock_http.get.call_count == 1

            with pytest.raises(KeyError, match="unknown-kid"):
                await client.get_key("unknown-kid")

            # Two fetches: initial + force refresh
            assert mock_http.get.call_count == 2

    @pytest.mark.asyncio
    async def test_ttl_expiration_triggers_refetch(self, jwks_data):
        client = JWKSClient(settings=_settings(jwks_ttl_seconds=0))
        ctx, mock_http = _mock_http_client(jwks_data)

        with patch("pico_client_auth.jwks_client.httpx.AsyncClient", return_value=ctx):
            await client.get_key("test-key-1")
            await client.get_key("test-key-1")

            # TTL=0 means always expired, so two HTTP calls
            assert mock_http.get.call_count == 2


class TestEndpointDefault:
    def test_default_endpoint_from_issuer(self):
        client = JWKSClient(settings=_settings(jwks_endpoint=""))
        assert client._endpoint == "https://auth.example.com/api/v1/auth/jwks"

    def test_custom_endpoint(self):
        client = JWKSClient(settings=_settings(jwks_endpoint="https://custom.example.com/.well-known/jwks.json"))
        assert client._endpoint == "https://custom.example.com/.well-known/jwks.json"

    def test_strips_trailing_slash_from_issuer(self):
        client = JWKSClient(settings=_settings(issuer="https://auth.example.com/", jwks_endpoint=""))
        assert client._endpoint == "https://auth.example.com/api/v1/auth/jwks"


class TestReplaceableKeySource:
    """The README documents replacing the key source without subclassing."""

    def test_jwks_client_is_exported_as_the_container_key(self):
        import pico_client_auth

        assert pico_client_auth.JWKSClient is JWKSClient
        assert "JWKSClient" in pico_client_auth.__all__

    def test_plain_component_registered_under_the_key_wins_resolution(self):
        import sys

        from pico_ioc import DictSource, configuration, init

        cfg = configuration(DictSource({"auth_client": {"enabled": True, "issuer": "https://t", "audience": "t"}}))
        container = init(modules=["pico_client_auth", sys.modules[__name__]], config=cfg)

        resolved = container.get(JWKSClient)
        assert isinstance(resolved, LocalKeys), "the @component(name=JWKSClient) override must win"
        assert not issubclass(LocalKeys, JWKSClient), "and it must win without subclassing"


@component(name=JWKSClient, primary=True)
class LocalKeys:
    """A key source that is deliberately NOT a JWKSClient subclass."""

    async def get_key(self, kid: str) -> dict:
        return {"kid": kid, "kty": "oct"}
