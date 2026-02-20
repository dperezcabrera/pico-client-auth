# Pico-Client-Auth

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**[Pico-Client-Auth](https://github.com/dperezcabrera/pico-client-auth)** provides JWT authentication for **[pico-fastapi](https://github.com/dperezcabrera/pico-fastapi)** applications. It integrates with the pico-ioc container to deliver automatic Bearer token validation, a request-scoped `SecurityContext`, role-based access control, and JWKS key rotation support.

> Requires Python 3.11+
> Built on pico-fastapi + pico-ioc
> Fully async-compatible
> Real JWKS-based token validation
> Auth by default with opt-out via `@allow_anonymous`

---

## Why pico-client-auth?

| Concern | DIY Middleware | pico-client-auth |
|---------|---------------|------------------|
| Token validation | Implement yourself | Built-in with JWKS |
| Key rotation | Manual handling | Automatic on unknown kid |
| Security context | `request.state` ad-hoc | Typed `SecurityContext` with ContextVar |
| Role checking | Scattered if/else | `@requires_role` decorator |
| Configuration | Hardcoded | `@configured` from YAML/env |
| Testing | Build your own fixtures | RSA keypair + `make_token` pattern |

---

## Core Features

- Auth by default on all routes
- `@allow_anonymous` to opt out specific endpoints
- `@requires_role("admin")` for declarative authorization
- `SecurityContext` accessible from controllers, services, and any code within a request
- JWKS fetch with TTL cache and automatic key rotation
- Extensible `RoleResolver` protocol
- Fail-fast startup if issuer/audience are missing
- Auto-discovered via `pico_boot.modules` entry point

---

## Installation

```bash
pip install pico-client-auth
```

---

## Quick Example

```yaml
# application.yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
```

```python
from pico_fastapi import controller, get
from pico_client_auth import SecurityContext, allow_anonymous, requires_role

@controller(prefix="/api")
class ApiController:

    @get("/me")
    async def get_me(self):
        claims = SecurityContext.require()
        return {"sub": claims.sub, "email": claims.email}

    @get("/health")
    @allow_anonymous
    async def health(self):
        return {"status": "ok"}

    @get("/admin")
    @requires_role("admin")
    async def admin_panel(self):
        return {"admin": True}
```

```python
from pico_boot import init
from pico_ioc import configuration, YamlTreeSource
from fastapi import FastAPI

config = configuration(YamlTreeSource("application.yaml"))
container = init(modules=["controllers"], config=config)
app = container.get(FastAPI)
# pico-client-auth is auto-discovered — all routes are now protected
```

---

## Quick Example (without pico-boot)

```python
from pico_ioc import init, configuration, YamlTreeSource
from fastapi import FastAPI

config = configuration(YamlTreeSource("application.yaml"))
container = init(
    modules=[
        "controllers",
        "pico_fastapi",
        "pico_client_auth",  # Required without pico-boot
    ],
    config=config,
)
app = container.get(FastAPI)
```

---

## SecurityContext

Access authenticated user information from anywhere within a request:

```python
from pico_client_auth import SecurityContext

# In controller, service, or repository
claims = SecurityContext.require()    # TokenClaims (raises if not auth'd)
claims = SecurityContext.get()         # TokenClaims | None
roles  = SecurityContext.get_roles()   # list[str]
SecurityContext.has_role("admin")      # bool
SecurityContext.require_role("admin")  # raises InsufficientPermissionsError
```

---

## Custom Role Resolver

Override how roles are extracted from tokens:

```python
from pico_ioc import component
from pico_client_auth import RoleResolver, TokenClaims

@component
class MyRoleResolver:
    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        return raw_claims.get("roles", [])
```

---

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `auth_client.enabled` | `true` | Enable/disable auth middleware |
| `auth_client.issuer` | `""` | Expected JWT issuer (`iss` claim) |
| `auth_client.audience` | `""` | Expected JWT audience (`aud` claim) |
| `auth_client.jwks_ttl_seconds` | `300` | JWKS cache TTL in seconds |
| `auth_client.jwks_endpoint` | `""` | JWKS URL (default: `{issuer}/api/v1/auth/jwks`) |

---

## Testing

```python
from pico_client_auth import SecurityContext, TokenClaims
from pico_client_auth.errors import MissingTokenError

def test_require_raises_when_empty():
    SecurityContext.clear()
    with pytest.raises(MissingTokenError):
        SecurityContext.require()

def test_authenticated_flow():
    claims = TokenClaims(sub="u1", email="a@b.com", role="admin",
                         org_id="o1", jti="j1")
    SecurityContext.set(claims, ["admin"])
    assert SecurityContext.require().sub == "u1"
    assert SecurityContext.has_role("admin")
    SecurityContext.clear()
```

For full e2e testing with mock JWKS and signed tokens, see the [Testing Guide](https://dperezcabrera.github.io/pico-client-auth/how-to/testing/).

---

## How It Works

- `AuthFastapiConfigurer` (priority=10) registers as an inner middleware
- Every request: extract Bearer token → validate JWT via JWKS → resolve roles → populate SecurityContext
- `@allow_anonymous` endpoints skip validation entirely
- `@requires_role` endpoints check resolved roles, return 403 if missing
- SecurityContext is cleared in `finally` — no leakage between requests

---

## License

MIT
