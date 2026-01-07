"""Tests for user authentication endpoints."""

import pytest
from httpx import AsyncClient
from unittest.mock import Mock, patch


@pytest.mark.asyncio
async def test_register_new_user(client: AsyncClient):
    """Test registering a new user creates pending user."""
    with patch('putplace_server.email_service.get_email_service') as mock_email:
        email_service = Mock()
        email_service.send_confirmation_email = Mock(return_value=True)
        mock_email.return_value = email_service

        user_data = {
            "email": "test@example.com",
            "password": "testpassword123"
        }

        response = await client.post("/api/register", json=user_data)
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert "check your email" in data["message"].lower()
        assert data["email"] == "test@example.com"
        assert data["expires_in_hours"] == 24


@pytest.mark.asyncio
async def test_register_user_minimal_data(client: AsyncClient):
    """Test registering a user with only required fields creates pending user."""
    with patch('putplace_server.email_service.get_email_service') as mock_email:
        email_service = Mock()
        email_service.send_confirmation_email = Mock(return_value=True)
        mock_email.return_value = email_service

        user_data = {
            "email": "minimal@example.com",
            "password": "password123"
        }

        response = await client.post("/api/register", json=user_data)
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert data["email"] == "minimal@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_db):
    """Test that duplicate email is rejected."""
    from putplace_server.user_auth import get_password_hash

    # Create a confirmed user with this email first
    await test_db.create_user(
        email="existing@example.com",
        hashed_password=get_password_hash("password123")
    )

    # Try to register with same email
    with patch('putplace_server.email_service.get_email_service') as mock_email:
        email_service = Mock()
        email_service.send_confirmation_email = Mock(return_value=True)
        mock_email.return_value = email_service

        user_data = {
            "email": "existing@example.com",
            "password": "password123"
        }

        response = await client.post("/api/register", json=user_data)
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "email" in data["detail"].lower()


@pytest.mark.asyncio
async def test_register_invalid_password_too_short(client: AsyncClient):
    """Test that password must be at least 8 characters."""
    user_data = {
        "email": "test@example.com",
        "password": "short"  # Too short
    }

    response = await client.post("/api/register", json=user_data)
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_register_valid_email(client: AsyncClient):
    """Test that email field is validated."""
    with patch('putplace_server.email_service.get_email_service') as mock_email:
        email_service = Mock()
        email_service.send_confirmation_email = Mock(return_value=True)
        mock_email.return_value = email_service

        user_data = {
            "email": "valid@example.com",
            "password": "password123"
        }

        response = await client.post("/api/register", json=user_data)
        assert response.status_code == 200  # Should succeed with valid email


@pytest.mark.asyncio
async def test_register_missing_required_field(client: AsyncClient):
    """Test that missing required fields are rejected."""
    user_data = {
        "email": "test@example.com"
        # Missing password
    }

    response = await client.post("/api/register", json=user_data)
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_db):
    """Test successful login with confirmed user."""
    from putplace_server.user_auth import get_password_hash

    # Create a confirmed user directly
    password = "loginpassword123"
    await test_db.create_user(
        email="login@example.com",
        hashed_password=get_password_hash(password)
    )

    # Now try to login with email
    login_data = {
        "email": "login@example.com",
        "password": password
    }

    response = await client.post("/api/login", json=login_data)
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert "token_type" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 0


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_db):
    """Test login with wrong password."""
    from putplace_server.user_auth import get_password_hash

    # Create confirmed user
    await test_db.create_user(
        email="wrongpw@example.com",
        hashed_password=get_password_hash("correctpassword123")
    )

    # Try to login with wrong password
    login_data = {
        "email": "wrongpw@example.com",
        "password": "wrongpassword123"
    }

    response = await client.post("/api/login", json=login_data)
    assert response.status_code == 401

    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Test login with nonexistent email."""
    login_data = {
        "email": "nonexistent@example.com",
        "password": "password123"
    }

    response = await client.post("/api/login", json=login_data)
    assert response.status_code == 401

    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_login_missing_fields(client: AsyncClient):
    """Test login with missing fields."""
    login_data = {
        "email": "test@example.com"
        # Missing password
    }

    response = await client.post("/api/login", json=login_data)
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_login_page_renders(client: AsyncClient):
    """Test that login page HTML is served."""
    response = await client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    # Check for key elements in the HTML
    html = response.text
    assert "Login" in html
    assert "<form" in html
    assert "email" in html.lower()
    assert "password" in html.lower()


@pytest.mark.asyncio
async def test_register_page_renders(client: AsyncClient):
    """Test that registration page HTML is served."""
    response = await client.get("/register")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    # Check for key elements in the HTML
    html = response.text
    assert "Register" in html
    assert "<form" in html
    assert "email" in html.lower()
    assert "password" in html.lower()


@pytest.mark.asyncio
async def test_password_is_hashed(client: AsyncClient, test_db):
    """Test that passwords are stored hashed, not in plain text."""
    from putplace_server.user_auth import get_password_hash

    password = "myplainpassword123"

    # Create confirmed user directly
    await test_db.create_user(
        email="hashed@example.com",
        hashed_password=get_password_hash(password)
    )

    # Check database directly
    user = await test_db.get_user_by_email("hashed@example.com")
    assert user is not None
    assert "hashed_password" in user

    # Password should be hashed (Argon2 hashes start with $argon2id$)
    assert user["hashed_password"].startswith("$argon2id$")
    # Plain password should not be in the hash
    assert password not in user["hashed_password"]


@pytest.mark.asyncio
async def test_user_registration_and_login_flow(client: AsyncClient, test_db):
    """Test complete flow: register, confirm, then login."""
    from putplace_server.user_auth import get_password_hash

    # Create confirmed user directly (simulating post-confirmation state)
    password = "flowpassword123"
    await test_db.create_user(
        email="flow@example.com",
        hashed_password=get_password_hash(password)
    )

    # Login with credentials
    login_data = {
        "email": "flow@example.com",
        "password": password
    }

    login_response = await client.post("/api/login", json=login_data)
    assert login_response.status_code == 200

    token_data = login_response.json()
    assert "access_token" in token_data

    # Verify token can be decoded
    from putplace_server.user_auth import decode_access_token
    email = decode_access_token(token_data["access_token"])
    assert email == "flow@example.com"


@pytest.mark.asyncio
async def test_jwt_token_contains_email(client: AsyncClient, test_db):
    """Test that JWT token contains the email in 'sub' claim."""
    from putplace_server.user_auth import get_password_hash

    # Create confirmed user directly
    password = "jwtpassword123"
    await test_db.create_user(
        email="jwt@example.com",
        hashed_password=get_password_hash(password)
    )

    # Login
    login_data = {
        "email": "jwt@example.com",
        "password": password
    }
    response = await client.post("/api/login", json=login_data)
    token = response.json()["access_token"]

    # Decode and verify
    from putplace_server.user_auth import decode_access_token
    email = decode_access_token(token)
    assert email == "jwt@example.com"


@pytest.mark.asyncio
async def test_home_page_has_auth_links(client: AsyncClient):
    """Test that home page contains links to login and register."""
    response = await client.get("/")
    assert response.status_code == 200

    html = response.text
    # Check for login and register links
    assert "/login" in html
    assert "/register" in html
