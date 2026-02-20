# Pico-Client-Auth Documentation

`pico-client-auth` is a JWT authentication client for **[pico-fastapi](https://github.com/dperezcabrera/pico-fastapi)** applications. It provides automatic Bearer token validation, a request-scoped `SecurityContext`, role-based access control, and JWKS key rotation support.

---

## Quick Install

```bash
pip install pico-client-auth
```

For auto-discovery with pico-boot:

```bash
pip install pico-boot pico-fastapi pico-client-auth
```

---

## 30-Second Example

```python
from pico_fastapi import controller, get
from pico_client_auth import SecurityContext, allow_anonymous, requires_role

@controller(prefix="/api")
class MyController:

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

```yaml
# application.yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Auth by Default** | All routes require a valid JWT unless explicitly marked `@allow_anonymous` |
| **SecurityContext** | Access authenticated user claims anywhere in the request lifecycle |
| **Role-Based Access** | `@requires_role("admin")` decorator for fine-grained authorization |
| **JWKS Caching** | Automatic key fetch with TTL and key rotation support |
| **Extensible Roles** | Implement `RoleResolver` protocol to customise role extraction |
| **Fail-Fast** | Missing configuration raises `AuthConfigurationError` at startup |
| **Zero Config** | Auto-discovered when using pico-boot |

---

## Documentation Structure

| # | Section | Description | Link |
|---|---------|-------------|------|
| 1 | **Getting Started** | 5-minute setup guide | [getting-started.md](./getting-started.md) |
| 2 | **Tutorial** | Step-by-step walkthrough | [tutorial.md](./tutorial.md) |
| 3 | **User Guide** | Core concepts and patterns | [user-guide/](./user-guide/index.md) |
| 4 | **How-To Guides** | Practical examples | [how-to/](./how-to/index.md) |
| 5 | **Architecture** | Design and internals | [architecture.md](./architecture.md) |
| 6 | **API Reference** | Decorators, classes, exceptions | [reference/](./reference/index.md) |
| 7 | **FAQ** | Common questions | [faq.md](./faq.md) |

---

## Core APIs at a Glance

### SecurityContext

```python
from pico_client_auth import SecurityContext

# In any handler or service (within a request)
claims = SecurityContext.require()    # Raises if not authenticated
claims = SecurityContext.get()         # Returns None if not authenticated
roles  = SecurityContext.get_roles()   # Resolved roles list
SecurityContext.has_role("admin")      # Boolean check
SecurityContext.require_role("admin")  # Raises InsufficientPermissionsError
```

### Decorators

```python
from pico_client_auth import allow_anonymous, requires_role

@allow_anonymous          # Skip token validation for this endpoint
async def health(): ...

@requires_role("admin")   # 403 if user lacks the role
async def admin(): ...
```

### Custom Role Resolver

```python
from pico_ioc import component
from pico_client_auth import RoleResolver, TokenClaims

@component
class MyRoleResolver:
    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        return raw_claims.get("roles", [])
```

---

## Why Pico-Client-Auth?

| Concern | Manual Auth Middleware | pico-client-auth |
|---------|----------------------|------------------|
| Token validation | DIY per project | Automatic via JWKS |
| Key rotation | Manual handling | Auto-refresh on unknown kid |
| Security context | `request.state` ad-hoc | Typed `SecurityContext` with ContextVar |
| Role checking | Scattered if/else | `@requires_role` decorator |
| Configuration | Hardcoded | `@configured` from YAML/env |
| Testing | Mock everything | Replace `RoleResolver`, use test tokens |

---

## Next Steps

1. **New to pico-client-auth?** Start with [Getting Started](./getting-started.md)
2. **Want examples?** Check the [How-To Guides](./how-to/index.md)
3. **Need custom roles?** Read [Custom Role Resolver](./how-to/custom-roles.md)
