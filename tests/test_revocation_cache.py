"""Tests for RevocationCache — TTL polling, fail-open policy, and the disabled default."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pico_client_auth.config import AuthClientSettings
from pico_client_auth.revocation_cache import RevocationCache

ENDPOINT = "https://auth.example.com/api/v1/auth/revoked-jtis"


def _settings(**overrides):
    defaults = dict(
        enabled=True,
        issuer="https://auth.example.com",
        audience="my-api",
        revocation_endpoint=ENDPOINT,
        revocation_ttl_seconds=15,
    )
    defaults.update(overrides)
    return AuthClientSettings(**defaults)


def _mock_http_client(payload=None, error=None):
    mock_response = MagicMock()
    mock_response.json.return_value = payload
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    if error is not None:
        mock_client.get.side_effect = error
    else:
        mock_client.get.return_value = mock_response

    ctx = AsyncMock()
    ctx.__aenter__.return_value = mock_client
    ctx.__aexit__.return_value = False
    return ctx, mock_client


def _patch_httpx(ctx):
    return patch("pico_client_auth.revocation_cache.httpx.AsyncClient", return_value=ctx)


class TestDisabled:
    def test_disabled_without_endpoint(self):
        cache = RevocationCache(_settings(revocation_endpoint=""))
        assert cache.enabled is False

    @pytest.mark.asyncio
    async def test_disabled_cache_never_fetches(self):
        cache = RevocationCache(_settings(revocation_endpoint=""))
        ctx, mock_http = _mock_http_client({"items": [{"jti": "j1"}]})
        with _patch_httpx(ctx):
            assert await cache.is_revoked("j1") is False
        mock_http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_force_refresh_is_noop(self):
        cache = RevocationCache(_settings(revocation_endpoint=""))
        ctx, mock_http = _mock_http_client({"items": []})
        with _patch_httpx(ctx):
            await cache.force_refresh()
        mock_http.get.assert_not_called()


class TestFetch:
    @pytest.mark.asyncio
    async def test_revoked_jti_is_rejected(self):
        cache = RevocationCache(_settings())
        ctx, _ = _mock_http_client({"items": [{"jti": "j1"}, {"jti": "j2"}]})
        with _patch_httpx(ctx):
            assert await cache.is_revoked("j1") is True
            assert await cache.is_revoked("j2") is True
            assert await cache.is_revoked("j3") is False

    @pytest.mark.asyncio
    async def test_entries_without_jti_are_ignored(self):
        cache = RevocationCache(_settings())
        ctx, _ = _mock_http_client({"items": [{"jti": ""}, {"reason": "x"}, {"jti": "ok"}]})
        with _patch_httpx(ctx):
            assert await cache.is_revoked("ok") is True
        assert cache._revoked == {"ok"}

    @pytest.mark.asyncio
    async def test_null_items_means_empty_denylist(self):
        cache = RevocationCache(_settings())
        ctx, _ = _mock_http_client({"items": None})
        with _patch_httpx(ctx):
            assert await cache.is_revoked("j1") is False

    @pytest.mark.asyncio
    async def test_token_without_jti_is_never_revoked(self):
        cache = RevocationCache(_settings())
        ctx, mock_http = _mock_http_client({"items": [{"jti": "j1"}]})
        with _patch_httpx(ctx):
            assert await cache.is_revoked("") is False
        mock_http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_bearer_header_sent_when_configured(self):
        cache = RevocationCache(_settings(revocation_bearer="tok123"))
        ctx, mock_http = _mock_http_client({"items": []})
        with _patch_httpx(ctx):
            await cache.is_revoked("j1")
        mock_http.get.assert_called_once_with(ENDPOINT, headers={"Authorization": "Bearer tok123"})

    @pytest.mark.asyncio
    async def test_no_bearer_header_by_default(self):
        cache = RevocationCache(_settings())
        ctx, mock_http = _mock_http_client({"items": []})
        with _patch_httpx(ctx):
            await cache.is_revoked("j1")
        mock_http.get.assert_called_once_with(ENDPOINT, headers={})


class TestTtl:
    @pytest.mark.asyncio
    async def test_within_ttl_uses_cached_denylist(self):
        cache = RevocationCache(_settings())
        ctx, mock_http = _mock_http_client({"items": [{"jti": "j1"}]})
        with _patch_httpx(ctx):
            await cache.is_revoked("j1")
            await cache.is_revoked("j2")
        assert mock_http.get.call_count == 1

    @pytest.mark.asyncio
    async def test_expired_ttl_triggers_refetch(self):
        cache = RevocationCache(_settings())
        ctx, mock_http = _mock_http_client({"items": [{"jti": "j1"}]})
        with _patch_httpx(ctx):
            await cache.is_revoked("j1")
            cache._fetched_at -= 16
            await cache.is_revoked("j1")
        assert mock_http.get.call_count == 2

    @pytest.mark.asyncio
    async def test_force_refresh_ignores_ttl(self):
        cache = RevocationCache(_settings())
        ctx, mock_http = _mock_http_client({"items": [{"jti": "j1"}]})
        with _patch_httpx(ctx):
            await cache.is_revoked("j1")
            await cache.force_refresh()
        assert mock_http.get.call_count == 2


class TestFailOpen:
    @pytest.mark.asyncio
    async def test_fetch_error_fails_open(self, caplog):
        cache = RevocationCache(_settings())
        ctx, _ = _mock_http_client(error=ConnectionError("auth server down"))
        with _patch_httpx(ctx), caplog.at_level("WARNING"):
            assert await cache.is_revoked("j1") is False
        assert "using stale" in caplog.text

    @pytest.mark.asyncio
    async def test_fetch_error_keeps_stale_denylist(self):
        cache = RevocationCache(_settings())
        good_ctx, _ = _mock_http_client({"items": [{"jti": "j1"}]})
        with _patch_httpx(good_ctx):
            assert await cache.is_revoked("j1") is True

        cache._fetched_at -= 16
        bad_ctx, _ = _mock_http_client(error=ConnectionError("auth server down"))
        with _patch_httpx(bad_ctx):
            assert await cache.is_revoked("j1") is True
            assert await cache.is_revoked("j2") is False

    @pytest.mark.asyncio
    async def test_fetch_error_resets_ttl_no_hammering(self):
        cache = RevocationCache(_settings())
        ctx, mock_http = _mock_http_client(error=ConnectionError("auth server down"))
        with _patch_httpx(ctx):
            await cache.is_revoked("j1")
            await cache.is_revoked("j1")
        assert mock_http.get.call_count == 1
