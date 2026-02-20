# pico-client-auth

JWT authentication client for pico-fastapi. Bearer token validation, SecurityContext, role-based access control, and JWKS support.

## Commands

```bash
pip install -e ".[test]"          # Install in dev mode
pytest tests/ -v                  # Run tests
pytest --cov=pico_client_auth --cov-report=term-missing tests/  # Coverage
tox                               # Full matrix (3.11-3.14)
```

## Project Structure

```
src/pico_client_auth/
  __init__.py          # Public API exports
  errors.py            # AuthClientError hierarchy
  models.py            # TokenClaims frozen dataclass
  config.py            # AuthClientSettings (@configured)
  decorators.py        # @allow_anonymous, @requires_role
  security_context.py  # SecurityContext (ContextVar-backed singleton)
  role_resolver.py     # RoleResolver protocol + DefaultRoleResolver
  jwks_client.py       # JWKSClient - JWKS fetch + cache with TTL
  token_validator.py   # TokenValidator - JWT decode + validate
  configurer.py        # AuthFastapiConfigurer (FastApiConfigurer, priority=10)
```

## Key Concepts

- **`AuthFastapiConfigurer`**: FastApiConfigurer with priority=10 (inner middleware). Registers auth middleware that validates JWT on every request.
- **`SecurityContext`**: Static accessor backed by ContextVar. Set by middleware, cleared in finally.
- **`@allow_anonymous`**: Skip auth for specific endpoints.
- **`@requires_role("admin")`**: Enforce role-based access after authentication.
- **`RoleResolver`**: Protocol for custom role extraction. DefaultRoleResolver uses `claims.role`.
- **`JWKSClient`**: Fetches JWKS with TTL cache. Force-refreshes on unknown kid (key rotation).
- **Fail-fast**: AuthConfigurationError raised at startup if issuer/audience missing when enabled.

## Code Style

- Python 3.11+
- Async-first for middleware, validators, resolvers
- Use pico-ioc's `@component`, `@configured` decorators
- Error responses: JSON `{"detail": "..."}` with 401/403 status

## Testing

- pytest + pytest-asyncio (mode=auto)
- RSA keypair fixture (session-scoped) for JWT signing
- Mock JWKSClient for token validator tests
- httpx AsyncClient with ASGITransport for e2e tests
- Target: >95% coverage

## Boundaries

- Do not modify `_version.py`
- Internal components (JWKSClient, TokenValidator, AuthFastapiConfigurer, DefaultRoleResolver) are NOT in `__all__`
- No direct dependency on pico-boot (uses entry point for auto-discovery)
