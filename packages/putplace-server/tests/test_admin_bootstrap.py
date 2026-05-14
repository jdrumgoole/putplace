"""Tests for the regstack-backed admin bootstrap (`ensure_admin_exists`)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from putplace_server.main import ensure_admin_exists
from putplace_server.regstack_integration import get_regstack


@pytest.fixture
async def _empty_regstack_users():
    """Drop the regstack user collection so each test starts from an empty state.

    The regstack singleton's mongo client is session-scoped, so users seeded by
    one test live until the worker session ends. These bootstrap tests assume
    "no users exist yet", so we wipe before each. We also re-run install_schema
    so the unique-email index is back in place (drop() takes the index with it)
    and to handle the case where the singleton was rebuilt mid-session (e.g.
    by ``test_lifespan_with_real_mongodb``) without going through the lifespan.
    """
    rs = get_regstack()
    db = rs.backend.client[rs.config.mongodb_database]
    await db[rs.config.user_collection].drop()
    await rs.install_schema()
    yield
    await db[rs.config.user_collection].drop()


@pytest.mark.asyncio
async def test_bootstrap_from_env_vars(_empty_regstack_users) -> None:
    with patch.dict(
        os.environ,
        {
            "PUTPLACE_ADMIN_PASSWORD": "securepass123",
            "PUTPLACE_ADMIN_EMAIL": "admin@putplace.example.com",
        },
    ):
        await ensure_admin_exists()

    rs = get_regstack()
    user = await rs.users.get_by_email("admin@putplace.example.com")
    assert user is not None
    assert user.is_superuser is True
    assert user.is_active is True
    assert user.is_verified is True
    assert rs.password_hasher.verify("securepass123", user.hashed_password) is True


@pytest.mark.asyncio
async def test_bootstrap_random_password_when_env_unset(_empty_regstack_users) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PUTPLACE_ADMIN_")}
    with patch.dict(os.environ, env, clear=True):
        await ensure_admin_exists()

    rs = get_regstack()
    user = await rs.users.get_by_email("admin@putplace.example.com")
    assert user is not None
    assert user.is_superuser is True
    assert user.hashed_password is not None
    assert user.hashed_password.startswith("$argon2id$")


@pytest.mark.asyncio
async def test_bootstrap_skipped_when_user_already_exists(_empty_regstack_users) -> None:
    # Seed one user before calling bootstrap.
    rs = get_regstack()
    await rs.bootstrap_admin(email="seed@example.com", password="seedpassword123")

    with patch.dict(
        os.environ,
        {
            "PUTPLACE_ADMIN_PASSWORD": "shouldnotapply123",
            "PUTPLACE_ADMIN_EMAIL": "shouldnotcreate@example.com",
        },
    ):
        await ensure_admin_exists()

    assert await rs.users.get_by_email("shouldnotcreate@example.com") is None
    assert await rs.users.count() == 1


@pytest.mark.asyncio
async def test_bootstrap_weak_password_rejected(_empty_regstack_users) -> None:
    with patch.dict(
        os.environ,
        {
            "PUTPLACE_ADMIN_PASSWORD": "weak",  # 4 chars; below 8-char floor
            "PUTPLACE_ADMIN_EMAIL": "weakadmin@putplace.example.com",
        },
    ):
        await ensure_admin_exists()

    rs = get_regstack()
    assert await rs.users.get_by_email("weakadmin@putplace.example.com") is None
    assert await rs.users.count() == 0


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent(_empty_regstack_users) -> None:
    with patch.dict(
        os.environ,
        {
            "PUTPLACE_ADMIN_PASSWORD": "idempotent123",
            "PUTPLACE_ADMIN_EMAIL": "idem@example.com",
        },
    ):
        await ensure_admin_exists()
        await ensure_admin_exists()

    rs = get_regstack()
    assert await rs.users.count() == 1
