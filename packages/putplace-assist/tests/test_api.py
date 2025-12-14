"""Tests for FastAPI endpoints.

These tests require a full application context with the FastAPI lifespan manager.
Mark them as integration tests to skip in basic test runs.
"""

import pytest
from httpx import AsyncClient


# Mark all API tests as integration tests
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestHealthEndpoints:
    """Tests for health check endpoints."""

    async def test_root(self, client: AsyncClient):
        """Test root endpoint."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "PutPlace Assist"
        assert "version" in data

    async def test_health(self, client: AsyncClient):
        """Test health endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "degraded")
        assert "version" in data
        assert "database_ok" in data


@pytest.mark.asyncio
class TestPathEndpoints:
    """Tests for path management endpoints."""

    async def test_list_paths_empty(self, client: AsyncClient):
        """Test listing paths when empty."""
        response = await client.get("/paths")
        assert response.status_code == 200
        data = response.json()
        assert data["paths"] == []
        assert data["total"] == 0

    async def test_register_path(self, client: AsyncClient, temp_test_dir):
        """Test registering a path."""
        response = await client.post(
            "/paths",
            json={"path": str(temp_test_dir), "recursive": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == str(temp_test_dir)
        assert data["recursive"] is True
        assert "id" in data

    async def test_register_path_not_found(self, client: AsyncClient):
        """Test registering nonexistent path."""
        response = await client.post(
            "/paths",
            json={"path": "/nonexistent/path", "recursive": True},
        )
        assert response.status_code == 400

    async def test_get_path(self, client: AsyncClient, temp_test_dir):
        """Test getting a specific path."""
        # First register a path
        create_response = await client.post(
            "/paths",
            json={"path": str(temp_test_dir)},
        )
        path_id = create_response.json()["id"]

        # Then get it
        response = await client.get(f"/paths/{path_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == path_id

    async def test_delete_path(self, client: AsyncClient, temp_test_dir):
        """Test deleting a path."""
        # First register a path
        create_response = await client.post(
            "/paths",
            json={"path": str(temp_test_dir)},
        )
        path_id = create_response.json()["id"]

        # Then delete it
        response = await client.delete(f"/paths/{path_id}")
        assert response.status_code == 200

        # Verify it's gone
        get_response = await client.get(f"/paths/{path_id}")
        assert get_response.status_code == 404


@pytest.mark.asyncio
class TestExcludeEndpoints:
    """Tests for exclude pattern endpoints."""

    async def test_list_excludes_empty(self, client: AsyncClient):
        """Test listing excludes when empty."""
        response = await client.get("/excludes")
        assert response.status_code == 200
        data = response.json()
        assert data["patterns"] == []

    async def test_add_exclude(self, client: AsyncClient):
        """Test adding an exclude pattern."""
        response = await client.post(
            "/excludes",
            json={"pattern": "*.log"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pattern"] == "*.log"
        assert "id" in data

    async def test_delete_exclude(self, client: AsyncClient):
        """Test deleting an exclude pattern."""
        # First add a pattern
        create_response = await client.post(
            "/excludes",
            json={"pattern": "*.log"},
        )
        exclude_id = create_response.json()["id"]

        # Then delete it
        response = await client.delete(f"/excludes/{exclude_id}")
        assert response.status_code == 200


@pytest.mark.asyncio
class TestFileEndpoints:
    """Tests for file management endpoints."""

    async def test_list_files_empty(self, client: AsyncClient):
        """Test listing files when empty."""
        response = await client.get("/files")
        assert response.status_code == 200
        data = response.json()
        assert data["files"] == []
        assert data["total"] == 0


@pytest.mark.asyncio
class TestActivityEndpoints:
    """Tests for activity endpoints."""

    async def test_list_activity_empty(self, client: AsyncClient):
        """Test listing activity when empty."""
        response = await client.get("/activity")
        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []


@pytest.mark.asyncio
class TestUploadEndpoints:
    """Tests for upload endpoints."""

    async def test_get_upload_status(self, client: AsyncClient):
        """Test getting upload status."""
        response = await client.get("/uploads/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_uploading" in data
        assert "queue_size" in data

    async def test_get_queue_status(self, client: AsyncClient):
        """Test getting queue status."""
        response = await client.get("/uploads/queue")
        assert response.status_code == 200
        data = response.json()
        assert "pending" in data
        assert "in_progress" in data


@pytest.mark.asyncio
class TestServerEndpoints:
    """Tests for server configuration endpoints."""

    async def test_list_servers_empty(self, client: AsyncClient):
        """Test listing servers when empty."""
        response = await client.get("/servers")
        assert response.status_code == 200
        data = response.json()
        assert data["servers"] == []
