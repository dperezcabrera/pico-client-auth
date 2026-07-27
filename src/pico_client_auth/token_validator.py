"""JWT token validation using JWKS."""

import base64
import json
import logging

import jwt
from jwt import ExpiredSignatureError, PyJWTError
from pico_ioc import component

from . import pqc_jwt
from .config import AuthClientSettings
from .errors import TokenExpiredError, TokenInvalidError
from .jwks_client import JWKSClient
from .models import TokenClaims
from .revocation_cache import RevocationCache

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

    def __init__(
        self,
        settings: AuthClientSettings,
        jwks_client: JWKSClient,
        revocation_cache: RevocationCache,
    ):
        self._settings = settings
        self._jwks_client = jwks_client
        self._revocations = revocation_cache

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

        # SECURITY: hard-reject symmetric HS* algorithms regardless of the
        # accepted_algorithms config. This validator only uses asymmetric
        # JWK/public keys, so an HS* token would imply an HS/RS confusion
        # attack (signing with the public key as the HMAC secret).
        if alg.upper().startswith("HS"):
            raise TokenInvalidError(f"Symmetric algorithm '{alg}' is not permitted")

        if alg not in self._settings.accepted_algorithms:
            raise TokenInvalidError(f"Algorithm '{alg}' is not accepted")

        if alg in _PQC_ALGORITHMS:
            raw_claims = await self._validate_pqc(token, headers, alg)
        else:
            raw_claims = await self._validate_rsa(token, headers)

        # Denylist check after signature passes — cheap O(1)
        # set lookup against the locally-cached jti list.
        # Disabled when ``revocation_endpoint`` isn't configured
        # (default for setups that haven't opted in).
        jti = str(raw_claims.get("jti", ""))
        if jti and await self._revocations.is_revoked(jti):
            raise TokenInvalidError(
                f"Token revoked (jti={jti})",
            )

        claims = TokenClaims(
            sub=raw_claims.get("sub", ""),
            email=raw_claims.get("email", ""),
            role=raw_claims.get("role", ""),
            org_id=raw_claims.get("org_id", ""),
            jti=jti,
            groups=tuple(raw_claims.get("groups", [])),
        )
        return claims, raw_claims

    async def _validate_rsa(self, token: str, headers: dict) -> dict:
        """Validate a JWT using PyJWT (classical algorithms)."""
        try:
            kid = headers.get("kid", "")
            key = await self._jwks_client.get_key(kid)
            # SECURITY: This is the asymmetric JWK/public-key path. Symmetric
            # HS* algorithms are hard-rejected regardless of accepted_algorithms
            # config to prevent HS/RS confusion attacks (an attacker signing an
            # HS256 token using the public key as the HMAC secret).
            jose_algorithms = [
                a
                for a in self._settings.accepted_algorithms
                if a not in _PQC_ALGORITHMS and not a.upper().startswith("HS")
            ]

            return jwt.decode(
                token,
                jwt.PyJWK(dict(key)),
                algorithms=jose_algorithms,
                audience=self._settings.audience,
                issuer=self._settings.issuer,
                # SECURITY: reject tokens that omit `exp` so they cannot live forever.
                options={"require": ["exp"]},
            )
        except ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired") from exc
        except (PyJWTError, KeyError) as exc:
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
