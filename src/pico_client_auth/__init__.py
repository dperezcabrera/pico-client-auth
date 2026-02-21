"""pico-client-auth: JWT authentication client for pico-fastapi.

Provides automatic Bearer token validation, a request-scoped SecurityContext,
role-based access control decorators, and JWKS key rotation support.

Public API:
    Models: TokenClaims
    Context: SecurityContext
    Decorators: allow_anonymous, requires_role
    Protocols: RoleResolver
    Configuration: AuthClientSettings
    Errors: AuthClientError, MissingTokenError, TokenExpiredError,
            TokenInvalidError, InsufficientPermissionsError,
            AuthConfigurationError
"""

from .config import AuthClientSettings
from .decorators import allow_anonymous, requires_group, requires_role
from .errors import (
    AuthClientError,
    AuthConfigurationError,
    InsufficientPermissionsError,
    MissingTokenError,
    TokenExpiredError,
    TokenInvalidError,
)
from .models import TokenClaims
from .role_resolver import RoleResolver
from .security_context import SecurityContext

__all__ = [
    "SecurityContext",
    "TokenClaims",
    "allow_anonymous",
    "requires_group",
    "requires_role",
    "RoleResolver",
    "AuthClientSettings",
    "AuthClientError",
    "MissingTokenError",
    "TokenExpiredError",
    "TokenInvalidError",
    "InsufficientPermissionsError",
    "AuthConfigurationError",
]
