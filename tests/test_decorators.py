"""Tests for @allow_anonymous and @requires_role decorators."""

from pico_client_auth.decorators import (
    PICO_ALLOW_ANONYMOUS,
    PICO_REQUIRED_ROLES,
    allow_anonymous,
    requires_role,
)


def test_allow_anonymous_sets_attribute():
    @allow_anonymous
    def my_handler():
        pass

    assert getattr(my_handler, PICO_ALLOW_ANONYMOUS) is True


def test_allow_anonymous_returns_same_function():
    def my_handler():
        pass

    result = allow_anonymous(my_handler)
    assert result is my_handler


def test_requires_role_sets_frozenset():
    @requires_role("admin", "superuser")
    def my_handler():
        pass

    roles = getattr(my_handler, PICO_REQUIRED_ROLES)
    assert roles == frozenset({"admin", "superuser"})


def test_requires_role_single():
    @requires_role("editor")
    def my_handler():
        pass

    roles = getattr(my_handler, PICO_REQUIRED_ROLES)
    assert roles == frozenset({"editor"})


def test_requires_role_returns_same_function():
    def my_handler():
        pass

    result = requires_role("admin")(my_handler)
    assert result is my_handler


def test_no_decorator_has_no_attributes():
    def my_handler():
        pass

    assert not hasattr(my_handler, PICO_ALLOW_ANONYMOUS)
    assert not hasattr(my_handler, PICO_REQUIRED_ROLES)
