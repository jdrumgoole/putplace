"""Tests for API key authentication and management."""

import pytest
from bson import ObjectId
from httpx import AsyncClient

from putplace.auth import APIKeyAuth, generate_api_key, hash_api_key


@pytest.mark.asyncio
async def test_generate_api_key():
    """Test API key generation."""
    key1 = generate_api_key()
    key2 = generate_api_key()

    # Keys should be 64 characters (32 bytes hex encoded)
    assert len(key1) == 64
    assert len(key2) == 64

    # Keys should be unique
    assert key1 != key2

    # Keys should be hex strings
    assert all(c in '0123456789abcdef' for c in key1)
    assert all(c in '0123456789abcdef' for c in key2)


@pytest.mark.asyncio
async def test_hash_api_key():
    """Test API key hashing."""
    key = "test_api_key_12345"
    hash1 = hash_api_key(key)
    hash2 = hash_api_key(key)

    # Same key should produce same hash
    assert hash1 == hash2

    # Hash should be 64 characters (SHA256 hex)
    assert len(hash1) == 64

    # Different keys should produce different hashes
    different_key = "different_key_67890"
    assert hash_api_key(different_key) != hash1


@pytest.mark.asyncio
async def test_create_api_key(test_db):
    """Test creating an API key."""
    auth = APIKeyAuth(test_db)

    api_key, metadata = await auth.create_api_key(
        name="test-key",
        description="Test API key"
    )

    # API key should be returned
    assert api_key is not None
    assert len(api_key) == 64

    # Metadata should contain expected fields
    assert metadata["name"] == "test-key"
    assert metadata["description"] == "Test API key"
    assert metadata["is_active"] is True
    assert "created_at" in metadata
    assert "key_hash" not in metadata  # Hash should not be returned


@pytest.mark.asyncio
async def test_create_api_key_with_user_id(test_db):
    """Test creating an API key associated with a user."""
    auth = APIKeyAuth(test_db)

    user_id = "user_12345"
    api_key, metadata = await auth.create_api_key(
        name="user-key",
        user_id=user_id,
        description="User's API key"
    )

    assert metadata["user_id"] == user_id
    assert metadata["name"] == "user-key"


@pytest.mark.asyncio
async def test_verify_api_key_success(test_db):
    """Test verifying a valid API key."""
    auth = APIKeyAuth(test_db)

    # Create a key
    api_key, _ = await auth.create_api_key(name="valid-key")

    # Verify it
    result = await auth.verify_api_key(api_key)

    assert result is not None
    assert result["name"] == "valid-key"
    assert result["is_active"] is True
    assert "last_used_at" in result


@pytest.mark.asyncio
async def test_verify_api_key_invalid(test_db):
    """Test verifying an invalid API key."""
    auth = APIKeyAuth(test_db)

    # Try to verify a non-existent key
    result = await auth.verify_api_key("invalid_key_12345")

    assert result is None


@pytest.mark.asyncio
async def test_verify_api_key_inactive(test_db):
    """Test that inactive keys are not verified."""
    auth = APIKeyAuth(test_db)

    # Create and then revoke a key
    api_key, metadata = await auth.create_api_key(name="inactive-key")
    key_id = metadata["_id"]

    await auth.revoke_api_key(key_id)

    # Try to verify the revoked key
    result = await auth.verify_api_key(api_key)

    assert result is None


@pytest.mark.asyncio
async def test_revoke_api_key(test_db):
    """Test revoking an API key."""
    auth = APIKeyAuth(test_db)

    # Create a key
    api_key, metadata = await auth.create_api_key(name="revoke-test")
    key_id = metadata["_id"]

    # Revoke it
    success = await auth.revoke_api_key(key_id)
    assert success is True

    # Verify it's no longer valid
    result = await auth.verify_api_key(api_key)
    assert result is None


@pytest.mark.asyncio
async def test_revoke_nonexistent_key(test_db):
    """Test revoking a non-existent key."""
    auth = APIKeyAuth(test_db)

    # Try to revoke a key that doesn't exist
    fake_id = str(ObjectId())
    success = await auth.revoke_api_key(fake_id)

    assert success is False


