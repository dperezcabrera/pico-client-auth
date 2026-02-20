"""Role resolution protocol and default implementation."""

from typing import Protocol, runtime_checkable

from pico_ioc import component

from .models import TokenClaims


@runtime_checkable
class RoleResolver(Protocol):
    """Protocol for resolving user roles from JWT claims.

    Implement this protocol to customise how roles are extracted
    (e.g. from a ``roles`` array claim, from an external service, etc.).
    Register your implementation as a ``@component`` and it will
    automatically replace the default resolver.
    """

    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]: ...


@component(on_missing_selector=RoleResolver)
class DefaultRoleResolver:
    """Default role resolver that returns the single ``role`` claim as a list.

    This is registered as a fallback (``on_missing_selector``) so that
    applications can override it by providing their own ``RoleResolver``
    component.
    """

    async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
        return [claims.role] if claims.role else []
