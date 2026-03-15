# Changelog

All notable changes to **pico-client-auth** will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).

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
