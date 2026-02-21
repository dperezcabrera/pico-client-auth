"""Thread/task-local security context (Spring SecurityContextHolder pattern)."""

from contextvars import ContextVar
from typing import Optional

from .errors import InsufficientPermissionsError, MissingTokenError
from .models import TokenClaims

_claims_var: ContextVar[Optional[TokenClaims]] = ContextVar("_pico_auth_claims", default=None)
_roles_var: ContextVar[list[str]] = ContextVar("_pico_auth_roles", default=[])
_groups_var: ContextVar[tuple[str, ...]] = ContextVar("_pico_auth_groups", default=())


class SecurityContext:
    """Singleton-style accessor for the current request's authentication state.

    All methods are static; the underlying storage uses ``ContextVar`` so
    each async task / thread has its own isolated copy.
    """

    @staticmethod
    def get() -> Optional[TokenClaims]:
        """Return the current claims, or ``None`` if not authenticated."""
        return _claims_var.get()

    @staticmethod
    def require() -> TokenClaims:
        """Return the current claims, raising if not authenticated.

        Raises:
            MissingTokenError: If no authentication context is set.
        """
        claims = _claims_var.get()
        if claims is None:
            raise MissingTokenError("No authenticated user in SecurityContext")
        return claims

    @staticmethod
    def get_roles() -> list[str]:
        """Return the resolved roles for the current request."""
        return list(_roles_var.get())

    @staticmethod
    def has_role(role: str) -> bool:
        """Check whether the current user has the given role."""
        return role in _roles_var.get()

    @staticmethod
    def require_role(*roles: str) -> None:
        """Assert that the current user has at least one of the given roles.

        Raises:
            InsufficientPermissionsError: If none of the roles match.
        """
        current = set(_roles_var.get())
        if not current.intersection(roles):
            raise InsufficientPermissionsError(f"Required one of {roles}, but user has {sorted(current)}")

    @staticmethod
    def get_groups() -> tuple[str, ...]:
        """Return the group IDs for the current request."""
        return _groups_var.get()

    @staticmethod
    def has_group(group_id: str) -> bool:
        """Check whether the current user belongs to the given group."""
        return group_id in _groups_var.get()

    @staticmethod
    def require_group(*group_ids: str) -> None:
        """Assert that the current user belongs to at least one of the given groups.

        Raises:
            InsufficientPermissionsError: If none of the groups match.
        """
        current = set(_groups_var.get())
        if not current.intersection(group_ids):
            raise InsufficientPermissionsError(f"Required one of groups {group_ids}, but user has {sorted(current)}")

    @staticmethod
    def set(claims: TokenClaims, roles: list[str]) -> None:
        """Populate the security context (called by the middleware)."""
        _claims_var.set(claims)
        _roles_var.set(roles)
        _groups_var.set(claims.groups)

    @staticmethod
    def clear() -> None:
        """Clear the security context (called by the middleware in ``finally``)."""
        _claims_var.set(None)
        _roles_var.set([])
        _groups_var.set(())
