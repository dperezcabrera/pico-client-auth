# Frequently Asked Questions

## General

### What does pico-client-auth do?

It adds JWT-based authentication to pico-fastapi applications. It validates Bearer tokens, populates a `SecurityContext` with the user's claims and roles, and provides decorators for role-based access control.

### How is this different from writing my own auth middleware?

| Concern | DIY Middleware | pico-client-auth |
|---------|---------------|------------------|
| Token validation | Implement yourself | Built-in with JWKS |
| Key rotation | Manual handling | Automatic on unknown kid |
| Security context | `request.state` ad-hoc | Typed `SecurityContext` with ContextVar |
| Role checking | Scattered if/else | `@requires_role` decorator |
| Configuration | Hardcoded or custom | `@configured` from YAML/env |
| Testing | Build your own fixtures | RSA keypair + `make_token` pattern |

### Does this implement OAuth flows?

No. pico-client-auth is a **token validator**, not an identity provider. It validates JWTs issued by an external auth server. It does not handle login, token issuance, refresh tokens, or OAuth authorization flows.

### Do I need pico-boot?

No, but it's recommended. Without pico-boot, include `"pico_client_auth"` in your modules list:

```python
from pico_ioc import init

container = init(modules=[
    "myapp",
    "pico_fastapi",
    "pico_client_auth",
], config=config)
```

With pico-boot, pico-client-auth is auto-discovered.

---

## Configuration

### What happens if I don't set issuer or audience?

If `auth_client.enabled` is `True` (default) and `issuer` or `audience` are empty, the application raises `AuthConfigurationError` at startup. This fail-fast behavior prevents deploying with broken auth.

### How do I disable auth for development?

```yaml
auth_client:
  enabled: false
```

When disabled, no middleware is registered and all routes are accessible.

### How do I change the JWKS endpoint?

By default, it's `{issuer}/api/v1/auth/jwks`. Override it:

```yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
  jwks_endpoint: https://auth.example.com/.well-known/jwks.json
```

### How long are JWKS keys cached?

Default: 300 seconds (5 minutes). Configure with `jwks_ttl_seconds`:

```yaml
auth_client:
  jwks_ttl_seconds: 600  # 10 minutes
```

If a token arrives with an unknown `kid`, the cache is force-refreshed regardless of TTL.

---

## Authentication

### Which algorithms are supported?

Currently, RS256 only. The JWKS must contain RSA keys.

### What claims are extracted into TokenClaims?

| Claim | TokenClaims Field | Description |
|-------|-------------------|-------------|
| `sub` | `sub` | Subject (user ID) |
| `email` | `email` | User email |
| `role` | `role` | Primary role |
| `org_id` | `org_id` | Organisation ID |
| `jti` | `jti` | Token ID |

All other claims are available via the `raw_claims` dict in `RoleResolver.resolve()`.

### What if my token doesn't have all these claims?

Missing claims default to empty strings. `TokenClaims` is always constructed, even if some fields are empty.

### Are FastAPI's /docs and /redoc endpoints protected?

No. FastAPI's built-in documentation routes are not controller routes, so the auth middleware doesn't intercept them. They remain accessible without a token.

---

## Authorization

### How does @requires_role work?

The middleware checks the resolved roles (from `RoleResolver`) against the `@requires_role` decorator's role set. If the user has **at least one** matching role, access is granted. Otherwise, 403 Forbidden.

```text
@requires_role("editor", "admin")
# User with role "editor"  200
# User with role "admin"  200
# User with role "viewer"  403
```

### Can I check roles programmatically?

Yes, using `SecurityContext`:

```python
if SecurityContext.has_role("admin"):
    ...
    # ...

SecurityContext.require_role("admin", "superuser")  # raises if missing
```

### My tokens use a roles array, not a single role string

Override the `RoleResolver`:

```python
from pico_ioc import component
from pico_client_auth import RoleResolver, TokenClaims

@component
class ArrayRoleResolver:
    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        return raw_claims.get("roles", [])
```

---

## SecurityContext

### Can I use SecurityContext outside of controllers?

Yes! That's one of its main advantages. `SecurityContext` is backed by `ContextVar`, so it works in services, repositories, and any code running within a request:

```python
@component
class AuditService:
    def log_action(self, action: str):
        claims = SecurityContext.require()
        print(f"{claims.sub}: {action}")
```

### Is SecurityContext thread-safe?

Yes. It uses `ContextVar`, which provides isolation per async task and per thread.

### SecurityContext is empty on @allow_anonymous endpoints

Correct. The middleware skips token validation entirely on anonymous endpoints, so `SecurityContext.get()` returns `None`. Use `SecurityContext.get()` (not `require()`) on endpoints where auth is optional.

---

## Testing

### How do I test protected endpoints?

See the [Testing Auth](./how-to/testing.md) guide. In short:

1. Generate an RSA keypair in a session-scoped fixture
2. Create a `make_token` factory that signs JWTs
3. Mock the `JWKSClient` to return your test public key
4. Build a FastAPI test app with the auth configurer
5. Use `httpx.AsyncClient` with `ASGITransport`

### How do I override roles in tests?

Use container overrides:

```python
class FixedRoleResolver:
    async def resolve(self, claims, raw_claims):
        return ["admin"]

container = init(
    modules=["myapp"],
    overrides={RoleResolver: FixedRoleResolver()},
    config=config,
)
```

---

## Errors and Troubleshooting

### AuthConfigurationError at startup

**Message:** `auth_client.issuer must be set when auth is enabled`

**Fix:** Set `auth_client.issuer` and `auth_client.audience` in your config, or disable auth:

```yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
```

### 401 on all requests

**Common causes:**

1. JWKS endpoint unreachable  check network / `jwks_endpoint` config
2. Token signed with wrong key  ensure your auth server's JWKS matches
3. Wrong issuer/audience  token's `iss`/`aud` must match config

### 403 when user has the right role

**Common causes:**

1. Custom `RoleResolver` not returning the expected roles
2. `DefaultRoleResolver` reads `claims.role` (singular), but your token uses `roles` (plural)
3. Role name mismatch (case-sensitive): `"Admin"` vs `"admin"`

### Token validation works locally but not in production

Check:

1. Clock skew between servers (JWT `exp` validation is time-sensitive)
2. JWKS endpoint URL is accessible from production
3. `issuer` matches exactly (including trailing slash)
