# Pico-Client-Auth

[![PyPI](https://img.shields.io/pypi/v/pico-client-auth.svg)](https://pypi.org/project/pico-client-auth/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/dperezcabrera/pico-client-auth)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![CI (tox matrix)](https://github.com/dperezcabrera/pico-client-auth/actions/workflows/ci.yml/badge.svg)
[![codecov](https://codecov.io/gh/dperezcabrera/pico-client-auth/branch/main/graph/badge.svg)](https://codecov.io/gh/dperezcabrera/pico-client-auth)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-client-auth&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-client-auth)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-client-auth&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-client-auth)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-client-auth&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-client-auth)
[![PyPI Downloads](https://img.shields.io/pypi/dm/pico-client-auth)](https://pypi.org/project/pico-client-auth/)
[![Docs](https://img.shields.io/badge/Docs-pico--client--auth-blue?style=flat&logo=readthedocs&logoColor=white)](https://dperezcabrera.github.io/pico-client-auth/)
[![Interactive Lab](https://img.shields.io/badge/Learn-online-green?style=flat&logo=python&logoColor=white)](https://dperezcabrera.github.io/pico-learn/)

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
- `@requires_role("admin")` for declarative role-based authorization
- `@requires_group("team-id")` for group-based access control
- `@requires_scope("treasury:*")` for **agent-identity** authorization (dual-token, see below)
- `SecurityContext` accessible from controllers, services, and any code within a request
- JWKS fetch with TTL cache and automatic key rotation
- Optional **`jti` revocation denylist** with bounded propagation (opt-in)
- Extensible `RoleResolver` protocol
- Fail-fast startup if issuer/audience are missing
- Auto-discovered via `pico_boot.modules` entry point
- **Post-quantum ready**: ML-DSA-65 / ML-DSA-87 signature verification (optional `pqc` extra)

---

## Installation

```bash
pip install pico-client-auth

# With post-quantum (ML-DSA) support
pip install pico-client-auth[pqc]
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
from pico_client_auth import SecurityContext, allow_anonymous, requires_role, requires_group

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
groups = SecurityContext.get_groups()  # tuple[str, ...]
SecurityContext.has_group("team-id")   # bool
SecurityContext.require_group("team")  # raises InsufficientPermissionsError
```

---

## Agent Identity & Scopes *(v0.4.2+)*

A request can carry **two** tokens. `Authorization: Bearer <service-token>` proves *which service* is calling ( `SecurityContext`). `X-Agent-Authorization: Bearer <agent-token>` proves *which LLM agent is acting, on behalf of which user, with which scopes* ( `AgentContext`). Both are validated through the same `TokenValidator`/JWKS.

Gate an endpoint on agent scopes with `@requires_scope` — scope matching is a `:`-segmented glob, so `treasury:*` matches `treasury:write:budget:opex`:

```python
from pico_client_auth import requires_scope, AgentContext

@app.get("/treasury/payments")
@requires_role("treasury-service")    # service identity (Authorization)
@requires_scope("treasury:write:*")   # agent identity (X-Agent-Authorization)
async def make_payment():
    agent = AgentContext.get()        # AgentClaims | None
    return {"agent": agent.sub, "user": agent.user_id, "scopes": agent.scopes}
```

- An endpoint with `@requires_scope` returns **401** if the agent header is missing and **403** if its scopes don't satisfy the requirement.
- Endpoints **without** `@requires_scope` ignore the agent header (it's optional; `AgentContext` is still populated if a valid one is present).

### Revocation denylist (opt-in)

Set `revocation_endpoint` to have the validator reject tokens whose `jti` is on the issuer's denylist. The cache is polled every `revocation_ttl_seconds` (default 15s — the worst-case window between an operator revoking and validators rejecting). Empty endpoint (default) = signature-only validation. JWKS rotation remains the instant-kill path.

If a poll fails, tokens carrying a `jti` are **rejected**: a denylist that cannot be reached means revocation status cannot be confirmed. Set `revocation_fail_open: true` to accept them instead, trading prompt revocation for availability.

## Token Validation Hardening *(v0.6.0+)*

Three rules the validator enforces unconditionally, independent of configuration:

- **`exp` is mandatory.** A token without an expiry is rejected rather than treated as non-expiring. `nbf` is enforced when present.
- **Symmetric `HS*` algorithms are rejected**, even if listed in `accepted_algorithms`. This path verifies with public keys, so an `HS256` token implies an RS/HS confusion attack — signing with the public key as the HMAC secret.
- **JWKS and revocation endpoints must be `https`.** Plain `http` is permitted only for `localhost`, `127.0.0.1` and `::1`, so development still works.

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
| `auth_client.accepted_algorithms` | `["RS256"]` | List of accepted JWT signing algorithms |
| `auth_client.revocation_endpoint` | `""` | `jti` denylist URL to poll. Empty = revocation disabled |
| `auth_client.revocation_ttl_seconds` | `15` | Poll interval / worst-case revokereject window |
| `auth_client.revocation_bearer` | `""` | Optional bearer token for the revocation endpoint |
| `auth_client.revocation_fail_open` | `false` | Accept tokens when the denylist fetch fails instead of rejecting them |

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

## Post-Quantum (ML-DSA) Support

pico-client-auth supports ML-DSA-65 (NIST Level 3) and ML-DSA-87 (NIST Level 5) post-quantum signature verification via the optional `pqc` extra.

```yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
  accepted_algorithms:
    - RS256
    - ML-DSA-65
```

ML-DSA tokens use the [draft-ietf-cose-dilithium](https://datatracker.ietf.org/doc/draft-ietf-cose-dilithium/) JOSE standard:
- **kty**: `"AKP"` (Algorithm Key Pair)
- **alg**: `"ML-DSA-65"` or `"ML-DSA-87"`
- **pub**: base64url-encoded raw public key

Requires `liboqs-python` (installed automatically with `pip install pico-client-auth[pqc]`). When liboqs is not installed, ML-DSA tokens are rejected with `AuthConfigurationError`.

---

## How It Works

- `AuthFastapiConfigurer` (priority=10) registers as an inner middleware
- Every request: extract Bearer token  validate JWT via JWKS  resolve roles  populate SecurityContext
- Algorithm dispatch: RS256 tokens use PyJWT, ML-DSA tokens use liboqs
- `@allow_anonymous` endpoints skip validation entirely
- `@requires_role` endpoints check resolved roles, return 403 if missing
- `@requires_group` endpoints check group membership, return 403 if missing
- SecurityContext is cleared in `finally` — no leakage between requests

---

## Built for AI-assisted development

pico-client-auth is part of an ecosystem designed for humans and coding agents building software together. Every package ships `AGENTS.md` working conventions, an `llms.txt` machine-readable docs index and documented behaviour pinned by regression tests; [pico-testing](https://github.com/dperezcabrera/pico-testing) gives agents a verification loop for their own changes, and releases are gated by the whole ecosystem booting together against real infrastructure. The full story: [Built for AI-assisted development](https://github.com/dperezcabrera/pico-ioc#built-for-ai-assisted-development).

Install the agent skills for [Claude Code](https://code.claude.com) or [OpenAI Codex](https://openai.com/index/introducing-codex/):

```bash
curl -sL https://raw.githubusercontent.com/dperezcabrera/pico-skills/main/install.sh | bash
```

The `pico-conventions` skill teaches the assistant this module's API surface and invariants; `/add-component` and `/add-tests` scaffold components and tests that use it.

## License

MIT
