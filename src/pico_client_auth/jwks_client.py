"""JWKS key set fetcher with TTL-based caching."""

import logging
import time
from urllib.parse import urlparse

import httpx
from pico_ioc import component

from .config import AuthClientSettings

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def _require_https(url: str) -> None:
    """Reject plaintext http:// endpoints (secrets/keys must travel over TLS).

    Exception: localhost / 127.0.0.1 / ::1 are allowed over http for local
    development.
    """
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS:
        return
    raise ValueError(
        f"Insecure endpoint scheme for {url!r}: only https is allowed "
        "(http permitted for localhost/127.0.0.1 only)"
    )


@component
class JWKSClient:
    """Fetches and caches the JSON Web Key Set from the auth server.

    Supports automatic cache refresh when a key ID (``kid``) is not found
    (handles key rotation) and TTL-based expiration.
    """

    def __init__(self, settings: AuthClientSettings):
        self._settings = settings
        self._keys: dict = {}
        self._fetched_at: float = 0.0
        self._endpoint = settings.jwks_endpoint or f"{settings.issuer.rstrip('/')}/api/v1/auth/jwks"

    def _is_expired(self) -> bool:
        return (time.monotonic() - self._fetched_at) >= self._settings.jwks_ttl_seconds

    async def _fetch_keys(self) -> None:
        logger.debug("Fetching JWKS from %s", self._endpoint)
        # SECURITY: require TLS (https) for the JWKS endpoint and bound the
        # request with a timeout so a hung server can't stall validation.
        _require_https(self._endpoint)
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self._endpoint)
            response.raise_for_status()
            data = response.json()
        self._keys = {k["kid"]: k for k in data.get("keys", [])}
        self._fetched_at = time.monotonic()

    async def get_key(self, kid: str) -> dict:
        """Return the JWK for the given key ID, fetching/refreshing as needed.

        Args:
            kid: The ``kid`` header value from the JWT.

        Returns:
            The JWK dict matching the requested key ID.

        Raises:
            KeyError: If the key ID is not found even after a refresh.
        """
        if self._is_expired() or not self._keys:
            await self._fetch_keys()

        if kid in self._keys:
            return self._keys[kid]

        # Key not found — might be key rotation, force refresh once
        await self._fetch_keys()
        if kid in self._keys:
            return self._keys[kid]

        raise KeyError(f"Key ID '{kid}' not found in JWKS")
