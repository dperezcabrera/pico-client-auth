# Tutorial: Protect Your API in 5 Minutes

In this tutorial, we will add JWT authentication to a pico-fastapi application. You will learn how to protect endpoints, access authenticated user information, and enforce role-based access control.

> **Recommended:** Use `pico-boot` for auto-discovery and zero-config bootstrapping.

---

## Prerequisites

Install all required packages:

```bash
pip install fastapi uvicorn pico-ioc pico-fastapi pico-boot pico-client-auth
```

---

## Step 1: Create Your Configuration

```yaml
# application.yaml
fastapi:
  title: Protected API
  version: 1.0.0

auth_client:
  issuer: https://auth.example.com
  audience: my-api
```

---

## Step 2: Define a Service

```python
# services.py
from pico_ioc import component
from pico_client_auth import SecurityContext

@component
class UserService:
    def get_profile(self) -> dict:
        claims = SecurityContext.require()
        return {
            "sub": claims.sub,
            "email": claims.email,
            "org_id": claims.org_id,
            "roles": SecurityContext.get_roles(),
        }

    def is_admin(self) -> bool:
        return SecurityContext.has_role("admin")
```

Notice how `SecurityContext` can be used **anywhere** in the call chain, not just in the controller. The middleware populates it before the handler runs, and clears it afterward.

---

## Step 3: Create Protected Controllers

```python
# controllers.py
from pico_fastapi import controller, get
from pico_client_auth import allow_anonymous, requires_role
from services import UserService

@controller(prefix="/api", tags=["API"])
class ApiController:
    def __init__(self, user_service: UserService):
        self.user_service = user_service

    @get("/me")
    async def get_profile(self):
        """Get the authenticated user's profile."""
        return self.user_service.get_profile()

    @get("/health")
    @allow_anonymous
    async def health(self):
        """Public health check - no token required."""
        return {"status": "ok"}

    @get("/admin/stats")
    @requires_role("admin")
    async def admin_stats(self):
        """Admin-only endpoint."""
        return {"users": 42, "active": 30}

    @get("/editor/drafts")
    @requires_role("editor", "admin")
    async def editor_drafts(self):
        """Accessible to editors and admins."""
        return {"drafts": 5}
```

---

## Step 4: Wire the Application

```python
# main.py
from pico_boot import init
from pico_ioc import configuration, YamlTreeSource
from fastapi import FastAPI

def create_app() -> FastAPI:
    config = configuration(YamlTreeSource("application.yaml"))
    container = init(
        modules=[
            "services",
            "controllers",
        ],
        config=config,
    )
    return container.get(FastAPI)

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Step 5: Run and Test

```bash
uvicorn main:app --reload
```

### Test the endpoints:

```bash
# Public endpoint - works without token
curl http://localhost:8000/api/health
# {"status": "ok"}

# Protected endpoint - 401 without token
curl http://localhost:8000/api/me
# {"detail": "Missing or invalid Authorization header"}

# With a valid token
curl -H "Authorization: Bearer eyJ..." http://localhost:8000/api/me
# {"sub": "user-123", "email": "user@example.com", "org_id": "org-1", "roles": ["admin"]}

# Admin endpoint with non-admin token - 403
curl -H "Authorization: Bearer eyJ..." http://localhost:8000/api/admin/stats
# {"detail": "Requires one of roles: ['admin']"}
```

---

## Key Takeaways

1. **Auth by default**
   Every route is protected unless you explicitly add `@allow_anonymous`. This prevents accidental exposure of endpoints.

2. **SecurityContext is available everywhere**
   Not just in controllers -- services, repositories, and any code running within a request can access the authenticated user via `SecurityContext`.

3. **Role-based access is declarative**
   `@requires_role("admin")` reads clearly and is checked by the middleware before your handler runs.

4. **Fail-fast configuration**
   If `issuer` or `audience` are missing, the application won't start. No silent authentication bypass.

5. **Auto-discovery with pico-boot**
   `pico-client-auth` loads itself automatically. No need to include it in your modules list.

---

## Classic Version (Without pico-boot)

If you are not using `pico-boot`, use `pico_ioc.init()` directly and include `"pico_client_auth"` in the modules list:

```python
from pico_ioc import init

container = init(
    modules=[
        "services",
        "controllers",
        "pico_fastapi",       # Required without pico-boot
        "pico_client_auth",   # Required without pico-boot
    ],
    config=config,
)
```