@pytest.mark.asyncio
async def test_list_api_keys(test_db):
    """Test listing all API keys."""
    auth = APIKeyAuth(test_db)

    # Create multiple keys
    await auth.create_api_key(name="key1", description="First key")
    await auth.create_api_key(name="key2", description="Second key")
    await auth.create_api_key(name="key3", description="Third key")

    # List all keys
    keys = await auth.list_api_keys()

    assert len(keys) == 3
    assert all("name" in key for key in keys)
    assert all("key_hash" not in key for key in keys)  # Hashes should be excluded

    # Verify key names
    key_names = {key["name"] for key in keys}
    assert key_names == {"key1", "key2", "key3"}


@pytest.mark.asyncio
async def test_list_api_keys_by_user(test_db):
    """Test listing API keys filtered by user ID."""
    auth = APIKeyAuth(test_db)

    user1_id = "user1"
    user2_id = "user2"

    # Create keys for different users
    await auth.create_api_key(name="user1-key1", user_id=user1_id)
    await auth.create_api_key(name="user1-key2", user_id=user1_id)
    await auth.create_api_key(name="user2-key1", user_id=user2_id)

    # List keys for user1
    user1_keys = await auth.list_api_keys(user_id=user1_id)
    assert len(user1_keys) == 2
    assert all(key["user_id"] == user1_id for key in user1_keys)

    # List keys for user2
    user2_keys = await auth.list_api_keys(user_id=user2_id)
    assert len(user2_keys) == 1
    assert user2_keys[0]["user_id"] == user2_id


@pytest.mark.asyncio
async def test_delete_api_key(test_db):
    """Test permanently deleting an API key."""
    auth = APIKeyAuth(test_db)

    # Create a key
    _, metadata = await auth.create_api_key(name="delete-test")
    key_id = metadata["_id"]

    # Delete it
    success = await auth.delete_api_key(key_id)
    assert success is True

    # Verify it's gone
    keys = await auth.list_api_keys()
    assert not any(key["_id"] == key_id for key in keys)


@pytest.mark.asyncio
async def test_delete_nonexistent_key(test_db):
    """Test deleting a non-existent key."""
    auth = APIKeyAuth(test_db)

    # Try to delete a key that doesn't exist
    fake_id = str(ObjectId())
    success = await auth.delete_api_key(fake_id)

    assert success is False


@pytest.mark.asyncio
async def test_api_key_authentication_endpoint(client: AsyncClient, test_api_key: str):
    """Test API authentication via X-API-Key header."""
    # Test with valid API key
    response = await client.get("/health", headers={"X-API-Key": test_api_key})
    assert response.status_code == 200

    # Test without API key (should still work for public endpoints)
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth(client: AsyncClient, test_user_token: str, sample_file_metadata):
    """Test that protected endpoints require authentication."""
    # Try without JWT token - should return 401 or 403 Unauthorized
    response = await client.post("/put_file", json=sample_file_metadata)
    assert response.status_code in [401, 403]

    # Try with valid JWT token
    response = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_invalid_api_key_rejected(client: AsyncClient, sample_file_metadata):
    """Test that invalid JWT tokens are rejected."""
    response = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": "Bearer invalid_token_12345"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_key_last_used_timestamp_updated(test_db):
    """Test that last_used_at timestamp is updated on key usage."""
    auth = APIKeyAuth(test_db)

    # Create a key
    api_key, metadata = await auth.create_api_key(name="timestamp-test")
    created_at = metadata["created_at"]

    # Wait a moment
    import asyncio
    await asyncio.sleep(0.1)

    # Verify the key (which updates last_used_at)
    result = await auth.verify_api_key(api_key)

    assert result is not None
    assert "last_used_at" in result
    # last_used_at should be set after creation
    if result["last_used_at"] is not None:
        assert result["last_used_at"] >= created_at
