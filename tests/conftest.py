"""Shared fixtures for pico-client-auth tests."""

import json
import time
from datetime import UTC, datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt


@pytest.fixture(scope="session")
def rsa_keypair():
    """Generate an RSA key pair for signing/verifying JWTs in tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture(scope="session")
def rsa_private_pem(rsa_keypair):
    """PEM-encoded private key bytes."""
    private_key, _ = rsa_keypair
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@pytest.fixture(scope="session")
def rsa_public_pem(rsa_keypair):
    """PEM-encoded public key bytes."""
    _, public_key = rsa_keypair
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


@pytest.fixture(scope="session")
def jwk_dict(rsa_keypair):
    """Build a JWK dict from the RSA public key (for JWKS mock responses)."""
    import base64

    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

    _, public_key = rsa_keypair
    numbers = public_key.public_numbers()

    def _b64url(value: int, length: int) -> str:
        return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()

    n_bytes = (numbers.n.bit_length() + 7) // 8
    return {
        "kty": "RSA",
        "kid": "test-key-1",
        "use": "sig",
        "alg": "RS256",
        "n": _b64url(numbers.n, n_bytes),
        "e": _b64url(numbers.e, 3),
    }


@pytest.fixture(scope="session")
def jwks_response(jwk_dict):
    """A JWKS response dict containing a single test key."""
    return {"keys": [jwk_dict]}


@pytest.fixture(scope="session")
def make_token(rsa_private_pem):
    """Factory that creates signed JWT tokens with customisable claims."""

    def _make(
        sub="user-123",
        email="user@example.com",
        role="admin",
        org_id="org-1",
        jti="token-abc",
        issuer="https://auth.example.com",
        audience="my-api",
        expires_delta: timedelta | None = None,
        extra_claims: dict | None = None,
        kid: str = "test-key-1",
    ) -> str:
        now = datetime.now(UTC)
        exp = now + (expires_delta if expires_delta is not None else timedelta(hours=1))
        payload = {
            "sub": sub,
            "email": email,
            "role": role,
            "org_id": org_id,
            "jti": jti,
            "iss": issuer,
            "aud": audience,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        if extra_claims:
            payload.update(extra_claims)
        return jwt.encode(payload, rsa_private_pem.decode(), algorithm="RS256", headers={"kid": kid})

    return _make
