# Configuration

This module defines the settings for pico-client-auth's JWT authentication:

- `AuthClientSettings`: a dataclass that carries auth configuration (issuer, audience, JWKS TTL) and is populated from configuration sources via pico-ioc's `@configured` decorator.

## AuthClientSettings

What it is:
- A `@configured` dataclass loaded from the `auth_client` config prefix.
- Automatically populated from configuration sources (YAML, env, dict).

Fields:
- `enabled: bool` — Enable or disable the auth middleware. Default: `True`.
- `issuer: str` — Expected JWT issuer (`iss` claim). Required when enabled.
- `audience: str` — Expected JWT audience (`aud` claim). Required when enabled.
- `jwks_ttl_seconds: int` — How long to cache the JWKS key set. Default: `300`.
- `jwks_endpoint: str` — URL to fetch JWKS from. Default: `{issuer}/api/v1/auth/jwks`.
- `accepted_algorithms: tuple[str, ...]` — JWT signing algorithms to accept. Default: `("RS256",)`. Add `"ML-DSA-65"` or `"ML-DSA-87"` for post-quantum support. Symmetric `HS*` algorithms are rejected even if listed here.
- `revocation_endpoint: str` — `jti` denylist URL to poll. Default: `""` (revocation disabled). Must be `https` (`http` allowed for localhost only).
- `revocation_ttl_seconds: int` — Poll interval, and the worst-case window between a revocation and validators honouring it. Default: `15`.
- `revocation_bearer: str` — Bearer token for the revocation endpoint when it is gated. Default: `""`.
- `revocation_fail_open: bool` — When a denylist fetch fails, accept tokens instead of rejecting them. Default: `False` (fail closed).

How to use:
- Provide a configuration source with an `auth_client` prefix when initializing the container.
- `AuthClientSettings` is automatically populated and injected into the auth components.

Example:
```yaml
# application.yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
  jwks_ttl_seconds: 600
```

```python
from pico_boot import init
from pico_ioc import configuration, YamlTreeSource
from fastapi import FastAPI

config = configuration(YamlTreeSource("application.yaml"))
container = init(modules=["myapp"], config=config)
app = container.get(FastAPI)

# Auth middleware is automatically configured
```

## Fail-Fast Validation

When `enabled` is `True` (the default), the `AuthFastapiConfigurer` validates at startup:

- `issuer` must be non-empty
- `audience` must be non-empty

If either is missing, `AuthConfigurationError` is raised immediately. This prevents deploying an application with broken authentication.

```python
from pico_client_auth.errors import AuthConfigurationError

# This will raise at container startup:
# auth_client:
#   enabled: true
#   issuer: ""         # Empty!
#   audience: "my-api"
```

## Disabling Auth

Set `enabled: false` to skip the auth middleware entirely. Useful for development or internal services:

```yaml
auth_client:
  enabled: false
```

When disabled, no middleware is registered. All routes are accessible without tokens.

## Accepted Algorithms

By default only RS256 is accepted. To enable post-quantum ML-DSA verification, add the algorithms to `accepted_algorithms`:

```yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
  accepted_algorithms:
    - RS256
    - ML-DSA-65
    - ML-DSA-87
```

Tokens with algorithms not in this list are rejected with `TokenInvalidError`. ML-DSA requires the `pqc` extra (`pip install pico-client-auth[pqc]`).

## Custom JWKS Endpoint

By default, the JWKS endpoint is derived from the issuer:

```
{issuer}/api/v1/auth/jwks
```

Override it for non-standard auth servers:

```yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
  jwks_endpoint: https://auth.example.com/.well-known/jwks.json
```

---

## Auto-generated API

::: pico_client_auth.config
