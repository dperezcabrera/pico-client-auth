# How to Implement a Custom Role Resolver

This guide shows how to override the default role extraction logic to support multi-role tokens, external role services, or custom claim structures.

---

## Why Override the Default?

The `DefaultRoleResolver` reads a single `role` string from `TokenClaims`. This works for simple tokens like:

```json
{"sub": "user-123", "role": "admin", ...}
```

But many auth servers use different structures:

- **Roles array**: `{"roles": ["admin", "editor"]}`
- **Realm roles** (Keycloak): `{"realm_access": {"roles": ["admin"]}}`
- **Permissions**: `{"permissions": ["read:users", "write:orders"]}`
- **External lookup**: Roles stored in a database, not in the token

---

## Example 1: Roles Array

For tokens with a `roles` array claim:

```json
{
  "sub": "user-123",
  "roles": ["admin", "editor", "viewer"],
  "email": "user@example.com"
}
```

```python
from pico_ioc import component
from pico_client_auth import RoleResolver, TokenClaims

@component
class ArrayRoleResolver:
    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        return raw_claims.get("roles", [])
```

---

## Example 2: Keycloak Realm Roles

For Keycloak tokens with nested realm access:

```json
{
  "sub": "user-123",
  "realm_access": {
    "roles": ["admin", "uma_authorization"]
  }
}
```

```python
@component
class KeycloakRoleResolver:
    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        realm_access = raw_claims.get("realm_access", {})
        return realm_access.get("roles", [])
```

---

## Example 3: Database Roles with TTL Cache

When roles are managed in a database rather than embedded in the token, use a resolver that queries the database and caches results per user to avoid repeated queries.

```python
import time

from pico_ioc import component
from pico_client_auth import RoleResolver, TokenClaims


@component
class DatabaseRoleResolver:
    """Resolves roles from a database with per-user TTL cache."""

    def __init__(self, role_repository: RoleRepository):
        self._repo = role_repository
        self._cache: dict[str, tuple[float, list[str]]] = {}
        self._ttl = 300  # 5 minutes

    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        cached = self._cache.get(claims.sub)
        if cached and (time.monotonic() - cached[0]) < self._ttl:
            return cached[1]

        roles = await self._repo.find_roles_by_user(claims.sub)
        self._cache[claims.sub] = (time.monotonic(), roles)
        return roles
```

The repository component:

```python
from pico_ioc import component
from pico_sqlalchemy import get_session, SessionManager
from sqlalchemy import select


@component
class RoleRepository:
    def __init__(self, session_manager: SessionManager):
        self._sm = session_manager

    async def find_roles_by_user(self, user_id: str) -> list[str]:
        async with get_session(self._sm) as session:
            result = await session.execute(
                select(UserRole.role).where(UserRole.user_id == user_id)
            )
            return [r[0] for r in result.all()]
```

The request flow:

```
Request  Bearer token  TokenValidator (JWT signature)
                              ↓
                    DatabaseRoleResolver (DB + cache)
                              ↓
                    SecurityContext.set(claims, roles)
                              ↓
                    @requires_role("admin") ← uses resolved roles
```

---

## Example 4: Hybrid Token + Database Roles

Combine roles from the token with additional roles from a database:

```python
import time

from pico_ioc import component
from pico_client_auth import RoleResolver, TokenClaims


@component
class HybridRoleResolver:
    """Merges token roles with database roles, cached per user."""

    def __init__(self, role_repository: RoleRepository):
        self._repo = role_repository
        self._cache: dict[str, tuple[float, list[str]]] = {}
        self._ttl = 300

    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        # Token roles (always fresh)
        token_roles = raw_claims.get("roles", [])

        # Database roles (cached)
        cached = self._cache.get(claims.sub)
        if cached and (time.monotonic() - cached[0]) < self._ttl:
            db_roles = cached[1]
        else:
            db_roles = await self._repo.find_roles_by_user(claims.sub)
            self._cache[claims.sub] = (time.monotonic(), db_roles)

        return list(set(token_roles + db_roles))
```

