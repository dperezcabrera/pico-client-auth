"""JWT token validation using JWKS."""

import logging

from jose import ExpiredSignatureError, JWTError, jwt
from pico_ioc import component

from .config import AuthClientSettings
from .errors import TokenExpiredError, TokenInvalidError
from .jwks_client import JWKSClient
from .models import TokenClaims

logger = logging.getLogger(__name__)


@component
class TokenValidator:
    """Decodes and validates JWT tokens using keys from :class:`JWKSClient`.

    Validates the signature, issuer, audience, and expiration.
    """

    def __init__(self, settings: AuthClientSettings, jwks_client: JWKSClient):
        self._settings = settings
        self._jwks_client = jwks_client

    async def validate(self, token: str) -> tuple[TokenClaims, dict]:
        """Validate a JWT token and return structured claims.

        Args:
            token: The raw JWT string (without the ``Bearer `` prefix).

        Returns:
            A tuple of ``(TokenClaims, raw_claims_dict)``.

        Raises:
            TokenExpiredError: If the token has expired.
            TokenInvalidError: If the token is malformed, has a bad
                signature, or fails issuer/audience validation.
        """
        try:
            headers = jwt.get_unverified_headers(token)
            kid = headers.get("kid", "")
            key = await self._jwks_client.get_key(kid)

            raw_claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self._settings.audience,
                issuer=self._settings.issuer,
            )
        except ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired") from exc
        except (JWTError, KeyError) as exc:
            raise TokenInvalidError(f"Invalid token: {exc}") from exc

        claims = TokenClaims(
            sub=raw_claims.get("sub", ""),
            email=raw_claims.get("email", ""),
            role=raw_claims.get("role", ""),
            org_id=raw_claims.get("org_id", ""),
            jti=raw_claims.get("jti", ""),
        )
        return claims, raw_claims
