"""Tests for MongoDB database operations."""

import pytest

from putplace.database import MongoDB


@pytest.mark.asyncio
async def test_database_connection(test_db: MongoDB):
    """Test that database connection is established."""
    assert test_db.client is not None
    assert test_db.collection is not None


@pytest.mark.asyncio
async def test_insert_file_metadata(test_db: MongoDB, sample_file_metadata):
    """Test inserting file metadata into database."""
    doc_id = await test_db.insert_file_metadata(sample_file_metadata)

    assert doc_id is not None
    assert isinstance(doc_id, str)
    assert len(doc_id) > 0


@pytest.mark.asyncio
async def test_find_by_sha256_exists(test_db: MongoDB, sample_file_metadata):
    """Test finding file metadata by SHA256 when it exists."""
    # Insert document
    await test_db.insert_file_metadata(sample_file_metadata)

    # Find it
    result = await test_db.find_by_sha256(sample_file_metadata["sha256"])

    assert result is not None
    assert result["filepath"] == sample_file_metadata["filepath"]
    assert result["hostname"] == sample_file_metadata["hostname"]
    assert result["ip_address"] == sample_file_metadata["ip_address"]
    assert result["sha256"] == sample_file_metadata["sha256"]
    assert "_id" in result


@pytest.mark.asyncio
async def test_find_by_sha256_not_exists(test_db: MongoDB):
    """Test finding file metadata by SHA256 when it doesn't exist."""
    nonexistent_sha256 = "f" * 64
    result = await test_db.find_by_sha256(nonexistent_sha256)

    assert result is None


@pytest.mark.asyncio
async def test_insert_multiple_documents(test_db: MongoDB, sample_file_metadata):
    """Test inserting multiple documents."""
    # Insert first document
    doc_id1 = await test_db.insert_file_metadata(sample_file_metadata)

    # Insert second document with different data
    second_metadata = sample_file_metadata.copy()
    second_metadata["filepath"] = "/var/log/other.log"
    second_metadata["sha256"] = "b" * 64

    doc_id2 = await test_db.insert_file_metadata(second_metadata)

    # IDs should be different
    assert doc_id1 != doc_id2

    # Both should be retrievable
    result1 = await test_db.find_by_sha256(sample_file_metadata["sha256"])
    result2 = await test_db.find_by_sha256(second_metadata["sha256"])

    assert result1["filepath"] == sample_file_metadata["filepath"]
    assert result2["filepath"] == second_metadata["filepath"]


@pytest.mark.asyncio
async def test_database_indexes(test_db: MongoDB):
    """Test that database indexes are created."""
    indexes = await test_db.collection.index_information()

    # Should have _id index (default) plus our custom indexes
    assert len(indexes) >= 3

    # Check for sha256 index
    index_names = list(indexes.keys())
    assert any("sha256" in name for name in index_names)


@pytest.mark.asyncio
async def test_insert_without_connection():
    """Test that insert fails without database connection."""
    db = MongoDB()
    # Don't connect

    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.insert_file_metadata({"test": "data"})


@pytest.mark.asyncio
async def test_find_without_connection():
    """Test that find fails without database connection."""
    db = MongoDB()
    # Don't connect

    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.find_by_sha256("a" * 64)


@pytest.mark.asyncio
async def test_duplicate_sha256_allowed(test_db: MongoDB, sample_file_metadata):
    """Test that duplicate SHA256 values are allowed (same hash, different hosts)."""
    # Insert first document
    doc_id1 = await test_db.insert_file_metadata(sample_file_metadata)

    # Insert second document with same SHA256 but different hostname
    second_metadata = sample_file_metadata.copy()
    second_metadata["hostname"] = "otherserver"

    doc_id2 = await test_db.insert_file_metadata(second_metadata)

    # Both should succeed
    assert doc_id1 != doc_id2

    # Finding by SHA256 should return one of them (typically the first)
    result = await test_db.find_by_sha256(sample_file_metadata["sha256"])
    assert result is not None
    assert result["sha256"] == sample_file_metadata["sha256"]


@pytest.mark.asyncio
async def test_database_connect_and_close(test_settings):
    """Test database connect and close methods."""
    from putplace.database import MongoDB

    db = MongoDB()

    # Initially not connected
    assert db.client is None
    assert db.collection is None

    # Connect to database
    await db.connect()

    # Should be connected now
    assert db.client is not None
    assert db.collection is not None

    # Verify indexes were created
    indexes = await db.collection.index_information()
    assert len(indexes) >= 3  # _id, sha256, and compound index

    # Clean up and close
    await db.collection.drop()
    await db.close()

    # Client should still exist but be closed
    assert db.client is not None


