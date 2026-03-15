"""Shared fixtures for pico-client-auth tests."""

import base64
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
        groups: list[str] | None = None,
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
            "groups": groups or [],
        }
        if extra_claims:
            payload.update(extra_claims)
        return jwt.encode(payload, rsa_private_pem.decode(), algorithm="RS256", headers={"kid": kid})

    return _make


# ── ML-DSA (post-quantum) fixtures ──────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@pytest.fixture(scope="session")
def mldsa65_keypair():
    """Generate an ML-DSA-65 key pair. Skips if liboqs is not installed."""
    oqs = pytest.importorskip("oqs")
    sig = oqs.Signature("ML-DSA-65")
    public_key = sig.generate_keypair()
    secret_key = sig.export_secret_key()
    return public_key, secret_key


@pytest.fixture(scope="session")
def mldsa87_keypair():
    """Generate an ML-DSA-87 key pair. Skips if liboqs is not installed."""
    oqs = pytest.importorskip("oqs")
    sig = oqs.Signature("ML-DSA-87")
    public_key = sig.generate_keypair()
    secret_key = sig.export_secret_key()
    return public_key, secret_key


@pytest.fixture(scope="session")
def mldsa65_jwk_dict(mldsa65_keypair):
    """AKP JWK dict for the ML-DSA-65 test key."""
    public_key, _ = mldsa65_keypair
    return {
        "kty": "AKP",
        "kid": "pqc-key-65",
        "alg": "ML-DSA-65",
        "pub": _b64url_encode(public_key),
    }


@pytest.fixture(scope="session")
def mldsa87_jwk_dict(mldsa87_keypair):
    """AKP JWK dict for the ML-DSA-87 test key."""
    public_key, _ = mldsa87_keypair
    return {
        "kty": "AKP",
        "kid": "pqc-key-87",
        "alg": "ML-DSA-87",
        "pub": _b64url_encode(public_key),
    }


@pytest.fixture(scope="session")
def make_pqc_token():
    """Factory that creates ML-DSA signed JWT tokens."""
    oqs = pytest.importorskip("oqs")

    def _make(
        secret_key: bytes,
        algorithm: str = "ML-DSA-65",
        sub="user-123",
        email="user@example.com",
        role="admin",
        org_id="org-1",
        jti="token-abc",
        issuer="https://auth.example.com",
        audience="my-api",
        expires_delta: timedelta | None = None,
        extra_claims: dict | None = None,
        kid: str = "pqc-key-65",
        groups: list[str] | None = None,
    ) -> str:
        now = datetime.now(UTC)
        exp = now + (expires_delta if expires_delta is not None else timedelta(hours=1))

        header = {"alg": algorithm, "typ": "JWT", "kid": kid}
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
            "groups": groups or [],
        }
        if extra_claims:
            payload.update(extra_claims)

        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

        sig = oqs.Signature(algorithm, secret_key)
        signature = sig.sign(signing_input)
        signature_b64 = _b64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    return _make
