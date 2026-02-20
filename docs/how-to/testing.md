# How to Test Authenticated Endpoints

This guide covers testing pico-client-auth protected endpoints using mock tokens, JWKS fixtures, and role overrides.

---

## Basic Setup

A typical test creates an RSA keypair, signs test tokens, and mocks the JWKS client:

```python
# conftest.py
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jose import jwt
from datetime import datetime, timedelta, UTC
import base64

@pytest.fixture(scope="session")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()

@pytest.fixture(scope="session")
def rsa_private_pem(rsa_keypair):
    private_key, _ = rsa_keypair
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

@pytest.fixture(scope="session")
def jwk_dict(rsa_keypair):
    _, public_key = rsa_keypair
    numbers = public_key.public_numbers()
    n_bytes = (numbers.n.bit_length() + 7) // 8
    def b64url(value, length):
        return base64.urlsafe_b64encode(
            value.to_bytes(length, "big")
        ).rstrip(b"=").decode()
    return {
        "kty": "RSA", "kid": "test-key-1", "use": "sig", "alg": "RS256",
        "n": b64url(numbers.n, n_bytes), "e": b64url(numbers.e, 3),
    }

@pytest.fixture(scope="session")
def make_token(rsa_private_pem):
    def _make(sub="user-1", role="admin", **overrides):
        now = datetime.now(UTC)
        payload = {
            "sub": sub, "email": f"{sub}@test.com", "role": role,
            "org_id": "org-1", "jti": "tok-1",
            "iss": "https://auth.example.com", "aud": "my-api",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
            **overrides,
        }
        return jwt.encode(payload, rsa_private_pem.decode(),
                          algorithm="RS256", headers={"kid": "test-key-1"})
    return _make
```

---

## Testing with a FastAPI Test App

Build a minimal app with the auth middleware for integration tests:

```python
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pico_client_auth.config import AuthClientSettings
from pico_client_auth.configurer import AuthFastapiConfigurer
from pico_client_auth.decorators import allow_anonymous, requires_role
from pico_client_auth.jwks_client import JWKSClient
from pico_client_auth.role_resolver import DefaultRoleResolver
from pico_client_auth.security_context import SecurityContext
from pico_client_auth.token_validator import TokenValidator

@pytest.fixture
def app(jwk_dict):
    settings = AuthClientSettings(
        enabled=True,
        issuer="https://auth.example.com",
        audience="my-api",
        jwks_ttl_seconds=300,
        jwks_endpoint="https://auth.example.com/jwks",
    )
    mock_jwks = AsyncMock(spec=JWKSClient)
    mock_jwks.get_key = AsyncMock(return_value=jwk_dict)

    validator = TokenValidator(settings=settings, jwks_client=mock_jwks)
    resolver = DefaultRoleResolver()
    configurer = AuthFastapiConfigurer(
        settings=settings, token_validator=validator, role_resolver=resolver,
    )

    app = FastAPI()
    configurer.configure(app)

    @app.get("/protected")
    async def protected():
        claims = SecurityContext.require()
        return {"sub": claims.sub}

    @app.get("/public")
    @allow_anonymous
    async def public():
        return {"ok": True}

    @app.get("/admin")
    @requires_role("admin")
    async def admin():
        return {"admin": True}

    return app

@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
```

---

## Test Cases

### 401 Without Token

```python
@pytest.mark.asyncio
async def test_no_token_returns_401(client):
    resp = await client.get("/protected")
    assert resp.status_code == 401
```

### 200 With Valid Token

```python
@pytest.mark.asyncio
async def test_valid_token(client, make_token):
    token = make_token(sub="alice")
    resp = await client.get("/protected",
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["sub"] == "alice"
```

### @allow_anonymous Works Without Token

```python
@pytest.mark.asyncio
async def test_anonymous_endpoint(client):
    resp = await client.get("/public")
    assert resp.status_code == 200
```

### @requires_role Returns 403

```python
@pytest.mark.asyncio
async def test_missing_role_returns_403(client, make_token):
    token = make_token(role="viewer")
    resp = await client.get("/admin",
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
```

### @requires_role Passes With Correct Role

```python
@pytest.mark.asyncio
async def test_correct_role(client, make_token):
    token = make_token(role="admin")
    resp = await client.get("/admin",
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
```

---

## Testing with Container Overrides

If using `pico-boot`, you can override the `RoleResolver` in tests:

```python
from pico_boot import init
from pico_client_auth import RoleResolver

class FixedRoleResolver:
    async def resolve(self, claims, raw_claims):
        return ["admin", "editor"]  # Always return these roles

container = init(
    modules=["myapp"],
    overrides={RoleResolver: FixedRoleResolver()},
    config=config,
)
```

---

## Testing SecurityContext Directly

Unit test `SecurityContext` without HTTP:

```python
from pico_client_auth import SecurityContext, TokenClaims
from pico_client_auth.errors import MissingTokenError

def test_require_raises_when_empty():
    SecurityContext.clear()
    with pytest.raises(MissingTokenError):
        SecurityContext.require()

def test_set_and_get():
    claims = TokenClaims(sub="u1", email="a@b.com", role="admin",
                         org_id="o1", jti="j1")
    SecurityContext.set(claims, ["admin"])
    assert SecurityContext.require().sub == "u1"
    assert SecurityContext.has_role("admin")
    SecurityContext.clear()
```

---

## Common Testing Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| 401 on all requests | Mock JWKS not returning the right key | Ensure `mock_jwks.get_key` returns the JWK matching your token's `kid` |
| SecurityContext leaks between tests | Missing `clear()` | Add `SecurityContext.clear()` in a fixture with `autouse=True` |
| Expired token errors | Test token uses real time | Ensure `exp` is set far in the future |
| Wrong issuer/audience | Settings don't match `make_token` | Align `issuer`/`audience` in both |
