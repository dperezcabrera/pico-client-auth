"""Local cache of the issuer's ``jti`` denylist.

Backs the no-time-expiry policy: tokens are valid until either
the issuer's signing keys rotate (handled by ``JWKSClient``) or
their ``jti`` lands on the denylist (handled here). See
``feedback_no_time_expiry.md`` in the fleet memory store.

Polling, not push: validators poll
``GET /api/v1/auth/revoked-jtis`` every
``revocation_ttl_seconds``. The window between revoke and
rejection is bounded by that TTL — default 15s. For instant
fleet-wide invalidation, the operator rotates the JWKS instead.

Disabled by default: if ``revocation_endpoint`` is empty in
settings the cache is a no-op and ``is_revoked()`` always
returns False. Lets deployments opt in gradually.
"""

from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse

import httpx
from pico_ioc import component

from .config import AuthClientSettings

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def _require_https(url: str) -> None:
    """Reject plaintext http:// endpoints (the bearer token / denylist must
    travel over TLS). Exception: localhost / 127.0.0.1 / ::1 over http for dev.
    """
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS:
        return
    raise ValueError(
        f"Insecure revocation endpoint scheme for {url!r}: only https is allowed "
        "(http permitted for localhost/127.0.0.1 only)"
    )


@component
class RevocationCache:
    def __init__(self, settings: AuthClientSettings):
        self._settings = settings
        self._revoked: set[str] = set()
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()
        # Tracks whether the most recent fetch attempt succeeded. Drives
        # fail-closed behaviour in is_revoked() when a fetch errors out.
        self._last_fetch_ok: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self._settings.revocation_endpoint)

    def _is_expired(self) -> bool:
        ttl = max(1, int(self._settings.revocation_ttl_seconds))
        return (time.monotonic() - self._fetched_at) >= ttl

    async def _fetch(self) -> None:
        if not self.enabled:
            return
        logger.debug(
            "Fetching revocation denylist from %s",
            self._settings.revocation_endpoint,
        )
        # SECURITY: require TLS for the revocation endpoint (carries a bearer token).
        _require_https(self._settings.revocation_endpoint)
        headers = {}
        if self._settings.revocation_bearer:
            headers["Authorization"] = f"Bearer {self._settings.revocation_bearer}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    self._settings.revocation_endpoint,
                    headers=headers,
                )
                r.raise_for_status()
                data = r.json()
        except Exception as exc:  # noqa: BLE001
            # SECURITY: fetch error. Mark the fetch as failed so is_revoked()
            # can fail closed by default (treat as unable-to-confirm). The
            # legacy fail-open behaviour (serve a stale denylist) is opt-in via
            # ``revocation_fail_open``.
            self._last_fetch_ok = False
            logger.warning(
                "revocation cache fetch failed: %s",
                exc,
            )
            self._fetched_at = time.monotonic()
            return
        items = data.get("items", []) or []
        self._revoked = {str(it.get("jti", "")) for it in items if it.get("jti")}
        self._fetched_at = time.monotonic()
        self._last_fetch_ok = True
        logger.debug(
            "revocation cache refreshed: %d entries",
            len(self._revoked),
        )

    async def is_revoked(self, jti: str) -> bool:
        """Return True iff this jti is on the denylist.

        Refreshes the cache on TTL expiry. Tokens with no jti
        claim are always considered "not revoked" — pre-policy
        tokens stay valid (until JWKS rotation), and anyone
        passing a bare token without a jti can't be selectively
        targeted anyway.
        """
        if not self.enabled or not jti:
            return False
        if self._is_expired():
            async with self._lock:
                if self._is_expired():
                    await self._fetch()
        if jti in self._revoked:
            return True
        # SECURITY: if the last fetch failed we cannot confirm the token is NOT
        # revoked. Fail closed by default (report revoked); fail-open is opt-in.
        if not self._last_fetch_ok and not self._settings.revocation_fail_open:
            logger.warning(
                "revocation status unknown (fetch failed); failing closed for jti=%s",
                jti,
            )
            return True
        return False

    async def force_refresh(self) -> None:
        """Forces an immediate re-poll regardless of TTL. Used by
        retry paths after a 401/403 — same lazy-invalidation
        pattern as JWKSClient."""
        async with self._lock:
            await self._fetch()
