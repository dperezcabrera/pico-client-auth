"""JWT token validation using JWKS."""

import base64
import json
import logging

from jose import ExpiredSignatureError, JWTError, jwt
from pico_ioc import component

from . import pqc_jwt
from .config import AuthClientSettings
from .errors import TokenExpiredError, TokenInvalidError
from .jwks_client import JWKSClient
from .models import TokenClaims

logger = logging.getLogger(__name__)

_PQC_ALGORITHMS = ("ML-DSA-65", "ML-DSA-87")


def _get_unverified_headers(token: str) -> dict:
    """Decode JWT header without any library dependency on algorithm support."""
    try:
        header_b64 = token.split(".")[0]
        padded = header_b64 + "=" * (4 - len(header_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return {}


@component
class TokenValidator:
    """Decodes and validates JWT tokens using keys from :class:`JWKSClient`.

    Validates the signature, issuer, audience, and expiration.
    Supports RS256 and ML-DSA post-quantum algorithms.
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
        headers = _get_unverified_headers(token)
        alg = headers.get("alg", "RS256")

        if alg not in self._settings.accepted_algorithms:
            raise TokenInvalidError(f"Algorithm '{alg}' is not accepted")

        if alg in _PQC_ALGORITHMS:
            raw_claims = await self._validate_pqc(token, headers, alg)
        else:
            raw_claims = await self._validate_rsa(token, headers)

        claims = TokenClaims(
            sub=raw_claims.get("sub", ""),
            email=raw_claims.get("email", ""),
            role=raw_claims.get("role", ""),
            org_id=raw_claims.get("org_id", ""),
            jti=raw_claims.get("jti", ""),
            groups=tuple(raw_claims.get("groups", [])),
        )
        return claims, raw_claims

    async def _validate_rsa(self, token: str, headers: dict) -> dict:
        """Validate an RS256 JWT using python-jose."""
        try:
            kid = headers.get("kid", "")
            key = await self._jwks_client.get_key(kid)

            return jwt.decode(
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

    async def _validate_pqc(self, token: str, headers: dict, alg: str) -> dict:
        """Validate an ML-DSA JWT using liboqs."""
        try:
            kid = headers.get("kid", "")
            jwk = await self._jwks_client.get_key(kid)
        except KeyError as exc:
            raise TokenInvalidError(f"Invalid token: {exc}") from exc

        pub_b64 = jwk.get("pub", "")
        if not pub_b64:
            raise TokenInvalidError("JWK missing 'pub' field for ML-DSA key")

        padded = pub_b64 + "=" * (4 - len(pub_b64) % 4)
        public_key_bytes = base64.urlsafe_b64decode(padded)

        return pqc_jwt.decode_and_verify(
            token,
            public_key_bytes,
            alg,
            self._settings.issuer,
            self._settings.audience,
        )
