"""Scope-based authorization decorator.

Companion to `@requires_role` / `@requires_group`. Where roles/groups
attach to the SERVICE token (the HTTP caller's identity), scopes
attach to the AGENT token (`X-Agent-Authorization`). The middleware
validates the agent JWT and checks that at least one declared scope
intersects the endpoint's required set.

Wildcards: scope matching is a simple ``:``-segmented glob. The
required scope ``"treasury:*"`` matches the agent scope
``"treasury:write:budget:opex"`` (left-to-right segment match, ``*``
is a wildcard for the remainder). Exact matches always win.

Why scopes instead of more roles?
  - Roles are coarse, identity-bound, infrequently rotated.
  - Scopes are fine, task-bound, rotate per delegation. The same
    agent can run different tasks with different scopes; encoding
    that in roles would explode the role taxonomy.
"""

from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

PICO_REQUIRED_SCOPES = "_pico_required_scopes"


def requires_scope(*scopes: str) -> Callable[[F], F]:
    """Mark an endpoint as requiring at least one of the given scopes
    on the agent token (X-Agent-Authorization).

    Args:
        *scopes: One or more scope strings. The agent must declare at
                 least one matching scope (exact or via wildcard
                 expansion — see `scope_matches`).

    Example::

        @controller(prefix="/api/v1/internal/treasury")
        class TreasuryController:
            @post("/budget/draft")
            @requires_role("treasury_writer")
            @requires_scope("treasury:write:budget:opex")
            async def draft_budget(self, body: dict): ...
    """

    def decorator(fn: F) -> F:
        setattr(fn, PICO_REQUIRED_SCOPES, frozenset(scopes))
        return fn

    return decorator


def scope_matches(granted: str, required: str) -> bool:
    """Return True if `granted` satisfies `required`.

    Match rules:
      - Exact: ``a:b:c`` matches ``a:b:c``.
      - Wildcard (right edge): ``a:b:*`` matches ``a:b:c`` and
        ``a:b:c:d`` (anything under the prefix), but NOT ``a:b``.
      - Wildcard (sole): ``*`` matches anything.
      - Mid-segment wildcards (``a:*:c``) are NOT supported — keep
        the matcher simple and predictable.
    """
    if granted == required:
        return True
    if granted == "*":
        return True
    if granted.endswith(":*"):
        prefix = granted[:-2]
        return required == prefix or required.startswith(prefix + ":")
    return False


def any_scope_matches(granted_scopes, required_scopes) -> bool:
    """Return True if ANY granted scope matches ANY required scope.

    `granted_scopes` is the set declared by the agent's JWT.
    `required_scopes` is the set declared by `@requires_scope`."""
    for r in required_scopes:
        for g in granted_scopes:
            if scope_matches(g, r):
                return True
    return False
