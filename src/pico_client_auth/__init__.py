"""pico-client-auth: JWT authentication client for pico-fastapi.

Provides automatic Bearer token validation, a request-scoped SecurityContext,
role-based access control decorators, JWKS key rotation support, and
agentic identity propagation via X-Agent-Authorization + scope-based
authorization.

Public API:
    Models: TokenClaims, AgentClaims
    Contexts: SecurityContext, AgentContext
    Decorators: allow_anonymous, requires_role, requires_group, requires_scope
    Helpers: scope_matches, any_scope_matches
    Protocols: RoleResolver
    Configuration: AuthClientSettings
    Errors: AuthClientError, MissingTokenError, TokenExpiredError,
            TokenInvalidError, InsufficientPermissionsError,
            AuthConfigurationError
"""

from .agent_context import AgentClaims, AgentContext
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
from .scope import any_scope_matches, requires_scope, scope_matches
from .security_context import SecurityContext

__all__ = [
    "AgentClaims",
    "AgentContext",
    "SecurityContext",
    "TokenClaims",
    "allow_anonymous",
    "any_scope_matches",
    "requires_group",
    "requires_role",
    "requires_scope",
    "scope_matches",
    "RoleResolver",
    "AuthClientSettings",
    "AuthClientError",
    "MissingTokenError",
    "TokenExpiredError",
    "TokenInvalidError",
    "InsufficientPermissionsError",
    "AuthConfigurationError",
]
