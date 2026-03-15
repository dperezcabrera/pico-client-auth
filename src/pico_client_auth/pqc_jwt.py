"""ML-DSA (post-quantum) JWT decode and verification.

Provides custom JWT verification for ML-DSA-65 and ML-DSA-87 signatures,
since python-jose does not support post-quantum algorithms.

Requires the ``liboqs-python`` package (install via the ``pqc`` extra).
"""

import base64
import json
import time

from .errors import AuthConfigurationError, TokenExpiredError, TokenInvalidError

_SUPPORTED_ALGORITHMS = ("ML-DSA-65", "ML-DSA-87")


def _b64url_decode(data: str) -> bytes:
    """Decode a base64url-encoded string (with or without padding)."""
    padded = data + "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def _import_oqs():
    """Lazy-import oqs, raising AuthConfigurationError if not installed."""
    try:
        import oqs
    except ImportError as exc:
        raise AuthConfigurationError(
            "liboqs-python is required for ML-DSA verification. "
            "Install it with: pip install pico-client-auth[pqc]"
        ) from exc
    return oqs


def _split_token(token: str) -> tuple[str, str, str]:
    """Split a JWT into its three base64url parts."""
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenInvalidError("Malformed JWT: expected 3 parts")
    return parts[0], parts[1], parts[2]


def _decode_json_part(b64_data: str, label: str) -> dict:
    """Base64url-decode and JSON-parse a JWT segment."""
    try:
        return json.loads(_b64url_decode(b64_data))
    except Exception as exc:
        raise TokenInvalidError(f"Invalid JWT {label}: {exc}") from exc


def _verify_signature(oqs, algorithm: str, signing_input: bytes, signature: bytes, public_key_bytes: bytes) -> None:
    """Verify an ML-DSA signature, raising on failure."""
    verifier = oqs.Signature(algorithm)
    try:
        is_valid = verifier.verify(signing_input, signature, public_key_bytes)
    except Exception as exc:
        raise TokenInvalidError(f"Signature verification failed: {exc}") from exc
    if not is_valid:
        raise TokenInvalidError("Invalid signature")


def _validate_claims(claims: dict, issuer: str, audience: str) -> None:
    """Validate exp, iss, and aud claims."""
    exp = claims.get("exp")
    if exp is not None and time.time() > exp:
        raise TokenExpiredError("Token has expired")

    if claims.get("iss") != issuer:
        raise TokenInvalidError(f"Invalid issuer: expected {issuer}, got {claims.get('iss')}")

    token_aud = claims.get("aud")
    if isinstance(token_aud, list):
        if audience not in token_aud:
            raise TokenInvalidError(f"Invalid audience: {audience} not in {token_aud}")
    elif token_aud != audience:
        raise TokenInvalidError(f"Invalid audience: expected {audience}, got {token_aud}")


def decode_and_verify(
    token: str,
    public_key_bytes: bytes,
    algorithm: str,
    issuer: str,
    audience: str,
) -> dict:
    """Decode and verify an ML-DSA signed JWT.

    Args:
        token: The raw JWT string (``header.payload.signature``).
        public_key_bytes: Raw public key bytes for the ML-DSA algorithm.
        algorithm: ``"ML-DSA-65"`` or ``"ML-DSA-87"``.
        issuer: Expected ``iss`` claim value.
        audience: Expected ``aud`` claim value.

    Returns:
        The decoded claims dictionary.

    Raises:
        TokenInvalidError: If the token is malformed, has a bad signature,
            or fails issuer/audience validation.
        TokenExpiredError: If the token has expired.
        AuthConfigurationError: If liboqs-python is not installed.
    """
    if algorithm not in _SUPPORTED_ALGORITHMS:
        raise TokenInvalidError(f"Unsupported PQC algorithm: {algorithm}")

    oqs = _import_oqs()
    header_b64, payload_b64, signature_b64 = _split_token(token)

    header = _decode_json_part(header_b64, "header")
    if header.get("alg") != algorithm:
        raise TokenInvalidError(f"Algorithm mismatch: expected {algorithm}, got {header.get('alg')}")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    _verify_signature(oqs, algorithm, signing_input, _b64url_decode(signature_b64), public_key_bytes)

    claims = _decode_json_part(payload_b64, "payload")
    _validate_claims(claims, issuer, audience)
    return claims
