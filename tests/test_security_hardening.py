"""Regression tests for the security hardening: reject symmetric (HS*)
algorithms (RS/HS confusion defense) and require HTTPS for the JWKS and
revocation endpoints. These branches were added by the hardening but
previously had no coverage.
"""

from unittest.mock import AsyncMock

import jwt as pyjwt
import pytest

from pico_client_auth.config import AuthClientSettings
from pico_client_auth.errors import TokenInvalidError
from pico_client_auth.jwks_client import JWKSClient
from pico_client_auth.jwks_client import _require_https as jwks_require_https
from pico_client_auth.revocation_cache import RevocationCache
from pico_client_auth.revocation_cache import _require_https as revocation_require_https
from pico_client_auth.token_validator import TokenValidator


def _validator() -> TokenValidator:
    settings = AuthClientSettings(
        enabled=True,
        issuer="https://auth.example.com",
        audience="api",
        jwks_endpoint="https://auth.example.com/jwks",
        accepted_algorithms=("RS256",),
    )
    return TokenValidator(
        settings=settings,
        jwks_client=AsyncMock(spec=JWKSClient),
        revocation_cache=RevocationCache(AuthClientSettings()),
    )


class TestRejectSymmetricAlgorithm:
    @pytest.mark.asyncio
    async def test_hs256_token_is_rejected_before_signature_check(self):
        # An HS* token against an asymmetric validator implies an RS/HS
        # confusion attack; must be rejected regardless of accepted_algorithms.
        token = pyjwt.encode({"sub": "x"}, "public-key-as-secret", algorithm="HS256")
        with pytest.raises(TokenInvalidError, match="Symmetric algorithm"):
            await _validator().validate(token)


@pytest.mark.parametrize("require_https", [jwks_require_https, revocation_require_https])
class TestHttpsOnlyEndpoints:
    def test_https_is_allowed(self, require_https):
        require_https("https://auth.example.com/endpoint")  # no raise

    def test_http_localhost_is_allowed(self, require_https):
        require_https("http://localhost:8080/endpoint")
        require_https("http://127.0.0.1:8080/endpoint")

    def test_http_remote_is_rejected(self, require_https):
        with pytest.raises(ValueError, match="https"):
            require_https("http://auth.example.com/endpoint")
