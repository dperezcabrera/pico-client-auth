"""Configuration settings for pico-client-auth."""

from dataclasses import dataclass

from pico_ioc import configured


@configured(target="self", prefix="auth_client", mapping="tree")
@dataclass
class AuthClientSettings:
    """Type-safe settings for the auth client, loaded from configuration sources.

    Populated automatically from configuration sources using the ``auth_client``
    prefix via pico-ioc's ``@configured`` decorator.

    Attributes:
        enabled: Whether authentication middleware is active.
        issuer: Expected JWT issuer (``iss`` claim).
        audience: Expected JWT audience (``aud`` claim).
        jwks_ttl_seconds: How long to cache the JWKS key set (seconds).
        jwks_endpoint: URL to fetch JWKS from. Defaults to ``{issuer}/api/v1/auth/jwks``.
    """

    enabled: bool = True
    issuer: str = ""
    audience: str = ""
    jwks_ttl_seconds: int = 300
    jwks_endpoint: str = ""
    accepted_algorithms: tuple[str, ...] = ("RS256",)
    # ── Revocation denylist (jti) ────────────────────────────────
    # Endpoint the validator polls to refresh its local cache of
    # revoked JWT IDs. Empty disables the check entirely (back to
    # signature-only validation — safe default for setups that
    # haven't wired the issuer's revoke endpoint).
    # ``revocation_ttl_seconds`` is the worst-case window between
    # an operator clicking Revoke and validators actually
    # rejecting the token. Lower = snappier, higher = fewer
    # round-trips. JWKS rotation remains the instant-kill path.
    revocation_endpoint: str = ""
    revocation_ttl_seconds: int = 15
    # If the revocation endpoint requires a Bearer token (the
    # default — pico-server-auth gates it behind role=service),
    # the auth-client uses this token for the poll. Empty falls
    # back to anonymous (works for dev / unauthenticated setups).
    revocation_bearer: str = ""
