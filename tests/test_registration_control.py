"""Tests for registration enable/disable control."""

import pytest
from httpx import AsyncClient
from putplace.config import Settings


@pytest.mark.asyncio
async def test_registration_enabled_by_default(client: AsyncClient):
    """Test that registration is enabled by default."""
    from unittest.mock import Mock, patch

    with patch('putplace.email_service.get_email_service') as mock_email:
        email_service = Mock()
        email_service.send_confirmation_email = Mock(return_value=True)
        mock_email.return_value = email_service

        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpassword123"
        }

        response = await client.post("/api/register", json=user_data)
        assert response.status_code == 200
        data = response.json()
        assert "check your email" in data["message"].lower()


@pytest.mark.asyncio
async def test_registration_disabled(client: AsyncClient):
    """Test that registration can be disabled."""
    from putplace.main import app, settings

    # Temporarily disable registration
    original_value = settings.registration_enabled
    settings.registration_enabled = False

    try:
        user_data = {
            "username": "blockeduser",
            "email": "blocked@example.com",
            "password": "password123"
        }

        response = await client.post("/api/register", json=user_data)
        assert response.status_code == 403
        data = response.json()
        assert "registration is currently disabled" in data["detail"].lower()
    finally:
        # Restore original value
        settings.registration_enabled = original_value


@pytest.mark.asyncio
async def test_registration_can_be_reenabled(client: AsyncClient):
    """Test that registration can be disabled and re-enabled."""
    from unittest.mock import Mock, patch
    from putplace.main import settings

    original_value = settings.registration_enabled

    try:
        # First disable registration
        settings.registration_enabled = False

        user_data = {
            "username": "testuser1",
            "email": "test1@example.com",
            "password": "password123"
        }

        response = await client.post("/api/register", json=user_data)
        assert response.status_code == 403

        # Now re-enable registration
        settings.registration_enabled = True

        with patch('putplace.email_service.get_email_service') as mock_email:
            email_service = Mock()
            email_service.send_confirmation_email = Mock(return_value=True)
            mock_email.return_value = email_service

            user_data2 = {
                "username": "testuser2",
                "email": "test2@example.com",
                "password": "password123"
            }

            response2 = await client.post("/api/register", json=user_data2)
            assert response2.status_code == 200
            data = response2.json()
            assert "check your email" in data["message"].lower()
    finally:
        settings.registration_enabled = original_value


def test_registration_enabled_setting_from_env(monkeypatch):
    """Test that registration_enabled can be set via environment variable."""
    # Set environment variable
    monkeypatch.setenv("REGISTRATION_ENABLED", "false")

    # Create new settings instance
    settings = Settings()

    assert settings.registration_enabled is False


def test_registration_enabled_default_value():
    """Test that registration_enabled defaults to True."""
    settings = Settings()
    assert settings.registration_enabled is True
