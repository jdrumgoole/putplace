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
