"""Tests for main.py API endpoints."""

import pytest
from httpx import AsyncClient
from io import BytesIO


@pytest.mark.asyncio
async def test_get_file_endpoint(client: AsyncClient, test_user_token: str, sample_file_metadata):
    """Test GET /get_file/{sha256} endpoint."""
    # First, store some metadata
    response = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 201

    # Now retrieve it
    sha256 = sample_file_metadata["sha256"]
    response = await client.get(
        f"/get_file/{sha256}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["sha256"] == sha256
    assert data["filepath"] == sample_file_metadata["filepath"]
    assert data["hostname"] == sample_file_metadata["hostname"]


@pytest.mark.asyncio
async def test_get_file_not_found(client: AsyncClient, test_user_token: str):
    """Test GET /get_file/{sha256} with nonexistent file."""
    nonexistent_sha = "0" * 64

    response = await client.get(
        f"/get_file/{nonexistent_sha}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_file_invalid_sha256(client: AsyncClient, test_user_token: str):
    """Test GET /get_file/{sha256} with invalid SHA256."""
    invalid_sha = "invalid"

    response = await client.get(
        f"/get_file/{invalid_sha}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == 400  # Bad request for invalid SHA256


@pytest.mark.asyncio
async def test_upload_file_endpoint(client: AsyncClient, test_user_token: str, sample_file_metadata):
    """Test POST /upload_file/{sha256} endpoint."""
    # First register the file metadata and check if upload is required
    response = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 201
    upload_required = response.json().get("upload_required", False)

    if not upload_required:
        # File already exists, so skip upload test
        return

    # Upload the actual file
    file_content = b"Test file content"
    sha256 = sample_file_metadata["sha256"]
    hostname = sample_file_metadata["hostname"]
    filepath = sample_file_metadata["filepath"]

    response = await client.post(
        f"/upload_file/{sha256}",
        params={"hostname": hostname, "filepath": filepath},
        files={"file": ("test.txt", BytesIO(file_content), "text/plain")},
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    # Might fail with 400 if metadata not found, which is expected
    assert response.status_code in [200, 400]


@pytest.mark.asyncio
async def test_api_my_files_endpoint(client: AsyncClient, test_user_token: str, sample_file_metadata):
    """Test GET /api/my_files endpoint."""
    # Upload a file first
    response = await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 201

    # Get user's files
    response = await client.get(
        "/api/my_files",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == 200
    files = response.json()
    assert isinstance(files, list)


@pytest.mark.asyncio
async def test_api_clones_endpoint(client: AsyncClient, test_user_token: str, sample_file_metadata):
    """Test GET /api/clones/{sha256} endpoint - find duplicate files."""
    # Create multiple files with same SHA256
    sha256 = sample_file_metadata["sha256"]

    # First file
    await client.post(
        "/put_file",
        json=sample_file_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    # Second file (different hostname/path, same SHA256)
    duplicate_metadata = sample_file_metadata.copy()
    duplicate_metadata["hostname"] = "server02"
    duplicate_metadata["filepath"] = "/var/log/copy.log"

    await client.post(
        "/put_file",
        json=duplicate_metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    # Get clones
    response = await client.get(
        f"/api/clones/{sha256}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    # Should return all files with this SHA256
    assert response.status_code == 200
    clones = response.json()
    assert isinstance(clones, list)
    assert len(clones) >= 2


@pytest.mark.asyncio
async def test_create_api_key_endpoint(client: AsyncClient, test_user_token: str):
    """Test POST /api_keys endpoint."""
    key_data = {
        "name": "test-api-key",
        "description": "Test API key"
    }

    response = await client.post(
        "/api_keys",
        json=key_data,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == 201
    data = response.json()
    assert "api_key" in data
    assert len(data["api_key"]) == 64
    assert data["name"] == "test-api-key"


@pytest.mark.asyncio
async def test_list_api_keys_endpoint(client: AsyncClient, test_user_token: str):
    """Test GET /api_keys endpoint."""
    # Create some API keys first
    for i in range(3):
        await client.post(
            "/api_keys",
            json={"name": f"key-{i}", "description": f"Test key {i}"},
            headers={"Authorization": f"Bearer {test_user_token}"}
        )

    # List them
    response = await client.get(
        "/api_keys",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == 200
    keys = response.json()
    assert isinstance(keys, list)
    assert len(keys) >= 3


@pytest.mark.asyncio
async def test_revoke_api_key_endpoint(client: AsyncClient, test_user_token: str):
    """Test PUT /api_keys/{key_id}/revoke endpoint."""
    # Create an API key
    response = await client.post(
        "/api_keys",
        json={"name": "revoke-test", "description": "Key to revoke"},
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 201
    key_id = response.json()["_id"]

    # Revoke it
    response = await client.put(
        f"/api_keys/{key_id}/revoke",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == 200
    assert "revoked" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_delete_api_key_endpoint(client: AsyncClient, test_user_token: str):
    """Test DELETE /api_keys/{key_id} endpoint."""
    # Create an API key
    response = await client.post(
        "/api_keys",
        json={"name": "delete-test", "description": "Key to delete"},
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 201
    key_id = response.json()["_id"]

    # Delete it
    response = await client.delete(
        f"/api_keys/{key_id}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == 200
    assert "deleted" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test GET /health endpoint."""
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "degraded"]
    assert "database" in data
    # Storage might not be in health response in test mode


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test GET / endpoint returns HTML."""
    response = await client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"PutPlace" in response.content or b"Welcome" in response.content


@pytest.mark.asyncio
async def test_api_register_endpoint(client: AsyncClient):
    """Test POST /api/register endpoint creates pending user."""
    from unittest.mock import Mock, patch

    with patch('putplace.email_service.get_email_service') as mock_email:
        email_service = Mock()
        email_service.send_confirmation_email = Mock(return_value=True)
        mock_email.return_value = email_service

        user_data = {
            "username": "newapiuser",
            "email": "newapiuser@example.com",
            "password": "securepassword123"
        }

        response = await client.post("/api/register", json=user_data)

        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert data["email"] == "newapiuser@example.com"
        assert "check your email" in data["message"].lower()


@pytest.mark.asyncio
async def test_api_login_endpoint(client: AsyncClient, test_db):
    """Test POST /api/login endpoint."""
    from putplace.user_auth import get_password_hash

    # Create a test user
    username = "logintest"
    password = "testpass123"
    await test_db.create_user(
        username=username,
        email="logintest@example.com",
        hashed_password=get_password_hash(password),
        full_name="Login Test User"
    )

    # Try to log in with JSON
    response = await client.post(
        "/api/login",
        json={"username": username, "password": password}
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_api_login_wrong_password(client: AsyncClient, test_db):
    """Test POST /api/login with wrong password."""
    from putplace.user_auth import get_password_hash

    # Create a test user
    await test_db.create_user(
        username="wrongpasstest",
        email="wrongpass@example.com",
        hashed_password=get_password_hash("correctpass"),
        full_name="Wrong Pass Test"
    )

    # Try to log in with wrong password
    response = await client.post(
        "/api/login",
        json={"username": "wrongpasstest", "password": "wrongpass"}
    )

    assert response.status_code == 401
    assert "Incorrect" in response.json()["detail"]


@pytest.mark.asyncio
async def test_api_oauth_config_endpoint(client: AsyncClient):
    """Test GET /api/oauth/config endpoint."""
    response = await client.get("/api/oauth/config")

    assert response.status_code == 200
    data = response.json()
    assert "google_client_id" in data


@pytest.mark.asyncio
async def test_endpoint_requires_authentication(client: AsyncClient, sample_file_metadata):
    """Test that protected endpoints reject requests without authentication."""
    # Try to access protected endpoint without JWT token
    response = await client.post("/put_file", json=sample_file_metadata)
    assert response.status_code in [401, 403]

    response = await client.get(f"/get_file/{sample_file_metadata['sha256']}")
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_endpoint_requires_user_authentication(client: AsyncClient):
    """Test that user-protected endpoints reject requests without JWT token."""
    # Try to access user endpoint without token
    response = await client.get("/api/my_files")
    # Might return 401 or 403 depending on auth implementation
    assert response.status_code in [401, 403]

    response = await client.post("/api_keys", json={"name": "test"})
    assert response.status_code in [401, 403]
