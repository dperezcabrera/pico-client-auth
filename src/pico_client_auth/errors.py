"""Authentication error hierarchy for pico-client-auth."""


class AuthClientError(Exception):
    """Base error for all pico-client-auth exceptions."""


class MissingTokenError(AuthClientError):
    """No Bearer token found in the Authorization header."""


class TokenExpiredError(AuthClientError):
    """The JWT token has expired."""


class TokenInvalidError(AuthClientError):
    """The JWT token is malformed or has an invalid signature."""


class InsufficientPermissionsError(AuthClientError):
    """The authenticated user lacks the required role(s)."""


class AuthConfigurationError(AuthClientError):
    """Authentication configuration is missing or invalid."""
