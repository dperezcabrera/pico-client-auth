# How-To Guides

Practical step-by-step guides for common tasks with pico-client-auth.

## Available Guides

| Guide | Description |
|-------|-------------|
| [Custom Role Resolver](./custom-roles.md) | Extract roles from a `roles` array or external service |
| [Public Endpoints](./allow-anonymous.md) | Mark endpoints as publicly accessible |
| [Testing Auth](./testing.md) | Test controllers with mock tokens and role overrides |
| [Post-Quantum (ML-DSA)](./pqc.md) | Enable ML-DSA-65/87 post-quantum JWT verification |

## Quick Reference

### Protecting All Routes (Default)

All routes require a valid JWT by default. No configuration needed.

```python
@controller(prefix="/api")
class MyController:
    @get("/data")
    async def get_data(self):
        # Only accessible with valid Bearer token
        claims = SecurityContext.require()
        return {"user": claims.sub}
```

### Public Endpoints

```python
from pico_client_auth import allow_anonymous

@get("/health")
@allow_anonymous
async def health(self):
    return {"status": "ok"}
```

### Role-Based Access

```python
from pico_client_auth import requires_role

@get("/admin")
@requires_role("admin")
async def admin(self):
    return {"admin": True}

@get("/content")
@requires_role("editor", "admin")  # Any of these roles
async def content(self):
    return {"drafts": 5}
```

### Group-Based Access

```python
from pico_client_auth import requires_group

@get("/team")
@requires_group("engineering", "platform")  # Any of these groups
async def team_dashboard(self):
    return {"team": True}
```

### Accessing User Claims

```python
from pico_client_auth import SecurityContext

# In controller, service, or anywhere within a request
claims = SecurityContext.require()
print(claims.sub, claims.email, claims.org_id)

# Check roles
if SecurityContext.has_role("admin"):
    ...
    # ...
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
