# API Reference

Complete reference documentation for pico-client-auth's public API.

## Module: pico_client_auth

### Decorators

| Decorator | Description |
|-----------|-------------|
| `@allow_anonymous` | Skip authentication for an endpoint |
| `@requires_role(*roles)` | Require at least one of the specified roles |

### Classes

| Class | Description |
|-------|-------------|
| `SecurityContext` | Static accessor for authenticated claims and roles |
| `TokenClaims` | Frozen dataclass with JWT claim fields |
| `RoleResolver` | Protocol for custom role extraction |
| `AuthClientSettings` | Configuration dataclass for auth settings |

### Exceptions

| Exception | Description |
|-----------|-------------|
| `AuthClientError` | Base exception for all pico-client-auth errors |
| `MissingTokenError` | No Bearer token found in request |
| `TokenExpiredError` | JWT token has expired |
| `TokenInvalidError` | JWT is malformed or has invalid signature |
| `InsufficientPermissionsError` | User lacks required role(s) |
| `AuthConfigurationError` | Auth configuration is missing or invalid |

---

## Decorator Reference

### @allow_anonymous

Marks an endpoint as publicly accessible without authentication.

```python
@allow_anonymous
async def my_handler(): ...
```

Sets `_pico_allow_anonymous = True` on the function. The auth middleware checks this attribute before validating the token.

---

### @requires_role

Requires the authenticated user to have at least one of the specified roles.

```text
@requires_role(*roles: str)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `*roles` | `str` | One or more role names (user must have at least one) |

**Example:**

```python
@requires_role("admin")
async def admin_only(): ...

@requires_role("editor", "admin")
async def editor_or_admin(): ...
```

Sets `_pico_required_roles = frozenset(roles)` on the function. The middleware checks this after token validation.

---

## Class Reference

### SecurityContext

Static class for accessing authenticated user state within a request.

| Method | Returns | Raises | Description |
|--------|---------|--------|-------------|
| `get()` | `TokenClaims \| None` | -- | Current claims or None |
| `require()` | `TokenClaims` | `MissingTokenError` | Current claims (must exist) |
| `get_roles()` | `list[str]` | -- | Resolved roles (returns copy) |
| `has_role(role)` | `bool` | -- | Check if user has role |
| `require_role(*roles)` | `None` | `InsufficientPermissionsError` | Assert at least one role |
| `set(claims, roles)` | `None` | -- | *Internal*: populate context |
| `clear()` | `None` | -- | *Internal*: clear context |

---

### TokenClaims

Immutable dataclass representing essential JWT claims.

```python
@dataclass(frozen=True)
class TokenClaims:
    sub: str       # Subject (user ID)
    email: str     # User email
    role: str      # Primary role claim
    org_id: str    # Organisation ID
    jti: str       # JWT ID
```

---

### RoleResolver (Protocol)

Protocol for custom role extraction from JWT claims.

```python
@runtime_checkable
class RoleResolver(Protocol):
    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]: ...
```

The default implementation (`DefaultRoleResolver`) returns `[claims.role]` if non-empty, else `[]`.

Override by registering a `@component` that satisfies this protocol.

---

### AuthClientSettings

Configuration dataclass loaded from the `auth_client` config prefix.

```python
@configured(target="self", prefix="auth_client", mapping="tree")
@dataclass
class AuthClientSettings:
    enabled: bool = True
    issuer: str = ""
    audience: str = ""
    jwks_ttl_seconds: int = 300
    jwks_endpoint: str = ""
    accepted_algorithms: tuple[str, ...] = ("RS256",)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable/disable auth middleware |
| `issuer` | `str` | `""` | Expected JWT issuer |
| `audience` | `str` | `""` | Expected JWT audience |
| `jwks_ttl_seconds` | `int` | `300` | JWKS cache TTL (seconds) |
| `jwks_endpoint` | `str` | `""` | JWKS URL (default: `{issuer}/api/v1/auth/jwks`) |
| `accepted_algorithms` | `tuple[str, ...]` | `("RS256",)` | Accepted JWT signing algorithms (e.g. `RS256`, `ML-DSA-65`, `ML-DSA-87`) |

---

## Exception Reference

### AuthClientError

Base exception for all pico-client-auth errors.

```python
try:
    ...
    # pico-client-auth operations
except AuthClientError as e:
    ...
    # Handle any auth error
```

### MissingTokenError

Raised when no Bearer token is found in the Authorization header, or when `SecurityContext.require()` is called without an authenticated context.

### TokenExpiredError

Raised when the JWT `exp` claim indicates the token has expired.

### TokenInvalidError

Raised when the JWT is malformed, has an invalid signature, wrong issuer, or wrong audience.

### InsufficientPermissionsError

Raised when `SecurityContext.require_role()` is called and the user lacks all specified roles.

### AuthConfigurationError

Raised at startup if `auth_client.enabled` is `True` but `issuer` or `audience` are empty.

---

## Auto-generated API

::: pico_client_auth
