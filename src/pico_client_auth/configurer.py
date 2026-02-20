"""FastAPI configurer that registers the authentication middleware."""

import logging

from fastapi import FastAPI, Request
from pico_ioc import component
from starlette.responses import JSONResponse
from starlette.routing import Match

from .config import AuthClientSettings
from .decorators import PICO_ALLOW_ANONYMOUS, PICO_REQUIRED_ROLES
from .errors import (
    AuthClientError,
    AuthConfigurationError,
    TokenExpiredError,
    TokenInvalidError,
)
from .role_resolver import RoleResolver
from .security_context import SecurityContext
from .token_validator import TokenValidator

logger = logging.getLogger(__name__)


def _find_endpoint(app: FastAPI, scope: dict):
    """Resolve the route endpoint function for the given ASGI scope.

    Walks the app's routes and returns the first matching endpoint,
    or ``None`` if no route matches.
    """
    for route in app.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "endpoint", None)
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

            # Extract Bearer token
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse({"detail": "Missing or invalid Authorization header"}, status_code=401)

            raw_token = auth_header[7:]

            try:
                claims, raw_claims = await token_validator.validate(raw_token)
                roles = await role_resolver.resolve(claims, raw_claims)
                SecurityContext.set(claims, roles)

                # Check @requires_role
                required_roles = getattr(endpoint, PICO_REQUIRED_ROLES, None) if endpoint else None
                if required_roles and not set(roles).intersection(required_roles):
                    return JSONResponse(
                        {"detail": f"Requires one of roles: {sorted(required_roles)}"},
                        status_code=403,
                    )

                return await call_next(request)
            except TokenExpiredError:
                return JSONResponse({"detail": "Token has expired"}, status_code=401)
            except (TokenInvalidError, AuthClientError) as exc:
                return JSONResponse({"detail": str(exc)}, status_code=401)
            finally:
                SecurityContext.clear()
