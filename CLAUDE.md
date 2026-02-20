Read and follow ./AGENTS.md for project conventions.

## Pico Ecosystem Context

pico-client-auth provides JWT authentication for pico-fastapi apps. It uses:
- `@component`, `@configured` from pico-ioc
- `FastApiConfigurer` protocol from pico-fastapi (priority=10, inner middleware)
- `RoleResolver` protocol with `on_missing_selector` fallback pattern
- Auto-discovered via `pico_boot.modules` entry point

## Key Reminders

- pico-ioc dependency: `>= 2.2.0`
- **NEVER change `version_scheme`** in pyproject.toml. It MUST remain `"post-release"`.
- requires-python >= 3.11
- Commit messages: one line only
- SecurityContext uses ContextVar for async task isolation
- JWKSClient handles key rotation via force-refresh on unknown kid
- AuthFastapiConfigurer fail-fast: raises AuthConfigurationError if issuer/audience missing
