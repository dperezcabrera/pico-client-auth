"""Tests for TokenValidator."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from pico_client_auth.config import AuthClientSettings
from pico_client_auth.errors import TokenExpiredError, TokenInvalidError
from pico_client_auth.jwks_client import JWKSClient
from pico_client_auth.token_validator import TokenValidator


@pytest.fixture
def settings():
    return AuthClientSettings(
        enabled=True,
        issuer="https://auth.example.com",
        audience="my-api",
        jwks_ttl_seconds=300,
        jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
    )


@pytest.fixture
def mock_jwks_client(jwk_dict):
    client = AsyncMock(spec=JWKSClient)
    client.get_key = AsyncMock(return_value=jwk_dict)
    return client


@pytest.fixture
def validator(settings, mock_jwks_client):
    return TokenValidator(settings=settings, jwks_client=mock_jwks_client)


class TestValidToken:
    @pytest.mark.asyncio
    async def test_valid_token_returns_claims(self, validator, make_token):
        token = make_token()
        claims, raw = await validator.validate(token)
        assert claims.sub == "user-123"
        assert claims.email == "user@example.com"
        assert claims.role == "admin"
        assert claims.org_id == "org-1"
        assert claims.jti == "token-abc"
        assert raw["iss"] == "https://auth.example.com"


class TestExpiredToken:
    @pytest.mark.asyncio
    async def test_expired_token_raises(self, validator, make_token):
        token = make_token(expires_delta=timedelta(seconds=-60))
        with pytest.raises(TokenExpiredError, match="expired"):
            await validator.validate(token)


class TestBadSignature:
    @pytest.mark.asyncio
    async def test_wrong_key_raises(self, settings, make_token):
        """A token validated against a different key should fail."""
        import base64

        from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod

        other_key = rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)
        pub = other_key.public_key().public_numbers()
        n_bytes = (pub.n.bit_length() + 7) // 8
        other_jwk = {
            "kty": "RSA",
            "kid": "test-key-1",
            "use": "sig",
            "alg": "RS256",
            "n": base64.urlsafe_b64encode(pub.n.to_bytes(n_bytes, "big")).rstrip(b"=").decode(),
            "e": base64.urlsafe_b64encode(pub.e.to_bytes(3, "big")).rstrip(b"=").decode(),
        }
        mock_client = AsyncMock(spec=JWKSClient)
        mock_client.get_key = AsyncMock(return_value=other_jwk)
        validator = TokenValidator(settings=settings, jwks_client=mock_client)

        token = make_token()
        with pytest.raises(TokenInvalidError):
            await validator.validate(token)


class TestWrongAudience:
    @pytest.mark.asyncio
    async def test_wrong_audience_raises(self, mock_jwks_client, make_token):
        settings = AuthClientSettings(
            enabled=True,
            issuer="https://auth.example.com",
            audience="wrong-audience",
            jwks_ttl_seconds=300,
            jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
        )
        validator = TokenValidator(settings=settings, jwks_client=mock_jwks_client)
        token = make_token()
        with pytest.raises(TokenInvalidError):
            await validator.validate(token)


class TestWrongIssuer:
    @pytest.mark.asyncio
    async def test_wrong_issuer_raises(self, mock_jwks_client, make_token):
        settings = AuthClientSettings(
            enabled=True,
            issuer="https://other-issuer.com",
            audience="my-api",
            jwks_ttl_seconds=300,
            jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
        )
        validator = TokenValidator(settings=settings, jwks_client=mock_jwks_client)
        token = make_token()
        with pytest.raises(TokenInvalidError):
            await validator.validate(token)
