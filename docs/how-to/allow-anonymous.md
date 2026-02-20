# How to Create Public Endpoints

This guide shows how to mark specific endpoints as publicly accessible, bypassing JWT token validation.

---

## The Problem

By default, **all routes** require a valid JWT token. Public endpoints like health checks, login pages, or public APIs need to opt out of authentication.

---

## Using @allow_anonymous

Apply the `@allow_anonymous` decorator to any controller method:

```python
from pico_fastapi import controller, get
from pico_client_auth import allow_anonymous

@controller(prefix="/api")
class ApiController:

    @get("/health")
    @allow_anonymous
    async def health(self):
        """No token required."""
        return {"status": "ok"}

    @get("/version")
    @allow_anonymous
    async def version(self):
        """Also public."""
        return {"version": "1.0.0"}

    @get("/data")
    async def get_data(self):
        """This still requires a token."""
        return {"secret": "data"}
```

---

## How It Works

The middleware checks for the `_pico_allow_anonymous` attribute on the matched endpoint function:

1. Route is matched via Starlette's `route.matches(scope)`
2. If the endpoint has `_pico_allow_anonymous = True`, skip auth entirely
3. The request proceeds to the handler without any token validation
4. `SecurityContext` will be empty (`get()` returns `None`)

---

## Accessing Optional Claims on Anonymous Endpoints

On `@allow_anonymous` endpoints, the middleware skips token validation entirely. If you want to *optionally* read claims when a token is present (but not require it), you'll need to handle that in the endpoint:

```python
from pico_client_auth import SecurityContext, allow_anonymous

@get("/greeting")
@allow_anonymous
async def greeting(self):
    claims = SecurityContext.get()  # None if no token
    if claims:
        return {"message": f"Hello, {claims.email}!"}
    return {"message": "Hello, guest!"}
```

!!! note
    On `@allow_anonymous` routes, the middleware does **not** validate the token even if one is provided. `SecurityContext` will be empty.

---

## Common Use Cases

| Endpoint | Why Anonymous |
|----------|--------------|
| `/health`, `/ready` | Load balancer / k8s probes |
| `/version`, `/info` | Public metadata |
| `/docs`, `/openapi.json` | FastAPI auto-generated docs |
| `/auth/login` | Login page or token exchange |
| `/public/*` | Public content APIs |

---

## FastAPI Built-in Routes

FastAPI's built-in routes (`/docs`, `/redoc`, `/openapi.json`) are **not** controller routes, so the auth middleware won't affect them. They are handled by FastAPI before the middleware runs for route matching.
