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
