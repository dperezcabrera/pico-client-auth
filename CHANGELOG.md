# Changelog

All notable changes to **pico-client-auth** will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Changed

- **Revocation cache fails closed by default**: when the denylist fetch fails, tokens with a `jti` are rejected instead of accepted, because revocation status cannot be confirmed. The previous fail-open behavior (serve a stale denylist and accept on unknown) is opt-in via `auth_client.revocation_fail_open: true`.
- Token validation hardened: `exp` is mandatory, symmetric `HS*` algorithms are rejected regardless of `accepted_algorithms` (RS/HS confusion defense), and the JWKS/revocation endpoints must use HTTPS (`http` allowed for localhost only).

### Added

- Security regression tests covering the HS* rejection, HTTPS-only endpoints and revoked-`jti` rejection.

## v0.5.0 — PyJWT Migration (2026-07-10)

### Changed

- JWT validation migrated from `python-jose` to `PyJWT[crypto]`. Tokens are wire-compatible; no configuration changes needed. Aligned with pico-server-auth 0.2.0 issuing through PyJWT.

## v0.4.3 — Docs & CI (2026-07-10)

### Changed

- Documentation raised to the fleet standard (docs QA at zero, AI-first `llms.txt`, flagship use case linked, emojis stripped).
- SonarCloud analysis runs from CI on main pushes.

## v0.4.2 — Agentic Identity & Scope Authorization (2026-06-07)

### Added

- **Agent identity (`X-Agent-Authorization`)** — a request may now carry a *second* JWT alongside the service token. The service token (`Authorization`) says *which service* is calling; the agent token (`X-Agent-Authorization`) says *which LLM agent is acting on behalf of which user, with what scopes and spend limits*. Both are validated through the same `TokenValidator`/JWKS.
- **`AgentContext` + `AgentClaims`** — request-scoped context (ContextVar-isolated) exposing the agent's `sub`, `scopes`, `user_id`, `spend_limit`, `parent_chain`, and raw claims. Cleared automatically at the end of each request.
- **`@requires_scope(...)` decorator + scope matching** — endpoint-level authorization against agent scopes, with `:`-segmented glob matching (`treasury:*` matches `treasury:write:budget:opex`). Helpers `scope_matches` / `any_scope_matches` are exported.
- **`RevocationCache`** — a local cache of the issuer's `jti` denylist. After signature validation, the validator rejects revoked tokens. Polls `revocation_endpoint` every `revocation_ttl_seconds`; **disabled by default** (empty endpoint → signature-only validation, unchanged behavior). JWKS rotation remains the instant-kill path.
- New config fields: `revocation_endpoint` (default `""`), `revocation_ttl_seconds` (default `15`), `revocation_bearer` (default `""`).

### Changed

- `TokenValidator` now performs a `jti` denylist check after signature verification (no-op unless `revocation_endpoint` is configured).
- Public API additions to `__init__.py`: `AgentClaims`, `AgentContext`, `requires_scope`, `scope_matches`, `any_scope_matches`.

### Compatibility

- **Backward-compatible.** Endpoints without `@requires_scope` ignore the agent header; with no `revocation_endpoint` configured, validation behaves exactly as in v0.4.1.

---

## v0.4.1 — Bug Fix & Test Coverage (2026-03-15)

### Fixed

- `TokenValidator._validate_rsa` now uses configured `accepted_algorithms` instead of hardcoded `["RS256"]`, so classical algorithms like RS384/RS512 are respected if configured

### Added

- `test_pqc_jwt_mock.py` — 23 unit tests for `pqc_jwt` with mocked oqs (no liboqs required)
- `TestPQCDispatchMocked` / `TestAlgorithmNotAccepted` in `test_token_validator.py` — PQC dispatch and algorithm rejection tests
- PQC code coverage raised from 16% to 98% without liboqs

### Changed

- Added `E402` to per-file test ignores in `pyproject.toml`

---

## v0.4.0 — Post-Quantum (ML-DSA) Support (2026-03-15)

### Added

- ML-DSA-65 and ML-DSA-87 post-quantum JWT signature verification via `liboqs-python`
- `pqc_jwt` module — custom JWT decode+verify for ML-DSA algorithms (python-jose does not support PQC)
- `accepted_algorithms` field in `AuthClientSettings` — restrict which JWT signing algorithms are accepted (default: `("RS256",)`)
- Algorithm dispatch in `TokenValidator` — routes ML-DSA tokens to `pqc_jwt`, RS256 tokens to python-jose
- `pqc` optional dependency extra (`pip install pico-client-auth[pqc]`)
- `Dockerfile.pqc-test` — Docker container with liboqs C library for PQC testing
- `pqc-build` / `pqc-test` Makefile targets
- `pqc-py{311..314}` tox test environments
- PQC test fixtures: `mldsa65_keypair`, `mldsa87_keypair`, `mldsa_jwk_dict`, `make_pqc_token`
- PQC tests gracefully skip when liboqs is not installed (`pytest.importorskip`)

---

## v0.3.0 — Groups Support (2026-02-21)

### Added

- `TokenClaims.groups` field — tuple of group IDs from the JWT `groups` claim
- `@requires_group("group-id")` decorator — endpoint-level group-based access control (403 if missing)
- `SecurityContext.get_groups()` — return the group IDs for the current request
- `SecurityContext.has_group(group_id)` — check whether the current user belongs to a group
- `SecurityContext.require_group(*group_ids)` — assert membership in at least one group
- Middleware enforcement of `@requires_group` — checked alongside `@requires_role`
- Docker E2E test infrastructure (`Dockerfile.test`, `Makefile`)

---

## v0.1.0 — Initial Release (2026-02-20)

### Added

- Automatic Bearer token validation via FastAPI middleware (`AuthFastapiConfigurer`, priority=10)
- `SecurityContext` — ContextVar-backed request-scoped accessor for authenticated user claims
- `@allow_anonymous` — decorator to skip authentication on specific endpoints
- `@requires_role("admin", "editor")` — decorator for role-based access control
- `JWKSClient` — JWKS fetcher with TTL-based cache and automatic key rotation support
- `TokenValidator` — RS256 JWT decode and validation (issuer, audience, expiration)
- `RoleResolver` protocol — pluggable role extraction with `DefaultRoleResolver` fallback
- `TokenClaims` — frozen dataclass with `sub`, `email`, `role`, `org_id`, `jti`
- Fail-fast startup — `AuthConfigurationError` if `issuer`/`audience` missing when enabled
- Error responses — JSON `{"detail": "..."}` with HTTP 401 (auth) or 403 (authz)
