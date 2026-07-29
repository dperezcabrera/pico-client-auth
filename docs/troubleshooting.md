# Troubleshooting

## AuthConfigurationError at startup

`auth_client.issuer` and `auth_client.audience` are mandatory when auth is
enabled — the configurer fails fast rather than validating tokens against
nothing. In tests either provide them or set `auth_client.enabled: false`.

## Every request returns 401 with a valid-looking token

- `iss` and `aud` claims must match `auth_client.issuer` / `audience`
  exactly (scheme and trailing slashes included).
- The token's `kid` must exist in the issuer's JWKS; after a key rotation
  the client force-refreshes once on unknown kid — an old token signed with
  a retired key stays invalid.
- Check the clock skew between services if `exp`/`iat` validation fails.

## A revoked token keeps working for a few seconds

Expected: validators poll the denylist every `revocation_ttl_seconds`
(default 15). The window is bounded by that TTL; rotate the JWKS for
instant fleet-wide invalidation.

## Revocation checks never happen

The cache is disabled unless `auth_client.revocation_endpoint` is set —
opt-in by design. Note the fail-closed policy: if the denylist cannot be
fetched, tokens with a `jti` are rejected because their revocation status
cannot be confirmed. To keep the previous fail-open behavior (serve the
last known denylist and accept on unknown), set
`auth_client.revocation_fail_open: true`.

## @requires_role passes in tests when it should not

With `auth_client.enabled: false` the middleware never runs and role
decorators are not enforced. Enable auth and mint real tokens in the tests
that assert authorization (see the testing how-to).

## SecurityContext.require() raises outside a request

That is the contract: the context is bound per-request by the middleware.
Guard optional paths with `SecurityContext.current()` which returns None.
