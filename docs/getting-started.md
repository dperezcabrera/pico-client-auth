# Getting Started

This guide walks you through adding JWT authentication to a pico-fastapi application in 5 minutes.

## Prerequisites

- **Python 3.11** or newer
- A working pico-fastapi application
- A JWT issuer (auth server) that exposes a JWKS endpoint

## Installation

```bash
pip install pico-client-auth

# With post-quantum (ML-DSA) support
pip install pico-client-auth[pqc]
```

This installs:

- `pico-client-auth` - JWT authentication client
- `pico-fastapi` - FastAPI integration (dependency)
- `pico-ioc` - Core DI container (dependency)
- `PyJWT` - JWT decoding
- `httpx` - JWKS HTTP client
- `liboqs-python` - ML-DSA signature verification (only with `[pqc]` extra)

---

## Understanding the Basics

### Key Concepts

| Concept | Description |
|---------|-------------|
| **SecurityContext** | Static accessor for the current user's claims and roles |
| **TokenClaims** | Frozen dataclass with `sub`, `email`, `role`, `org_id`, `jti` |
| **@allow_anonymous** | Skip authentication for specific endpoints |
| **@requires_role** | Enforce role-based access on an endpoint |
| **RoleResolver** | Protocol to customize how roles are extracted from tokens |

### Import Pattern

```python
# Decorators and context from pico-client-auth
from pico_client_auth import SecurityContext, allow_anonymous, requires_role

# Controller decorators from pico-fastapi
from pico_fastapi import controller, get, post

# Container initialization from pico-boot
from pico_boot import init
```

---

## Step 1: Configure Your Auth Server

Create or update your `application.yaml`:

```yaml
# application.yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
  jwks_ttl_seconds: 300    # Cache JWKS for 5 minutes (default)
  # jwks_endpoint: ""      # Auto-derived: {issuer}/api/v1/auth/jwks
```

!!! warning "Fail-Fast Validation"
    If `auth_client.enabled` is `true` (the default) but `issuer` or `audience` are empty, the application will raise `AuthConfigurationError` at startup. This prevents deploying with missing auth configuration.

---

## Step 2: Add Auth Decorators to Your Controllers

```python
# controllers.py
from pico_fastapi import controller, get
from pico_client_auth import SecurityContext, allow_anonymous, requires_role

@controller(prefix="/api")
class MyController:

    @get("/me")
    async def get_current_user(self):
        """Returns the authenticated user's info. Requires a valid JWT."""
        claims = SecurityContext.require()
        return {
            "sub": claims.sub,
            "email": claims.email,
            "roles": SecurityContext.get_roles(),
        }

    @get("/health")
    @allow_anonymous
    async def health_check(self):
        """Public endpoint - no token required."""
        return {"status": "ok"}

    @get("/admin/dashboard")
    @requires_role("admin")
    async def admin_dashboard(self):
        """Only accessible to users with the 'admin' role."""
        return {"dashboard": "admin data"}
```

---

## Step 3: Bootstrap the Application

```python
# main.py
from pico_boot import init
from pico_ioc import configuration, YamlTreeSource
from fastapi import FastAPI

def create_app() -> FastAPI:
    config = configuration(YamlTreeSource("application.yaml"))
    container = init(
        modules=[
            "controllers",
        ],
        config=config,
    )
    return container.get(FastAPI)

app = create_app()
```

That's it. `pico-client-auth` is auto-discovered via the `pico_boot.modules` entry point. All routes are now protected by default.

---

## Step 4: Test It

```bash
# No token - 401
curl http://localhost:8000/api/me
# {"detail": "Missing or invalid Authorization header"}

# Public endpoint - 200
curl http://localhost:8000/api/health
# {"status": "ok"}

# With valid token - 200
curl -H "Authorization: Bearer eyJ..." http://localhost:8000/api/me
# {"sub": "user-123", "email": "user@example.com", "roles": ["admin"]}
```

---

## How It Works

```
Request Flow:

[Outer Middleware (CORS, etc.)]
        |
[PicoScopeMiddleware]          -- Creates request scope
        |
[AuthFastapiConfigurer]        -- priority=10 (inner middleware)
  1. Find matched route endpoint
  2. Check @allow_anonymous  skip if present
  3. Extract Bearer token from Authorization header
  4. TokenValidator.validate(token)  claims + raw_claims
  5. RoleResolver.resolve(claims, raw_claims)  roles
  6. SecurityContext.set(claims, roles)
  7. Check @requires_role  403 if missing
  8. call_next(request)
  9. SecurityContext.clear() in finally
        |
[Controller Handler]           -- SecurityContext available here
```

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `auth_client.enabled` | `true` | Enable/disable auth middleware |
| `auth_client.issuer` | `""` | Expected JWT issuer (`iss` claim) |
| `auth_client.audience` | `""` | Expected JWT audience (`aud` claim) |
| `auth_client.jwks_ttl_seconds` | `300` | JWKS cache TTL in seconds |
| `auth_client.jwks_endpoint` | `""` | JWKS URL (default: `{issuer}/api/v1/auth/jwks`) |
| `auth_client.accepted_algorithms` | `["RS256"]` | Accepted JWT signing algorithms |

---

## Next Steps

- [Tutorial](./tutorial.md) - Step-by-step walkthrough building a protected API
- [User Guide](./user-guide/index.md) - Deep dive into SecurityContext and roles
- [How-To Guides](./how-to/index.md) - Practical examples
- [FAQ](./faq.md) - Common questions
