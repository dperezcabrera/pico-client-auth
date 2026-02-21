"""Data models for pico-client-auth."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenClaims:
    """Immutable representation of the essential JWT claims.

    Attributes:
        sub: Subject identifier (user ID).
        email: User email address.
        role: Primary role claim from the token.
        org_id: Organisation identifier.
        jti: Unique token identifier (JWT ID).
    """

    sub: str
    email: str
    role: str
    org_id: str
    jti: str
    groups: tuple[str, ...] = ()
