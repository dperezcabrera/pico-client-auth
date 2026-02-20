"""Route-level authentication decorators for pico-client-auth."""

from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

PICO_ALLOW_ANONYMOUS = "_pico_allow_anonymous"
PICO_REQUIRED_ROLES = "_pico_required_roles"


def allow_anonymous(fn: F) -> F:
    """Mark an endpoint as accessible without authentication.

    When applied to a controller method, the auth middleware will skip
    token validation for that route.
    """
    setattr(fn, PICO_ALLOW_ANONYMOUS, True)
    return fn


def requires_role(*roles: str) -> Callable[[F], F]:
    """Require the authenticated user to have at least one of the specified roles.

    Args:
        *roles: One or more role names. The user must have at least one.

    Returns:
        A decorator that attaches role metadata to the endpoint.
    """

    def decorator(fn: F) -> F:
        setattr(fn, PICO_REQUIRED_ROLES, frozenset(roles))
        return fn

    return decorator
