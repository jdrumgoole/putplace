"""Tests for the Phase 2 migration script (pp_migrate_users)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from pymongo import AsyncMongoClient

from putplace_server.config import Settings
from putplace_server.scripts.migrate_to_regstack import _migrate, _to_oauth_identity, _to_regstack_user


# ----- _to_regstack_user / _to_oauth_identity unit tests -------------------


def test_password_user_maps_to_regstack_shape() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    src = {
        "_id": ObjectId(),
        "email": "alice@example.com",
        "username": "alice@example.com",
        "hashed_password": "$argon2id$v=19$m=65536,t=3,p=4$...",
        "is_active": True,
        "is_admin": False,
        "full_name": "Alice",
        "created_at": now,
    }

    out = _to_regstack_user(src)

    assert out["_id"] == src["_id"]
    assert out["email"] == "alice@example.com"
    assert out["hashed_password"] == src["hashed_password"]
    assert out["is_active"] is True
    assert out["is_superuser"] is False
    assert out["is_verified"] is True
    assert out["is_mfa_enabled"] is False
    assert out["full_name"] == "Alice"
    assert out["created_at"] == now
    assert "username" not in out
    assert "is_admin" not in out


def test_oauth_user_empty_password_becomes_none() -> None:
    out = _to_regstack_user(
        {
            "_id": ObjectId(),
            "email": "bob@example.com",
            "hashed_password": "",
            "is_active": True,
            "is_admin": False,
            "auth_provider": "google",
            "oauth_id": "google-sub-123",
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
        }
    )

    assert out["hashed_password"] is None


def test_missing_hashed_password_becomes_none() -> None:
    out = _to_regstack_user(
        {
            "_id": ObjectId(),
            "email": "carol@example.com",
            "is_active": True,
            "is_admin": False,
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
        }
    )

    assert out["hashed_password"] is None


def test_is_admin_maps_to_is_superuser() -> None:
    out = _to_regstack_user(
        {
            "_id": ObjectId(),
            "email": "admin@example.com",
            "hashed_password": "x",
            "is_admin": True,
            "is_active": True,
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
        }
    )
    assert out["is_superuser"] is True


def test_naive_datetime_normalized_to_utc() -> None:
    naive = datetime(2025, 1, 1)
    out = _to_regstack_user(
        {
            "_id": ObjectId(),
            "email": "d@example.com",
            "hashed_password": "x",
            "is_active": True,
            "is_admin": False,
            "created_at": naive,
        }
    )
    assert out["created_at"].tzinfo == UTC


def test_oauth_identity_extracted_for_google_user() -> None:
    user_id = ObjectId()
    identity = _to_oauth_identity(
        {
            "_id": user_id,
            "email": "e@example.com",
            "hashed_password": "",
            "auth_provider": "google",
            "oauth_id": "google-sub-xyz",
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
        }
    )

    assert identity is not None
    assert identity["user_id"] == user_id
    assert identity["provider"] == "google"
    assert identity["subject_id"] == "google-sub-xyz"
    assert identity["email"] == "e@example.com"


def test_oauth_identity_none_for_password_user() -> None:
    assert (
        _to_oauth_identity(
            {
                "_id": ObjectId(),
                "email": "f@example.com",
                "hashed_password": "x",
                "auth_provider": None,
                "oauth_id": None,
                "created_at": datetime(2025, 1, 1, tzinfo=UTC),
            }
        )
        is None
    )


def test_oauth_identity_none_for_local_provider() -> None:
    assert (
        _to_oauth_identity(
            {
                "_id": ObjectId(),
                "email": "g@example.com",
                "hashed_password": "x",
                "auth_provider": "local",
                "oauth_id": "x",
                "created_at": datetime(2025, 1, 1, tzinfo=UTC),
            }
        )
        is None
    )


# ----- end-to-end migration against a live Mongo --------------------------


@pytest.fixture
async def migration_db(test_settings: Settings, worker_id: str):
    """Per-worker database with source/target/oauth/pending collections.

    Yields the names so the test can call _migrate() with them directly
    instead of touching the worker's canonical putplace collections.
    """
    client = AsyncMongoClient(test_settings.mongodb_url)
    db = client[test_settings.mongodb_database]

    source = f"users_src_{worker_id}"
    target = f"regstack_users_dst_{worker_id}"
    oauth = f"regstack_oauth_dst_{worker_id}"
    pending = "pending_users"  # the script reports its count; existence not required

    for name in (source, target, oauth):
        await db[name].drop()

    yield {
        "mongodb_url": test_settings.mongodb_url,
        "database": test_settings.mongodb_database,
        "source": source,
        "target": target,
        "oauth_target": oauth,
        "db": db,
    }

    for name in (source, target, oauth):
        await db[name].drop()
    await client.aclose()


async def _seed_user(db, source: str, **fields: Any) -> ObjectId:
    doc = {
        "_id": fields.get("_id", ObjectId()),
        "email": fields["email"],
        "username": fields["email"],
        "hashed_password": fields.get("hashed_password", ""),
        "is_active": fields.get("is_active", True),
        "is_admin": fields.get("is_admin", False),
        "created_at": fields.get("created_at", datetime(2025, 1, 1, tzinfo=UTC)),
    }
    for opt in ("full_name", "auth_provider", "oauth_id", "picture"):
        if opt in fields:
            doc[opt] = fields[opt]
    await db[source].insert_one(doc)
    return doc["_id"]


@pytest.mark.asyncio
async def test_migrates_password_user_preserving_id(migration_db) -> None:
    src_id = await _seed_user(
        migration_db["db"],
        migration_db["source"],
        email="alice@example.com",
        hashed_password="$argon2id$v=19$m=65536,t=3,p=4$abc",
        is_admin=False,
    )

    rc = await _migrate(
        mongodb_url=migration_db["mongodb_url"],
        database=migration_db["database"],
        source=migration_db["source"],
        target=migration_db["target"],
        oauth_target=migration_db["oauth_target"],
        dry_run=False,
    )
    assert rc == 0

    migrated = await migration_db["db"][migration_db["target"]].find_one({"_id": src_id})
    assert migrated is not None
    assert migrated["_id"] == src_id
    assert migrated["email"] == "alice@example.com"
    assert migrated["hashed_password"].startswith("$argon2id$")
    assert migrated["is_superuser"] is False
    assert migrated["is_verified"] is True


@pytest.mark.asyncio
async def test_oauth_user_split_into_identity_row(migration_db) -> None:
    src_id = await _seed_user(
        migration_db["db"],
        migration_db["source"],
        email="bob@example.com",
        hashed_password="",
        auth_provider="google",
        oauth_id="google-sub-bob",
    )

    rc = await _migrate(
        mongodb_url=migration_db["mongodb_url"],
        database=migration_db["database"],
        source=migration_db["source"],
        target=migration_db["target"],
        oauth_target=migration_db["oauth_target"],
        dry_run=False,
    )
    assert rc == 0

    user = await migration_db["db"][migration_db["target"]].find_one({"_id": src_id})
    assert user is not None
    assert user["hashed_password"] is None

    identity = await migration_db["db"][migration_db["oauth_target"]].find_one(
        {"provider": "google", "subject_id": "google-sub-bob"}
    )
    assert identity is not None
    assert identity["user_id"] == src_id
    assert identity["email"] == "bob@example.com"


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(migration_db) -> None:
    await _seed_user(
        migration_db["db"],
        migration_db["source"],
        email="alice@example.com",
        hashed_password="$argon2id$x",
    )

    rc = await _migrate(
        mongodb_url=migration_db["mongodb_url"],
        database=migration_db["database"],
        source=migration_db["source"],
        target=migration_db["target"],
        oauth_target=migration_db["oauth_target"],
        dry_run=True,
    )
    assert rc == 0
    assert await migration_db["db"][migration_db["target"]].count_documents({}) == 0
    assert await migration_db["db"][migration_db["oauth_target"]].count_documents({}) == 0


@pytest.mark.asyncio
async def test_idempotent_rerun(migration_db) -> None:
    await _seed_user(
        migration_db["db"],
        migration_db["source"],
        email="alice@example.com",
        hashed_password="$argon2id$x",
    )
    await _seed_user(
        migration_db["db"],
        migration_db["source"],
        email="bob@example.com",
        hashed_password="",
        auth_provider="google",
        oauth_id="google-sub-bob",
    )

    for _ in range(2):
        rc = await _migrate(
            mongodb_url=migration_db["mongodb_url"],
            database=migration_db["database"],
            source=migration_db["source"],
            target=migration_db["target"],
            oauth_target=migration_db["oauth_target"],
            dry_run=False,
        )
        assert rc == 0

    assert await migration_db["db"][migration_db["target"]].count_documents({}) == 2
    assert await migration_db["db"][migration_db["oauth_target"]].count_documents({}) == 1


@pytest.mark.asyncio
async def test_argon2_hash_portable_argon2_cffi_to_pwdlib() -> None:
    """A hash from argon2-cffi (putplace's old hasher) must verify under regstack's pwdlib.

    Without this property, every migrated user would need a forced password reset.
    """
    from argon2 import PasswordHasher as Argon2CffiHasher
    from regstack.auth.password import PasswordHasher

    plaintext = "correct horse battery staple"
    legacy_hash = Argon2CffiHasher().hash(plaintext)

    regstack_hasher = PasswordHasher()
    assert regstack_hasher.verify(plaintext, legacy_hash) is True
    assert regstack_hasher.verify("wrong password", legacy_hash) is False


@pytest.mark.asyncio
async def test_api_key_user_id_still_resolves(migration_db) -> None:
    src_id = await _seed_user(
        migration_db["db"],
        migration_db["source"],
        email="carol@example.com",
        hashed_password="$argon2id$x",
    )
    api_keys = migration_db["db"][f"api_keys_dst_{src_id}"]
    await api_keys.insert_one({"key_hash": "abc", "user_id": str(src_id), "is_active": True})

    rc = await _migrate(
        mongodb_url=migration_db["mongodb_url"],
        database=migration_db["database"],
        source=migration_db["source"],
        target=migration_db["target"],
        oauth_target=migration_db["oauth_target"],
        dry_run=False,
    )
    assert rc == 0

    api_key_doc = await api_keys.find_one({"key_hash": "abc"})
    assert api_key_doc is not None
    migrated = await migration_db["db"][migration_db["target"]].find_one(
        {"_id": ObjectId(api_key_doc["user_id"])}
    )
    assert migrated is not None
    assert migrated["email"] == "carol@example.com"

    await api_keys.drop()