---

## Example 5: Configurable TTL

Read the cache TTL from application configuration:

```yaml
# application.yaml
roles:
  cache_ttl_seconds: 600
```

```python
from dataclasses import dataclass

from pico_ioc import component, configured
from pico_client_auth import RoleResolver, TokenClaims


@configured(target="self", prefix="roles", mapping="tree")
@dataclass
class RolesSettings:
    cache_ttl_seconds: int = 300
```

```python
import time

@component
class DatabaseRoleResolver:
    def __init__(self, settings: RolesSettings, role_repository: RoleRepository):
        self._repo = role_repository
        self._cache: dict[str, tuple[float, list[str]]] = {}
        self._ttl = settings.cache_ttl_seconds

    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        cached = self._cache.get(claims.sub)
        if cached and (time.monotonic() - cached[0]) < self._ttl:
            return cached[1]

        roles = await self._repo.find_roles_by_user(claims.sub)
        self._cache[claims.sub] = (time.monotonic(), roles)
        return roles
```

---

## How It Works

When you register a `@component` that satisfies the `RoleResolver` protocol, pico-ioc uses it instead of the `DefaultRoleResolver`:

- `DefaultRoleResolver` is registered with `on_missing_selector=RoleResolver`
- Your `@component` takes priority automatically
- No configuration changes needed

---

## Testing Your Resolver

### Unit test (no database)

```python
import pytest
from pico_client_auth import TokenClaims


@pytest.fixture
def resolver():
    return ArrayRoleResolver()


@pytest.mark.asyncio
async def test_extracts_roles_from_array(resolver):
    claims = TokenClaims(sub="u1", email="a@b.com", role="", org_id="o1", jti="j1")
    raw = {"roles": ["admin", "editor"]}

    roles = await resolver.resolve(claims, raw)
    assert roles == ["admin", "editor"]


@pytest.mark.asyncio
async def test_empty_roles(resolver):
    claims = TokenClaims(sub="u1", email="a@b.com", role="", org_id="o1", jti="j1")
    raw = {}

    roles = await resolver.resolve(claims, raw)
    assert roles == []
```

### Testing the database resolver with a mock

```python
from unittest.mock import AsyncMock

import pytest
from pico_client_auth import TokenClaims


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.find_roles_by_user.return_value = ["admin", "editor"]
    return repo


@pytest.fixture
def resolver(mock_repo):
    return DatabaseRoleResolver(role_repository=mock_repo)


@pytest.mark.asyncio
async def test_fetches_roles_from_db(resolver, mock_repo):
    claims = TokenClaims(sub="u1", email="a@b.com", role="", org_id="o1", jti="j1")

    roles = await resolver.resolve(claims, {})
    assert set(roles) == {"admin", "editor"}
    mock_repo.find_roles_by_user.assert_called_once_with("u1")


@pytest.mark.asyncio
async def test_cache_avoids_repeated_queries(resolver, mock_repo):
    claims = TokenClaims(sub="u1", email="a@b.com", role="", org_id="o1", jti="j1")

    await resolver.resolve(claims, {})
    await resolver.resolve(claims, {})

    # Only one DB call thanks to cache
    mock_repo.find_roles_by_user.assert_called_once()


@pytest.mark.asyncio
async def test_override_in_container(mock_repo):
    from pico_client_auth import RoleResolver
    from pico_ioc import init

    # Tests use pico_ioc.init, not pico_boot.init: it loads exactly the listed
    # modules, so other pico plugins installed in the venv cannot leak in.
    # That is why "pico_client_auth" is declared explicitly.
    container = init(
        modules=["pico_client_auth", "myapp"],
        overrides={RoleResolver: DatabaseRoleResolver(role_repository=mock_repo)},
    )
    resolver = container.get(RoleResolver)
    assert isinstance(resolver, DatabaseRoleResolver)
```
