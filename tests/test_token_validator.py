"""Tests for TokenValidator."""

import base64
import json
import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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
        accepted_algorithms=("RS256",),
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


class TestAlgorithmNotAccepted:
    @pytest.mark.asyncio
    async def test_rejects_algorithm_not_in_accepted_list(self, mock_jwks_client, make_token):
        """RS256 token rejected when only ML-DSA-65 is accepted."""
        settings = AuthClientSettings(
            enabled=True,
            issuer="https://auth.example.com",
            audience="my-api",
            jwks_ttl_seconds=300,
            jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
            accepted_algorithms=("ML-DSA-65",),
        )
        validator = TokenValidator(settings=settings, jwks_client=mock_jwks_client)
        token = make_token()
        with pytest.raises(TokenInvalidError, match="not accepted"):
            await validator.validate(token)


class TestPQCDispatch:
    @pytest.mark.asyncio
    async def test_mldsa65_dispatches_to_pqc(self, mldsa65_keypair, mldsa65_jwk_dict, make_pqc_token):
        """ML-DSA-65 token is routed through pqc_jwt validation."""
        oqs = pytest.importorskip("oqs")
        _, secret_key = mldsa65_keypair
        token = make_pqc_token(secret_key, algorithm="ML-DSA-65", kid="pqc-key-65")

        mock_jwks = AsyncMock(spec=JWKSClient)
        mock_jwks.get_key = AsyncMock(return_value=mldsa65_jwk_dict)

        settings = AuthClientSettings(
            enabled=True,
            issuer="https://auth.example.com",
            audience="my-api",
            jwks_ttl_seconds=300,
            jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
            accepted_algorithms=("RS256", "ML-DSA-65"),
        )
        validator = TokenValidator(settings=settings, jwks_client=mock_jwks)
        claims, raw = await validator.validate(token)
        assert claims.sub == "user-123"
        assert claims.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_mldsa87_dispatches_to_pqc(self, mldsa87_keypair, mldsa87_jwk_dict, make_pqc_token):
        """ML-DSA-87 token is routed through pqc_jwt validation."""
        oqs = pytest.importorskip("oqs")
        _, secret_key = mldsa87_keypair
        token = make_pqc_token(secret_key, algorithm="ML-DSA-87", kid="pqc-key-87")

        mock_jwks = AsyncMock(spec=JWKSClient)
        mock_jwks.get_key = AsyncMock(return_value=mldsa87_jwk_dict)

        settings = AuthClientSettings(
            enabled=True,
            issuer="https://auth.example.com",
            audience="my-api",
            jwks_ttl_seconds=300,
            jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
            accepted_algorithms=("RS256", "ML-DSA-87"),
        )
        validator = TokenValidator(settings=settings, jwks_client=mock_jwks)
        claims, raw = await validator.validate(token)
        assert claims.sub == "user-123"

    @pytest.mark.asyncio
    async def test_rs256_still_uses_jose(self, settings, mock_jwks_client, make_token):
        """RS256 token continues to use the python-jose path."""
        validator = TokenValidator(settings=settings, jwks_client=mock_jwks_client)
        token = make_token()
        claims, raw = await validator.validate(token)
        assert claims.sub == "user-123"
        assert raw["iss"] == "https://auth.example.com"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_pqc_token_raw(alg="ML-DSA-65", kid="pqc-key-65", **payload_overrides) -> str:
    header = {"alg": alg, "typ": "JWT", "kid": kid}
    payload = {
        "sub": "user-123",
        "email": "user@example.com",
        "role": "admin",
        "org_id": "org-1",
        "jti": "token-abc",
        "iss": "https://auth.example.com",
        "aud": "my-api",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "groups": [],
    }
    payload.update(payload_overrides)
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    s = _b64url_encode(b"fake-signature")
    return f"{h}.{p}.{s}"


def _pqc_settings(**overrides):
    defaults = dict(
        enabled=True,
        issuer="https://auth.example.com",
        audience="my-api",
        jwks_ttl_seconds=300,
        jwks_endpoint="https://auth.example.com/api/v1/auth/jwks",
        accepted_algorithms=("RS256", "ML-DSA-65", "ML-DSA-87"),
    )
    defaults.update(overrides)
    return AuthClientSettings(**defaults)


class TestPQCDispatchMocked:
    """PQC dispatch tests using mocked oqs (no liboqs required)."""

    @pytest.mark.asyncio
    async def test_pqc_valid_token(self):
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = True
        mock_oqs = MagicMock()
        mock_oqs.Signature.return_value = mock_verifier

        pub_bytes = b"fake-public-key"
        jwk = {"kty": "AKP", "kid": "pqc-key-65", "alg": "ML-DSA-65", "pub": _b64url_encode(pub_bytes)}
        mock_jwks = AsyncMock(spec=JWKSClient)
        mock_jwks.get_key = AsyncMock(return_value=jwk)

        token = _make_pqc_token_raw()
        validator = TokenValidator(settings=_pqc_settings(), jwks_client=mock_jwks)

        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            claims, raw = await validator.validate(token)
            assert claims.sub == "user-123"
            assert claims.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_pqc_missing_pub_field(self):
        jwk = {"kty": "AKP", "kid": "pqc-key-65", "alg": "ML-DSA-65"}
        mock_jwks = AsyncMock(spec=JWKSClient)
        mock_jwks.get_key = AsyncMock(return_value=jwk)

        token = _make_pqc_token_raw()
        validator = TokenValidator(settings=_pqc_settings(), jwks_client=mock_jwks)

        with pytest.raises(TokenInvalidError, match="pub"):
            await validator.validate(token)

    @pytest.mark.asyncio
    async def test_pqc_unknown_kid(self):
        mock_jwks = AsyncMock(spec=JWKSClient)
        mock_jwks.get_key = AsyncMock(side_effect=KeyError("unknown-kid"))

        token = _make_pqc_token_raw()
        validator = TokenValidator(settings=_pqc_settings(), jwks_client=mock_jwks)

        with pytest.raises(TokenInvalidError, match="Invalid token"):
            await validator.validate(token)

    @pytest.mark.asyncio
    async def test_pqc_mldsa87_dispatches(self):
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = True
        mock_oqs = MagicMock()
        mock_oqs.Signature.return_value = mock_verifier

        pub_bytes = b"fake-public-key-87"
        jwk = {"kty": "AKP", "kid": "pqc-key-87", "alg": "ML-DSA-87", "pub": _b64url_encode(pub_bytes)}
        mock_jwks = AsyncMock(spec=JWKSClient)
        mock_jwks.get_key = AsyncMock(return_value=jwk)

        token = _make_pqc_token_raw(alg="ML-DSA-87", kid="pqc-key-87")
        validator = TokenValidator(settings=_pqc_settings(), jwks_client=mock_jwks)

        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            claims, raw = await validator.validate(token)
            assert claims.sub == "user-123"
