"""Tests for automatic admin user creation."""

import os
from unittest.mock import patch

import pytest

from putplace_server.database import MongoDB
from putplace_server.main import ensure_admin_exists
from putplace_server.user_auth import verify_password


@pytest.mark.asyncio
async def test_ensure_admin_no_users_generates_random_password(test_db: MongoDB):
    """Test that admin is created with random password when no users exist."""
    # Verify no users exist
    count = await test_db.users_collection.count_documents({})
    assert count == 0

    # Call ensure_admin_exists
    await ensure_admin_exists(test_db)

    # Verify admin user was created
    admin_user = await test_db.get_user_by_email("admin@localhost")
    assert admin_user is not None
    assert admin_user["email"] == "admin@localhost"
    assert admin_user["is_active"] is True
    assert "hashed_password" in admin_user
    assert admin_user["hashed_password"].startswith("$argon2id$")


@pytest.mark.asyncio
async def test_ensure_admin_with_env_vars(test_db: MongoDB):
    """Test that admin is created from environment variables when set."""
    # Set environment variables
    with patch.dict(
        os.environ,
        {
            "PUTPLACE_ADMIN_PASSWORD": "securepass123",
            "PUTPLACE_ADMIN_EMAIL": "admin@example.com",
        },
    ):
        # Call ensure_admin_exists
        await ensure_admin_exists(test_db)

    # Verify custom admin user was created
    admin_user = await test_db.get_user_by_email("admin@example.com")
    assert admin_user is not None
    assert admin_user["email"] == "admin@example.com"
    assert admin_user["is_active"] is True

    # Verify password works
    assert verify_password("securepass123", admin_user["hashed_password"]) is True


@pytest.mark.asyncio
async def test_ensure_admin_with_weak_password_rejected(test_db: MongoDB):
    """Test that weak passwords from env vars are rejected."""
    # Set environment variables with weak password
    with patch.dict(
        os.environ,
        {
            "PUTPLACE_ADMIN_PASSWORD": "weak",  # Only 4 characters
            "PUTPLACE_ADMIN_EMAIL": "weakadmin@example.com",
        },
    ):
        await ensure_admin_exists(test_db)

    # Verify admin user was NOT created
    admin_user = await test_db.get_user_by_email("weakadmin@example.com")
    assert admin_user is None

    # No users should exist
    count = await test_db.users_collection.count_documents({})
    assert count == 0


@pytest.mark.asyncio
async def test_ensure_admin_skips_if_users_exist(test_db: MongoDB):
    """Test that admin creation is skipped if any users already exist."""
    # Create an existing user
    from datetime import datetime

    from putplace_server.user_auth import get_password_hash

    existing_user = {
        "email": "existing@example.com",
        "username": "existing@example.com",  # Use email as username
        "hashed_password": get_password_hash("password123"),
        "is_active": True,
        "created_at": datetime.utcnow(),
    }
    await test_db.users_collection.insert_one(existing_user)

    # Try to create admin
    with patch.dict(
        os.environ,
        {
            "PUTPLACE_ADMIN_PASSWORD": "password123",
            "PUTPLACE_ADMIN_EMAIL": "shouldnotcreate@example.com",
        },
    ):
        await ensure_admin_exists(test_db)

    # Verify no new admin was created
    admin_user = await test_db.get_user_by_email("shouldnotcreate@example.com")
    assert admin_user is None

    # Only the existing user should be there
    count = await test_db.users_collection.count_documents({})
    assert count == 1


@pytest.mark.asyncio
async def test_ensure_admin_idempotent(test_db: MongoDB):
    """Test that calling ensure_admin_exists multiple times doesn't create duplicates."""
    # First call
    await ensure_admin_exists(test_db)

    # Verify admin created
    count = await test_db.users_collection.count_documents({})
    assert count == 1

    # Second call
    await ensure_admin_exists(test_db)

    # Still only one user
    count = await test_db.users_collection.count_documents({})
    assert count == 1


@pytest.mark.asyncio
async def test_ensure_admin_password_hashing(test_db: MongoDB):
    """Test that passwords are properly hashed using Argon2."""
    with patch.dict(
        os.environ,
        {
            "PUTPLACE_ADMIN_PASSWORD": "mypassword123",
            "PUTPLACE_ADMIN_EMAIL": "testadmin@example.com",
        },
    ):
        await ensure_admin_exists(test_db)

    admin_user = await test_db.get_user_by_email("testadmin@example.com")
    assert admin_user is not None

    # Password should be hashed with Argon2
    assert admin_user["hashed_password"].startswith("$argon2id$")

    # Original password should not be in the hash
    assert "mypassword123" not in admin_user["hashed_password"]

    # Verify password can be verified
    assert verify_password("mypassword123", admin_user["hashed_password"]) is True
    assert verify_password("wrongpassword", admin_user["hashed_password"]) is False


@pytest.mark.asyncio
async def test_ensure_admin_handles_database_errors_gracefully(test_db: MongoDB):
    """Test that errors during admin creation don't crash the app."""
    # Simulate a database error by dropping the collection during operation
    # This should be handled gracefully

    # Close the database connection to simulate an error
    original_collection = test_db.users_collection
    test_db.users_collection = None

    # Should not raise an exception
    try:
        await ensure_admin_exists(test_db)
    except Exception as e:
        pytest.fail(f"ensure_admin_exists raised an exception: {e}")

    # Restore collection
    test_db.users_collection = original_collection


@pytest.mark.asyncio
async def test_ensure_admin_creates_full_user_document(test_db: MongoDB):
    """Test that all required user fields are populated."""
    await ensure_admin_exists(test_db)

    admin_user = await test_db.get_user_by_email("admin@localhost")
    assert admin_user is not None

    # Check all required fields
    assert "email" in admin_user
    assert "hashed_password" in admin_user
    assert "is_active" in admin_user
    assert "created_at" in admin_user

    # Check field values
    assert admin_user["is_active"] is True
    assert admin_user["created_at"] is not None
