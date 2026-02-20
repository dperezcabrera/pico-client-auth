# User Guide

This guide covers the core concepts and features of pico-client-auth in depth.

## Contents

| Section | Description |
|---------|-------------|
| [SecurityContext](./security-context.md) | Accessing authenticated user claims and roles |
| [Role Resolver](./role-resolver.md) | Customizing how roles are extracted from tokens |

---

## Quick Reference

### Decorators

```python
from pico_client_auth import allow_anonymous, requires_role

@allow_anonymous          # Skip auth entirely
async def public(): ...

@requires_role("admin")   # Require a specific role
async def admin(): ...

@requires_role("editor", "admin")  # Any of these roles
async def edit(): ...
```

### SecurityContext

```python
from pico_client_auth import SecurityContext

claims = SecurityContext.get()           # TokenClaims | None
claims = SecurityContext.require()       # TokenClaims (raises if None)
roles  = SecurityContext.get_roles()     # list[str]
ok     = SecurityContext.has_role("x")   # bool
SecurityContext.require_role("x", "y")   # raises InsufficientPermissionsError
```

### TokenClaims

```python
from pico_client_auth import TokenClaims

# Frozen dataclass with these fields:
# sub: str       - Subject (user ID)
# email: str     - User email
# role: str      - Primary role claim
# org_id: str    - Organisation ID
# jti: str       - JWT ID
```

### Configuration

```yaml
auth_client:
  enabled: true               # default
  issuer: https://auth.example.com
  audience: my-api
  jwks_ttl_seconds: 300       # default
  jwks_endpoint: ""           # auto: {issuer}/api/v1/auth/jwks
```

---

## Authentication Flow

```
                    Request arrives
                         |
                         v
                   Has @allow_anonymous?
                    /            \
                  Yes             No
                   |               |
                   v               v
              Skip auth     Extract Bearer token
                   |               |
                   v               v
              call_next     TokenValidator.validate()
                                   |
                                   v
                          RoleResolver.resolve()
                                   |
                                   v
                          SecurityContext.set()
                                   |
                                   v
                           Has @requires_role?
                            /            \
                          Yes             No
                           |               |
                           v               v
                     User has role?    call_next
                      /        \
                    Yes         No
                     |           |
                     v           v
                 call_next    403 Forbidden
```

---

## Best Practices

### 1. Use @allow_anonymous Sparingly

Auth-by-default is a safety net. Only mark endpoints as anonymous when genuinely public:

```python
# Good - health checks, public info
@get("/health")
@allow_anonymous
async def health(self): ...

# Avoid - accidentally exposing sensitive data
@get("/users")
@allow_anonymous  # Are you sure?
async def list_users(self): ...
```

### 2. Access Claims via SecurityContext, Not Request

```python
# Good - works everywhere (controllers, services, repositories)
claims = SecurityContext.require()

# Avoid - couples your code to FastAPI's Request object
claims = request.state.claims
```

### 3. Use @requires_role for Authorization

```python
# Good - declarative, checked by middleware
@requires_role("admin")
async def admin_panel(self): ...

# Avoid - imperative checks in handler
async def admin_panel(self):
    if not SecurityContext.has_role("admin"):
        raise HTTPException(403)
```

### 4. Override RoleResolver for Complex Scenarios

If your tokens have a `roles` array instead of a single `role` string, provide a custom `RoleResolver`:

```python
@component
class MultiRoleResolver:
    async def resolve(self, claims, raw_claims) -> list[str]:
        return raw_claims.get("roles", [])
```