@pytest.mark.asyncio
async def test_database_close_without_client():
    """Test that close() handles missing client gracefully."""
    from putplace.database import MongoDB

    db = MongoDB()
    # Don't connect, just try to close
    await db.close()  # Should not raise an error

    assert db.client is None


@pytest.mark.asyncio
async def test_database_connection_failure():
    """Test handling of MongoDB connection failure."""
    from putplace.database import MongoDB
    from pymongo.errors import ConnectionFailure

    db = MongoDB()

    # Try to connect to invalid MongoDB URL
    from putplace.config import Settings

    invalid_settings = Settings(mongodb_url="mongodb://invalid-host:27017")

    # Temporarily replace settings
    from putplace import database as db_module

    original_settings = db_module.settings
    db_module.settings = invalid_settings

    try:
        # Should raise ConnectionFailure
        with pytest.raises(ConnectionFailure):
            await db.connect()

        # Connection should not be established
        assert db.client is None
        assert db.collection is None

    finally:
        # Restore original settings
        db_module.settings = original_settings


@pytest.mark.asyncio
async def test_database_is_healthy(test_db: MongoDB):
    """Test health check for connected database."""
    # Should be healthy
    assert await test_db.is_healthy() is True


@pytest.mark.asyncio
async def test_database_is_not_healthy():
    """Test health check for disconnected database."""
    from putplace.database import MongoDB

    db = MongoDB()
    # Not connected
    assert await db.is_healthy() is False


@pytest.mark.asyncio
async def test_insert_with_connection_loss(test_db: MongoDB, sample_file_metadata):
    """Test insert operation when connection is lost."""
    from pymongo.errors import ConnectionFailure
    from unittest.mock import AsyncMock

    # Save original method
    original_insert = test_db.collection.insert_one

    try:
        # Mock insert to raise ConnectionFailure
        test_db.collection.insert_one = AsyncMock(side_effect=ConnectionFailure("Connection lost"))

        # Should raise ConnectionFailure
        with pytest.raises(ConnectionFailure, match="Lost connection to database"):
            await test_db.insert_file_metadata(sample_file_metadata)

    finally:
        # Restore original method
        test_db.collection.insert_one = original_insert


@pytest.mark.asyncio
async def test_find_with_connection_loss(test_db: MongoDB):
    """Test find operation when connection is lost."""
    from pymongo.errors import ConnectionFailure
    from unittest.mock import AsyncMock

    # Save original method
    original_find = test_db.collection.find_one

    try:
        # Mock find to raise ConnectionFailure
        test_db.collection.find_one = AsyncMock(side_effect=ConnectionFailure("Connection lost"))

        # Should raise ConnectionFailure
        with pytest.raises(ConnectionFailure, match="Lost connection to database"):
            await test_db.find_by_sha256("a" * 64)

    finally:
        # Restore original method
        test_db.collection.find_one = original_find


@pytest.mark.asyncio
async def test_has_file_content_true(test_db: MongoDB, sample_file_metadata):
    """Test checking if file content exists when it does."""
    # Insert metadata with file content flag
    metadata_with_content = sample_file_metadata.copy()
    metadata_with_content["has_file_content"] = True
    await test_db.insert_file_metadata(metadata_with_content)

    # Should return True
    has_content = await test_db.has_file_content(sample_file_metadata["sha256"])
    assert has_content is True


@pytest.mark.asyncio
async def test_has_file_content_false(test_db: MongoDB, sample_file_metadata):
    """Test checking if file content exists when it doesn't."""
    # Insert metadata without file content flag
    await test_db.insert_file_metadata(sample_file_metadata)

    # Should return False
    has_content = await test_db.has_file_content(sample_file_metadata["sha256"])
    assert has_content is False


@pytest.mark.asyncio
async def test_has_file_content_not_found(test_db: MongoDB):
    """Test checking if file content exists for non-existent SHA256."""
    nonexistent_sha256 = "f" * 64
    has_content = await test_db.has_file_content(nonexistent_sha256)
    assert has_content is False


@pytest.mark.asyncio
async def test_has_file_content_without_connection():
    """Test that has_file_content fails without database connection."""
    db = MongoDB()
    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.has_file_content("a" * 64)


