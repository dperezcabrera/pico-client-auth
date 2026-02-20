"""Tests for DefaultRoleResolver."""

import pytest

from pico_client_auth.models import TokenClaims
from pico_client_auth.role_resolver import DefaultRoleResolver, RoleResolver


@pytest.fixture
def resolver():
    return DefaultRoleResolver()


def _claims(role="admin"):
    return TokenClaims(sub="u1", email="a@b.com", role=role, org_id="o1", jti="j1")


class TestDefaultRoleResolver:
    @pytest.mark.asyncio
    async def test_returns_role_as_list(self, resolver):
        roles = await resolver.resolve(_claims("editor"), {})
        assert roles == ["editor"]

    @pytest.mark.asyncio
    async def test_empty_role_returns_empty_list(self, resolver):
        roles = await resolver.resolve(_claims(""), {})
        assert roles == []

    @pytest.mark.asyncio
    async def test_implements_protocol(self, resolver):
        assert isinstance(resolver, RoleResolver)


class TestCustomRoleResolver:
    @pytest.mark.asyncio
    async def test_custom_resolver_from_raw_claims(self):
        class MultiRoleResolver:
            async def resolve(self, claims: TokenClaims, raw_claims: dict) -> list[str]:
                return raw_claims.get("roles", [])

        resolver = MultiRoleResolver()
        assert isinstance(resolver, RoleResolver)
        roles = await resolver.resolve(_claims(), {"roles": ["admin", "editor", "viewer"]})
        assert roles == ["admin", "editor", "viewer"]
