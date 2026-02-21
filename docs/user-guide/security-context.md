# SecurityContext

`SecurityContext` is a static class that provides access to the current request's authentication state. It follows the Spring `SecurityContextHolder` pattern: a globally accessible, task-isolated store backed by Python's `ContextVar`.

---

## Basic Usage

### Get Claims (Optional)

Returns `None` if the request is unauthenticated (e.g., on an `@allow_anonymous` endpoint):

```python
from pico_client_auth import SecurityContext

claims = SecurityContext.get()
if claims:
    print(f"User: {claims.sub}")
```

### Require Claims

Raises `MissingTokenError` if not authenticated:

```python
claims = SecurityContext.require()
# Always returns TokenClaims, never None
```

### Check and Require Roles

```python
# Boolean check
if SecurityContext.has_role("admin"):
    # ...

# Get all roles
roles = SecurityContext.get_roles()  # e.g. ["admin", "editor"]

# Assert role (raises InsufficientPermissionsError)
SecurityContext.require_role("admin", "superuser")
```

### Check and Require Groups

```python
# Get all groups
groups = SecurityContext.get_groups()  # e.g. ("engineering", "platform")

# Boolean check
if SecurityContext.has_group("engineering"):
    # ...

# Assert group membership (raises InsufficientPermissionsError)
SecurityContext.require_group("engineering", "platform")
```

---

## TokenClaims Fields

`TokenClaims` is a frozen (immutable) dataclass:

| Field | Type | Description |
|-------|------|-------------|
| `sub` | `str` | Subject identifier (user ID) |
| `email` | `str` | User email address |
| `role` | `str` | Primary role claim from the token |
| `org_id` | `str` | Organisation identifier |
| `jti` | `str` | Unique token identifier (JWT ID) |
| `groups` | `tuple[str, ...]` | Group IDs from the JWT (default `()`) |

```python
claims = SecurityContext.require()
print(claims.sub)       # "user-123"
print(claims.email)     # "user@example.com"
print(claims.role)      # "admin"
print(claims.org_id)    # "org-1"
print(claims.jti)       # "token-abc"
```

---

## Using SecurityContext in Services

A key advantage of `SecurityContext` over `request.state` is that it works **anywhere** in your code, not just in controllers:

```python
from pico_ioc import component
from pico_client_auth import SecurityContext

@component
class AuditService:
    def log_action(self, action: str):
        claims = SecurityContext.get()
        user_id = claims.sub if claims else "anonymous"
        print(f"[AUDIT] {user_id}: {action}")

@component
class OrderService:
    def __init__(self, audit: AuditService):
        self.audit = audit

    def create_order(self, items: list) -> dict:
        claims = SecurityContext.require()
        self.audit.log_action("create_order")
        return {"order_id": "123", "user": claims.sub}
```

---

## Async Task Isolation

`SecurityContext` uses `ContextVar`, which means each `asyncio.Task` gets its own copy. This is safe for concurrent requests:

```python
import asyncio
from pico_client_auth import SecurityContext

# Task A sets claims for user "alice"
# Task B sets claims for user "bob"
# They never interfere with each other
```

---

## Lifecycle

The auth middleware manages the `SecurityContext` lifecycle automatically:

1. **Before handler**: `SecurityContext.set(claims, roles)`
2. **During handler**: `SecurityContext.get()` / `SecurityContext.require()`
3. **After handler (finally)**: `SecurityContext.clear()`

You should **never** need to call `set()` or `clear()` yourself. These are internal APIs used by the middleware.

---

## API Summary

| Method | Returns | Raises | Description |
|--------|---------|--------|-------------|
| `get()` | `TokenClaims \| None` | -- | Current claims or None |
| `require()` | `TokenClaims` | `MissingTokenError` | Current claims (must exist) |
| `get_roles()` | `list[str]` | -- | Resolved roles (copy) |
| `has_role(role)` | `bool` | -- | Check single role |
| `require_role(*roles)` | `None` | `InsufficientPermissionsError` | Assert at least one role |
| `get_groups()` | `tuple[str, ...]` | -- | Group IDs for current request |
| `has_group(group_id)` | `bool` | -- | Check single group membership |
| `require_group(*group_ids)` | `None` | `InsufficientPermissionsError` | Assert at least one group |
| `set(claims, roles)` | `None` | -- | Internal: set by middleware |
| `clear()` | `None` | -- | Internal: cleared by middleware |
