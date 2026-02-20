# Role Resolver

The `RoleResolver` protocol defines how user roles are extracted from JWT claims. pico-client-auth provides a default implementation, but you can replace it with your own.

---

## Default Behavior

The `DefaultRoleResolver` extracts the single `role` field from `TokenClaims`:

```python
class DefaultRoleResolver:
    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        return [claims.role] if claims.role else []
```

For a token with `{"role": "admin"}`, this returns `["admin"]`.

---

## The RoleResolver Protocol

```python
from typing import Protocol, runtime_checkable
from pico_client_auth import TokenClaims

@runtime_checkable
class RoleResolver(Protocol):
    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]: ...
```

Parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `claims` | `TokenClaims` | Parsed structured claims |
| `raw_claims` | `dict` | Full decoded JWT payload (all fields) |

The `raw_claims` dict gives you access to any custom claims not mapped to `TokenClaims` fields.

---

## Overriding the Default

Register your own `@component` implementing `RoleResolver`. pico-ioc will use it instead of the default (which is registered with `on_missing_selector`):

```python
from pico_ioc import component
from pico_client_auth import RoleResolver, TokenClaims

@component
class MultiRoleResolver:
    """Extract roles from a 'roles' array claim."""

    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        return raw_claims.get("roles", [])
```

No additional configuration needed. Because `DefaultRoleResolver` uses `on_missing_selector=RoleResolver`, your component takes priority automatically.

---

## Advanced: Roles from an External Service

```python
@component
class DatabaseRoleResolver:
    """Fetch roles from a database based on the user's org and sub."""

    def __init__(self, role_repo: RoleRepository):
        self.role_repo = role_repo

    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        return await self.role_repo.get_roles(
            user_id=claims.sub,
            org_id=claims.org_id,
        )
```

---

## How It's Wired

The middleware calls `RoleResolver.resolve()` after token validation:

```
TokenValidator.validate(token)
        |
        v
  (TokenClaims, raw_claims)
        |
        v
RoleResolver.resolve(claims, raw_claims)
        |
        v
     roles: list[str]
        |
        v
SecurityContext.set(claims, roles)
```

The resolved roles are used for:

1. `@requires_role` decorator checks
2. `SecurityContext.get_roles()`
3. `SecurityContext.has_role()`
4. `SecurityContext.require_role()`