@pytest.mark.asyncio
async def test_mark_file_uploaded(test_db: MongoDB, sample_file_metadata):
    """Test marking a file as uploaded."""
    # Insert metadata
    await test_db.insert_file_metadata(sample_file_metadata)

    # Mark as uploaded
    storage_path = "/var/putplace/files/ab/abc123..."
    success = await test_db.mark_file_uploaded(
        sample_file_metadata["sha256"],
        sample_file_metadata["hostname"],
        sample_file_metadata["filepath"],
        storage_path
    )
    assert success is True

    # Verify it was updated
    result = await test_db.find_by_sha256(sample_file_metadata["sha256"])
    assert result["has_file_content"] is True
    assert result["storage_path"] == storage_path
    assert "file_uploaded_at" in result


@pytest.mark.asyncio
async def test_mark_file_uploaded_not_found(test_db: MongoDB):
    """Test marking a non-existent file as uploaded."""
    storage_path = "/var/putplace/files/test"
    success = await test_db.mark_file_uploaded(
        "f" * 64,
        "nonexistent-host",
        "/nonexistent/path",
        storage_path
    )
    assert success is False


@pytest.mark.asyncio
async def test_mark_file_uploaded_without_connection():
    """Test that mark_file_uploaded fails without database connection."""
    db = MongoDB()
    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.mark_file_uploaded("a" * 64, "host", "/path", "/storage")


@pytest.mark.asyncio
async def test_get_files_by_user(test_db: MongoDB, sample_file_metadata):
    """Test getting files by user ID."""
    # Insert metadata with user ID
    metadata_with_user = sample_file_metadata.copy()
    metadata_with_user["uploaded_by_user_id"] = "test_user_123"
    await test_db.insert_file_metadata(metadata_with_user)

    # Insert another file with same user
    metadata2 = sample_file_metadata.copy()
    metadata2["sha256"] = "b" * 64
    metadata2["uploaded_by_user_id"] = "test_user_123"
    await test_db.insert_file_metadata(metadata2)

    # Insert file with different user
    metadata3 = sample_file_metadata.copy()
    metadata3["sha256"] = "c" * 64
    metadata3["uploaded_by_user_id"] = "other_user"
    await test_db.insert_file_metadata(metadata3)

    # Get files for test_user_123
    files = await test_db.get_files_by_user("test_user_123")
    assert len(files) == 2
    assert all(f["uploaded_by_user_id"] == "test_user_123" for f in files)


@pytest.mark.asyncio
async def test_get_files_by_user_empty(test_db: MongoDB):
    """Test getting files by user ID when user has no files."""
    files = await test_db.get_files_by_user("nonexistent_user")
    assert len(files) == 0


@pytest.mark.asyncio
async def test_get_files_by_user_pagination(test_db: MongoDB, sample_file_metadata):
    """Test pagination for get_files_by_user."""
    import asyncio

    # Insert 5 files with distinct created_at times to ensure proper ordering
    for i in range(5):
        metadata = sample_file_metadata.copy()
        metadata["sha256"] = f"pagination{i:060x}"  # Make unique
        metadata["uploaded_by_user_id"] = "pagination_test_user"
        await test_db.insert_file_metadata(metadata)
        await asyncio.sleep(0.01)  # Small delay to ensure different timestamps

    # Get all files first to verify total count
    all_files = await test_db.get_files_by_user("pagination_test_user")
    assert len(all_files) == 5

    # Get first 2 files
    files_page1 = await test_db.get_files_by_user("pagination_test_user", limit=2, skip=0)
    assert len(files_page1) == 2

    # Get next 2 files
    files_page2 = await test_db.get_files_by_user("pagination_test_user", limit=2, skip=2)
    assert len(files_page2) == 2

    # Get last file
    files_page3 = await test_db.get_files_by_user("pagination_test_user", limit=2, skip=4)
    assert len(files_page3) == 1


@pytest.mark.asyncio
async def test_get_files_by_user_without_connection():
    """Test that get_files_by_user fails without database connection."""
    db = MongoDB()
    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.get_files_by_user("user123")


