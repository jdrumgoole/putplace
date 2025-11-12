"""Tests for FastAPI endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint returns home page HTML."""
    response = await client.get("/")
    assert response.status_code == 200

    # Check that it returns HTML
    assert "text/html" in response.headers["content-type"]

    # Check for key elements in the home page
    html = response.text
    assert "PutPlace" in html
    assert "File Metadata Storage" in html
    assert "/docs" in html  # Link to API docs


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "database" in data
    assert data["database"]["status"] == "connected"
    assert data["database"]["type"] == "mongodb"


@pytest.mark.asyncio
async def test_put_file_valid(client: AsyncClient, sample_file_metadata, test_user_token: str):
    """Test storing valid file metadata."""
    response = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 201

    data = response.json()
    assert data["filepath"] == sample_file_metadata["filepath"]
    assert data["hostname"] == sample_file_metadata["hostname"]
    assert data["ip_address"] == sample_file_metadata["ip_address"]
    assert data["sha256"] == sample_file_metadata["sha256"]
    assert "created_at" in data
    assert "id" in data or "_id" in data


@pytest.mark.asyncio
async def test_put_file_invalid_sha256(client: AsyncClient, sample_file_metadata, test_user_token: str):
    """Test that invalid SHA256 is rejected."""
    invalid_data = sample_file_metadata.copy()
    invalid_data["sha256"] = "tooshort"

    response = await client.post(
        "/put_file",
        json=invalid_data,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_put_file_missing_field(client: AsyncClient, sample_file_metadata, test_user_token: str):
    """Test that missing required field is rejected."""
    invalid_data = sample_file_metadata.copy()
    del invalid_data["hostname"]

    response = await client.post(
        "/put_file",
        json=invalid_data,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_get_file_by_sha256(client: AsyncClient, sample_file_metadata, test_user_token: str):
    """Test retrieving file metadata by SHA256."""
    # First, store the file
    post_response = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert post_response.status_code == 201

    # Then retrieve it
    sha256 = sample_file_metadata["sha256"]
    get_response = await client.get(
        f"/get_file/{sha256}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert get_response.status_code == 200

    data = get_response.json()
    assert data["filepath"] == sample_file_metadata["filepath"]
    assert data["hostname"] == sample_file_metadata["hostname"]
    assert data["sha256"] == sha256


@pytest.mark.asyncio
async def test_get_file_not_found(client: AsyncClient, test_user_token: str):
    """Test retrieving non-existent file returns 404."""
    nonexistent_sha256 = "f" * 64
    response = await client.get(
        f"/get_file/{nonexistent_sha256}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 404

    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_file_invalid_sha256_length(client: AsyncClient, test_user_token: str):
    """Test that invalid SHA256 length returns 400."""
    invalid_sha256 = "tooshort"
    response = await client.get(
        f"/get_file/{invalid_sha256}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 400

    data = response.json()
    assert "detail" in data
    assert "64 characters" in data["detail"]


@pytest.mark.asyncio
async def test_put_multiple_files(client: AsyncClient, sample_file_metadata, test_user_token: str):
    """Test storing multiple different files."""
    # Store first file
    response1 = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response1.status_code == 201

    # Store second file with different data
    second_file = sample_file_metadata.copy()
    second_file["filepath"] = "/var/log/other.log"
    second_file["sha256"] = "b" * 64

    response2 = await client.post(
        "/put_file",
        json=second_file,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response2.status_code == 201

    # Verify both can be retrieved
    get1 = await client.get(
        f"/get_file/{sample_file_metadata['sha256']}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert get1.status_code == 200
    assert get1.json()["filepath"] == sample_file_metadata["filepath"]

    get2 = await client.get(
        f"/get_file/{second_file['sha256']}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert get2.status_code == 200
    assert get2.json()["filepath"] == second_file["filepath"]


@pytest.mark.asyncio
async def test_put_duplicate_sha256(client: AsyncClient, sample_file_metadata, test_user_token: str):
    """Test storing files with same SHA256."""
    # Store first file
    response1 = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response1.status_code == 201

    # Store same file again (duplicate SHA256)
    response2 = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    # Should still succeed (MongoDB will create a new document)
    assert response2.status_code == 201


@pytest.mark.asyncio
async def test_api_cors_headers(client: AsyncClient):
    """Test that API responses include proper headers."""
    response = await client.get("/health")
    assert response.status_code == 200
    # Response should be JSON
    assert "application/json" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_app_lifespan(test_settings, test_db, monkeypatch):
    """Test application lifespan manager handles startup/shutdown.

    Note: This test uses the test_db fixture to ensure dependency overrides
    are in place, preventing global state pollution in serial test execution.
    """
    from fastapi import FastAPI
    from putplace.database import MongoDB
    from putplace import database

    # Set storage path via environment variable
    monkeypatch.setenv("STORAGE_PATH", test_settings.storage_path)

    # Save original mongodb instance
    original_mongodb = database.mongodb

    # Create an isolated test instance (not connected yet)
    test_mongodb = MongoDB()

    # Temporarily replace global instance for this test only
    database.mongodb = test_mongodb

    app = FastAPI()

    try:
        # Import lifespan after monkeypatch to get updated settings
        from putplace import main

        # Test lifespan context manager
        async with main.lifespan(app):
            # Inside lifespan, database should be connected
            assert test_mongodb.client is not None
            assert test_mongodb.collection is not None

        # After lifespan exits, connection should be closed (but client still exists)
        assert test_mongodb.client is not None

    finally:
        # Close test mongodb connection
        if test_mongodb.client:
            await test_mongodb.client.close()

        # Restore original instance immediately
        database.mongodb = original_mongodb


@pytest.mark.asyncio
async def test_put_file_database_error(client: AsyncClient, sample_file_metadata, test_user_token: str, test_db):
    """Test that database errors are handled properly."""
    from unittest.mock import AsyncMock

    # Save original method
    original_insert = test_db.insert_file_metadata

    try:
        # Mock insert to raise an exception
        test_db.insert_file_metadata = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        # Try to insert - should get 500 error
        response = await client.post(
            "/put_file",
            json=sample_file_metadata,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 500
        assert "Failed to store file metadata" in response.json()["detail"]

    finally:
        # Restore original method
        test_db.insert_file_metadata = original_insert


@pytest.mark.asyncio
async def test_health_endpoint_degraded(client: AsyncClient, test_db):
    """Test health endpoint when database is unavailable."""
    from unittest.mock import AsyncMock

    # Save original method
    original_is_healthy = test_db.is_healthy

    try:
        # Mock is_healthy to return False
        test_db.is_healthy = AsyncMock(return_value=False)

        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"]["status"] == "disconnected"

    finally:
        # Restore original method
        test_db.is_healthy = original_is_healthy
