"""FastAPI configurer that registers the authentication middleware."""

import logging

from fastapi import FastAPI, Request
from pico_ioc import component
from starlette.responses import JSONResponse
from starlette.routing import Match

from .agent_context import AgentClaims, AgentContext
from .config import AuthClientSettings
from .decorators import PICO_ALLOW_ANONYMOUS, PICO_REQUIRED_GROUPS, PICO_REQUIRED_ROLES
from .errors import (
    AuthClientError,
    AuthConfigurationError,
    TokenExpiredError,
    TokenInvalidError,
)
from .role_resolver import RoleResolver
from .scope import PICO_REQUIRED_SCOPES, any_scope_matches
from .security_context import SecurityContext
from .token_validator import TokenValidator

logger = logging.getLogger(__name__)


def _iter_leaf_routes(routes):
    """Yield endpoint-bearing routes, descending into nested routers.

    starlette >= 1.x wraps included routers (``_IncludedRouter``) so
    ``app.routes`` is no longer flat; walk ``routes`` /
    ``original_router.routes`` recursively to stay version-agnostic.
    """
    for route in routes:
        inner = getattr(route, "routes", None)
        if inner is None:
            inner = getattr(getattr(route, "original_router", None), "routes", None)
        if inner:
            yield from _iter_leaf_routes(inner)
        else:
            yield route


def _find_endpoint(app: FastAPI, scope: dict):
    """Resolve the route endpoint function for the given ASGI scope.

    Returns the first matching endpoint, or ``None`` if no route matches.
    """
    for route in _iter_leaf_routes(app.routes):
        try:
            match, _ = route.matches(scope)
        except Exception:  # noqa: BLE001 - a foreign route type must not break auth
            continue
        if match == Match.FULL:
            return getattr(route, "endpoint", None)
    return None


def _required_attr(endpoint, attr):
    """Read a pico decorator attribute off the resolved endpoint, if any."""
    return getattr(endpoint, attr, None) if endpoint else None


def _check_roles(endpoint, roles) -> JSONResponse | None:
    """403 if the endpoint declares @requires_role and the caller lacks it."""
    required_roles = _required_attr(endpoint, PICO_REQUIRED_ROLES)
    if required_roles and not set(roles).intersection(required_roles):
        return JSONResponse(
            {"detail": f"Requires one of roles: {sorted(required_roles)}"},
            status_code=403,
        )
    return None


def _check_groups(endpoint, claims) -> JSONResponse | None:
    """403 if the endpoint declares @requires_group and the caller lacks it."""
    required_groups = _required_attr(endpoint, PICO_REQUIRED_GROUPS)
    if required_groups and not set(claims.groups).intersection(required_groups):
        return JSONResponse(
            {"detail": f"Requires one of groups: {sorted(required_groups)}"},
            status_code=403,
        )
    return None


async def _authenticate_agent(request: Request, token_validator: TokenValidator) -> JSONResponse | None:
    """Validate the optional X-Agent-Authorization token and populate AgentContext.

    Returns an error response if an agent token is present but invalid;
    ``None`` when there is no agent token or it validated successfully.
    """
    agent_header = request.headers.get("x-agent-authorization", "")
    if not agent_header.startswith("Bearer "):
        return None
    agent_raw = agent_header[7:]
    try:
        _, agent_raw_claims = await token_validator.validate(agent_raw)
    except TokenExpiredError:
        return JSONResponse({"detail": "Agent token has expired"}, status_code=401)
    except (TokenInvalidError, AuthClientError) as exc:
        return JSONResponse({"detail": f"Invalid agent token: {exc}"}, status_code=401)
    AgentContext.set(AgentClaims.from_claims_dict(agent_raw_claims))
    return None


def _check_scopes(endpoint) -> JSONResponse | None:
    """Enforce @requires_scope against the agent identity in AgentContext."""
    required_scopes = _required_attr(endpoint, PICO_REQUIRED_SCOPES)
    if not required_scopes:
        return None
    agent = AgentContext.get()
    if agent is None:
        return JSONResponse(
            {"detail": "Endpoint requires X-Agent-Authorization header (agent token)"},
            status_code=401,
        )
    if not any_scope_matches(agent.scopes, required_scopes):
        return JSONResponse(
            {"detail": f"Agent missing required scope; required one of: {sorted(required_scopes)}"},
            status_code=403,
        )
    return None


@component
class AuthFastapiConfigurer:
    """Registers the authentication middleware on the FastAPI application.

    Implements the ``FastApiConfigurer`` protocol with ``priority = 10``
    so it runs as an inner middleware (after pico-ioc scope middleware).

    **Fail-fast**: if ``enabled=True`` but ``issuer`` or ``audience`` are
    empty, raises :class:`AuthConfigurationError` at startup.
    """

    priority = 10

    def __init__(
        self,
        settings: AuthClientSettings,
        token_validator: TokenValidator,
        role_resolver: RoleResolver,
    ):
        self._settings = settings
        self._token_validator = token_validator
        self._role_resolver = role_resolver

        if settings.enabled:
            if not settings.issuer:
                raise AuthConfigurationError("auth_client.issuer must be set when auth is enabled")
            if not settings.audience:
                raise AuthConfigurationError("auth_client.audience must be set when auth is enabled")

    def configure_app(self, app: FastAPI) -> None:
        """Register the auth middleware on the FastAPI app."""
        if not self._settings.enabled:
            logger.info("Auth client middleware is disabled")
            return

        token_validator = self._token_validator
        role_resolver = self._role_resolver

        @app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            endpoint = _find_endpoint(app, request.scope)

            # Check @allow_anonymous
            if endpoint and getattr(endpoint, PICO_ALLOW_ANONYMOUS, False):
                return await call_next(request)

            # Extract Bearer token (service identity)
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse({"detail": "Missing or invalid Authorization header"}, status_code=401)

            raw_token = auth_header[7:]

            try:
                claims, raw_claims = await token_validator.validate(raw_token)
                roles = await role_resolver.resolve(claims, raw_claims)
                SecurityContext.set(claims, roles)

                # Service-identity authorization: @requires_role / @requires_group
                for response in (_check_roles(endpoint, roles), _check_groups(endpoint, claims)):
                    if response is not None:
                        return response

                # Optional second token: agent identity (X-Agent-Authorization).
                # Validated with the same TokenValidator/JWKS as the service
                # token; required only when the endpoint declares @requires_scope.
                agent_error = await _authenticate_agent(request, token_validator)
                if agent_error is not None:
                    return agent_error

                scope_error = _check_scopes(endpoint)
                if scope_error is not None:
                    return scope_error

                return await call_next(request)
            except TokenExpiredError:
                return JSONResponse({"detail": "Token has expired"}, status_code=401)
            except (TokenInvalidError, AuthClientError) as exc:
                return JSONResponse({"detail": str(exc)}, status_code=401)
            finally:
                SecurityContext.clear()
                AgentContext.clear()
