# Exceptions

This reference documents the custom exception classes provided by pico-client-auth. These exceptions cover authentication failures, authorization errors, and configuration problems.

## Overview

- `AuthClientError` is the common base class for all custom errors in pico-client-auth.
- Authentication errors (401): `MissingTokenError`, `TokenExpiredError`, `TokenInvalidError`
- Authorization errors (403): `InsufficientPermissionsError`
- Configuration errors (startup): `AuthConfigurationError`

Catching the base class lets you handle all pico-client-auth-specific errors in one place.

Typical import:

```python
from pico_client_auth import (
    AuthClientError,
    MissingTokenError,
    TokenExpiredError,
    TokenInvalidError,
    InsufficientPermissionsError,
    AuthConfigurationError,
)
```

## AuthClientError

Base class for all pico-client-auth exceptions.

- Use this to catch any auth error without matching a concrete subclass.

```python
try:
    bootstrap_app()
except AuthClientError as exc:
    logger.error(f"Auth setup failed: {exc}")
    raise
```

## MissingTokenError

Raised when no Bearer token is found in the Authorization header.

Also raised by `SecurityContext.require()` when the security context is empty.

**HTTP mapping:** 401 Unauthorized

```python
from pico_client_auth import SecurityContext
from pico_client_auth.errors import MissingTokenError

try:
    claims = SecurityContext.require()
except MissingTokenError:
    # No authenticated user
    pass
```

## TokenExpiredError

Raised when the JWT `exp` claim indicates the token has expired.

**HTTP mapping:** 401 Unauthorized

## TokenInvalidError

Raised when the JWT fails validation:

- Malformed token (not a valid JWT)
- Invalid signature (wrong key)
- Wrong issuer (doesn't match `auth_client.issuer`)
- Wrong audience (doesn't match `auth_client.audience`)
- Unknown key ID (kid not found in JWKS)

**HTTP mapping:** 401 Unauthorized

## InsufficientPermissionsError

Raised when the authenticated user lacks the required role(s).

Triggered by:

- `@requires_role("admin")` decorator when the user doesn't have the role
- `SecurityContext.require_role("admin")` call

**HTTP mapping:** 403 Forbidden

```python
from pico_client_auth.errors import InsufficientPermissionsError

try:
    SecurityContext.require_role("admin")
except InsufficientPermissionsError:
    # User is authenticated but lacks the role
    pass
```

## AuthConfigurationError

Raised at application startup if `auth_client.enabled` is `True` but `issuer` or `audience` are empty.

This is a **fail-fast** mechanism to prevent deploying with broken authentication.

**When raised:** During container initialization, in `AuthFastapiConfigurer.__init__()`.

```python
from pico_client_auth.errors import AuthConfigurationError

try:
    container = init(modules=["myapp"], config=config)
    app = container.get(FastAPI)
except AuthConfigurationError as exc:
    logger.error(f"Missing auth config: {exc}")
    sys.exit(1)
```

## Error Response Format

The auth middleware returns JSON errors with a consistent format:

```json
{"detail": "Human-readable error message"}
```

| Exception | Status Code | Example Detail |
|-----------|-------------|----------------|
| `MissingTokenError` | 401 | `"Missing or invalid Authorization header"` |
| `TokenExpiredError` | 401 | `"Token has expired"` |
| `TokenInvalidError` | 401 | `"Invalid token: Signature verification failed"` |
| `InsufficientPermissionsError` | 403 | `"Requires one of roles: ['admin']"` |

## Recommendations

- Catch `AuthClientError` at application boundaries (e.g., startup) to handle all auth failures in a single place.
- Do not rely on the exact exception message in code paths; match on the exception class.
- Use `AuthConfigurationError` in deployment scripts to fail fast on misconfiguration.

---

## Auto-generated API

::: pico_client_auth.errors
