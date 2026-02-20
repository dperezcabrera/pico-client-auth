"""Tests for SecurityContext."""

import asyncio

import pytest

from pico_client_auth.errors import InsufficientPermissionsError, MissingTokenError
from pico_client_auth.models import TokenClaims
from pico_client_auth.security_context import SecurityContext


@pytest.fixture(autouse=True)
def _clean_context():
    """Ensure SecurityContext is clean before and after each test."""
    SecurityContext.clear()
    yield
    SecurityContext.clear()


def _make_claims(**overrides):
    defaults = dict(sub="u1", email="a@b.com", role="admin", org_id="o1", jti="j1")
    defaults.update(overrides)
    return TokenClaims(**defaults)


class TestGetAndSet:
    def test_get_returns_none_initially(self):
        assert SecurityContext.get() is None

    def test_set_and_get(self):
        claims = _make_claims()
        SecurityContext.set(claims, ["admin"])
        assert SecurityContext.get() is claims

    def test_clear(self):
        SecurityContext.set(_make_claims(), ["admin"])
        SecurityContext.clear()
        assert SecurityContext.get() is None
        assert SecurityContext.get_roles() == []


class TestRequire:
    def test_require_raises_when_empty(self):
        with pytest.raises(MissingTokenError):
            SecurityContext.require()

    def test_require_returns_claims(self):
        claims = _make_claims()
        SecurityContext.set(claims, [])
        assert SecurityContext.require() is claims


class TestRoles:
    def test_get_roles(self):
        SecurityContext.set(_make_claims(), ["admin", "editor"])
        assert SecurityContext.get_roles() == ["admin", "editor"]

    def test_get_roles_returns_copy(self):
        SecurityContext.set(_make_claims(), ["admin"])
        roles = SecurityContext.get_roles()
        roles.append("hacker")
        assert SecurityContext.get_roles() == ["admin"]

    def test_has_role_true(self):
        SecurityContext.set(_make_claims(), ["admin"])
        assert SecurityContext.has_role("admin") is True

    def test_has_role_false(self):
        SecurityContext.set(_make_claims(), ["admin"])
        assert SecurityContext.has_role("editor") is False

    def test_require_role_passes(self):
        SecurityContext.set(_make_claims(), ["admin", "editor"])
        SecurityContext.require_role("editor")  # should not raise

    def test_require_role_raises(self):
        SecurityContext.set(_make_claims(), ["viewer"])
        with pytest.raises(InsufficientPermissionsError):
            SecurityContext.require_role("admin", "editor")


class TestContextVarIsolation:
    @pytest.mark.asyncio
    async def test_isolation_between_tasks(self):
        """Each async task should have its own SecurityContext."""
        results = {}

        async def task_a():
            SecurityContext.set(_make_claims(sub="task-a"), ["a-role"])
            await asyncio.sleep(0.01)
            results["a"] = SecurityContext.get()

        async def task_b():
            SecurityContext.set(_make_claims(sub="task-b"), ["b-role"])
            await asyncio.sleep(0.01)
            results["b"] = SecurityContext.get()

        await asyncio.gather(asyncio.create_task(task_a()), asyncio.create_task(task_b()))
        assert results["a"].sub == "task-a"
        assert results["b"].sub == "task-b"