@pytest.mark.asyncio
async def test_get_files_by_sha256(test_db: MongoDB, sample_file_metadata):
    """Test getting all files with a specific SHA256."""
    sha256 = sample_file_metadata["sha256"]

    # Insert multiple files with same SHA256 on different hosts
    for i, hostname in enumerate(["host1", "host2", "host3"]):
        metadata = sample_file_metadata.copy()
        metadata["hostname"] = hostname
        metadata["filepath"] = f"/path/file{i}.txt"
        if i == 0:
            # First one has file content
            metadata["has_file_content"] = True
        await test_db.insert_file_metadata(metadata)

    # Get all files with this SHA256
    files = await test_db.get_files_by_sha256(sha256)
    assert len(files) == 3

    # File with content should be first
    assert files[0]["has_file_content"] is True
    assert files[0]["hostname"] == "host1"


@pytest.mark.asyncio
async def test_get_files_by_sha256_empty(test_db: MongoDB):
    """Test getting files by SHA256 when none exist."""
    files = await test_db.get_files_by_sha256("f" * 64)
    assert len(files) == 0


@pytest.mark.asyncio
async def test_get_files_by_sha256_without_connection():
    """Test that get_files_by_sha256 fails without database connection."""
    db = MongoDB()
    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.get_files_by_sha256("a" * 64)


@pytest.mark.asyncio
async def test_create_user(test_db: MongoDB):
    """Test creating a new user."""
    user_id = await test_db.create_user(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password_123",
        full_name="Test User"
    )

    assert user_id is not None
    assert isinstance(user_id, str)

    # Verify user was created
    user = await test_db.get_user_by_username("testuser")
    assert user is not None
    assert user["username"] == "testuser"
    assert user["email"] == "test@example.com"
    assert user["full_name"] == "Test User"
    assert user["is_active"] is True
    assert "created_at" in user


@pytest.mark.asyncio
async def test_create_user_duplicate_username(test_db: MongoDB):
    """Test that creating a user with duplicate username fails."""
    from pymongo.errors import DuplicateKeyError

    # Create first user
    await test_db.create_user(
        username="duplicate",
        email="user1@example.com",
        hashed_password="pass1"
    )

    # Try to create another user with same username
    with pytest.raises(DuplicateKeyError, match="Username already exists"):
        await test_db.create_user(
            username="duplicate",
            email="user2@example.com",
            hashed_password="pass2"
        )


@pytest.mark.asyncio
async def test_create_user_duplicate_email(test_db: MongoDB):
    """Test that creating a user with duplicate email fails."""
    from pymongo.errors import DuplicateKeyError

    # Create first user
    await test_db.create_user(
        username="user1",
        email="duplicate@example.com",
        hashed_password="pass1"
    )

    # Try to create another user with same email
    with pytest.raises(DuplicateKeyError, match="Email already exists"):
        await test_db.create_user(
            username="user2",
            email="duplicate@example.com",
            hashed_password="pass2"
        )


@pytest.mark.asyncio
async def test_create_user_without_connection():
    """Test that create_user fails without database connection."""
    db = MongoDB()
    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.create_user("user", "email@test.com", "pass")


@pytest.mark.asyncio
async def test_get_user_by_username(test_db: MongoDB):
    """Test getting user by username."""
    # Create a user
    await test_db.create_user(
        username="findme",
        email="findme@example.com",
        hashed_password="pass123"
    )

    # Find by username
    user = await test_db.get_user_by_username("findme")
    assert user is not None
    assert user["username"] == "findme"


@pytest.mark.asyncio
async def test_get_user_by_username_not_found(test_db: MongoDB):
    """Test getting user by username when not found."""
    user = await test_db.get_user_by_username("nonexistent")
    assert user is None


@pytest.mark.asyncio
async def test_get_user_by_username_without_connection():
    """Test that get_user_by_username fails without database connection."""
    db = MongoDB()
    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.get_user_by_username("user")


@pytest.mark.asyncio
async def test_get_user_by_email(test_db: MongoDB):
    """Test getting user by email."""
    # Create a user
    await test_db.create_user(
        username="emailuser",
        email="find@example.com",
        hashed_password="pass123"
    )

    # Find by email
    user = await test_db.get_user_by_email("find@example.com")
    assert user is not None
    assert user["email"] == "find@example.com"
    assert user["username"] == "emailuser"


@pytest.mark.asyncio
async def test_get_user_by_email_not_found(test_db: MongoDB):
    """Test getting user by email when not found."""
    user = await test_db.get_user_by_email("nonexistent@example.com")
    assert user is None


@pytest.mark.asyncio
async def test_get_user_by_email_without_connection():
    """Test that get_user_by_email fails without database connection."""
    db = MongoDB()
    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.get_user_by_email("user@example.com")
