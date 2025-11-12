"""Tests for email confirmation functionality."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from putplace.email_tokens import (
    generate_confirmation_token,
    calculate_expiration_time,
    is_token_expired
)
from putplace.models import UserCreate


class TestEmailTokens:
    """Test email token generation and validation."""

    def test_generate_confirmation_token(self):
        """Test token generation creates unique tokens."""
        token1 = generate_confirmation_token()
        token2 = generate_confirmation_token()

        assert len(token1) > 40  # Should be substantial length
        assert len(token2) > 40
        assert token1 != token2  # Should be unique

    def test_calculate_expiration_time_default(self):
        """Test expiration time calculation with default 24 hours."""
        now = datetime.utcnow()
        expires_at = calculate_expiration_time()

        # Should be approximately 24 hours from now
        diff = expires_at - now
        assert 23.9 < diff.total_seconds() / 3600 < 24.1

    def test_calculate_expiration_time_custom(self):
        """Test expiration time calculation with custom hours."""
        now = datetime.utcnow()
        expires_at = calculate_expiration_time(hours=48)

        # Should be approximately 48 hours from now
        diff = expires_at - now
        assert 47.9 < diff.total_seconds() / 3600 < 48.1

    def test_is_token_expired_not_expired(self):
        """Test token expiration check for non-expired token."""
        future_time = datetime.utcnow() + timedelta(hours=1)
        assert not is_token_expired(future_time)

    def test_is_token_expired_expired(self):
        """Test token expiration check for expired token."""
        past_time = datetime.utcnow() - timedelta(hours=1)
        assert is_token_expired(past_time)

    def test_is_token_expired_exactly_now(self):
        """Test token expiration check for exactly current time."""
        now = datetime.utcnow()
        # Equal times should be considered expired
        assert is_token_expired(now)


@pytest.mark.asyncio
class TestRegistrationWithEmailConfirmation:
    """Test user registration with email confirmation."""

    @pytest.fixture
    async def mock_email_service(self):
        """Mock email service."""
        with patch('putplace.email_service.get_email_service') as mock:
            email_service = Mock()
            email_service.send_confirmation_email = Mock(return_value=True)
            mock.return_value = email_service
            yield email_service

    async def test_register_creates_pending_user(self, client, test_db, mock_email_service):
        """Test registration creates pending user instead of active user."""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "testpassword123",
            "full_name": "New User"
        }

        response = await client.post("/api/register", json=user_data)

        assert response.status_code == 200
        data = response.json()
        assert "check your email" in data["message"].lower()
        assert data["email"] == user_data["email"]
        assert data["expires_in_hours"] == 24

        # Verify email was sent
        mock_email_service.send_confirmation_email.assert_called_once()

        # Verify pending user was created
        pending_user = await test_db.pending_users_collection.find_one({"email": user_data["email"]})
        assert pending_user is not None
        assert pending_user["username"] == user_data["username"]
        assert "confirmation_token" in pending_user

        # Verify actual user was NOT created
        actual_user = await test_db.users_collection.find_one({"email": user_data["email"]})
        assert actual_user is None

    async def test_register_duplicate_email_rejected(self, client, test_db, mock_email_service):
        """Test registration with duplicate email is rejected."""
        # Create first user
        user_data = {
            "username": "user1",
            "email": "duplicate@example.com",
            "password": "password123"
        }
        response1 = await client.post("/api/register", json=user_data)
        assert response1.status_code == 200

        # Try to register with same email
        user_data2 = {
            "username": "user2",
            "email": "duplicate@example.com",
            "password": "password456"
        }
        response2 = await client.post("/api/register", json=user_data2)
        assert response2.status_code == 400
        assert "already registered" in response2.json()["detail"].lower()

    async def test_register_email_send_failure_rolls_back(self, client, test_db):
        """Test registration rolls back if email fails to send."""
        with patch('putplace.email_service.get_email_service') as mock_email:
            email_service = Mock()
            email_service.send_confirmation_email = Mock(return_value=False)
            mock_email.return_value = email_service

            user_data = {
                "username": "failuser",
                "email": "fail@example.com",
                "password": "password123"
            }

            response = await client.post("/api/register", json=user_data)

            assert response.status_code == 500
            assert "failed to send" in response.json()["detail"].lower()

            # Verify pending user was NOT created (rolled back)
            pending_user = await test_db.pending_users_collection.find_one({"email": user_data["email"]})
            assert pending_user is None


@pytest.mark.asyncio
class TestEmailConfirmation:
    """Test email confirmation endpoint."""

    async def test_confirm_email_success(self, client, test_db):
        """Test successful email confirmation activates account."""
        # Create pending user
        from putplace.user_auth import get_password_hash
        from putplace.email_tokens import generate_confirmation_token, calculate_expiration_time

        token = generate_confirmation_token()
        hashed_password = get_password_hash("testpass123")

        await test_db.create_pending_user(
            username="pendinguser",
            email="pending@example.com",
            hashed_password=hashed_password,
            confirmation_token=token,
            expires_at=calculate_expiration_time(hours=24),
            full_name="Pending User"
        )

        # Confirm email
        response = await client.get(f"/api/confirm-email?token={token}")

        assert response.status_code == 200
        data = response.json()
        assert "confirmed successfully" in data["message"].lower()
        assert data["username"] == "pendinguser"
        assert data["email"] == "pending@example.com"

        # Verify actual user was created
        actual_user = await test_db.users_collection.find_one({"email": "pending@example.com"})
        assert actual_user is not None
        assert actual_user["username"] == "pendinguser"
        assert actual_user["is_active"] is True

        # Verify pending user was deleted
        pending_user = await test_db.pending_users_collection.find_one({"confirmation_token": token})
        assert pending_user is None

    async def test_confirm_email_invalid_token(self, client):
        """Test email confirmation with invalid token."""
        response = await client.get("/api/confirm-email?token=invalid-token-12345")

        assert response.status_code == 404
        assert "invalid or expired" in response.json()["detail"].lower()

    async def test_confirm_email_expired_token(self, client, test_db):
        """Test email confirmation with expired token."""
        # Create pending user with expired token
        from putplace.user_auth import get_password_hash
        from putplace.email_tokens import generate_confirmation_token
        from datetime import datetime

        token = generate_confirmation_token()
        hashed_password = get_password_hash("testpass123")

        # Set expiration to 1 hour ago
        expired_time = datetime.utcnow() - timedelta(hours=1)

        await test_db.create_pending_user(
            username="expireduser",
            email="expired@example.com",
            hashed_password=hashed_password,
            confirmation_token=token,
            expires_at=expired_time
        )

        # Try to confirm
        response = await client.get(f"/api/confirm-email?token={token}")

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

        # Verify pending user was deleted
        pending_user = await test_db.pending_users_collection.find_one({"confirmation_token": token})
        assert pending_user is None

        # Verify actual user was NOT created
        actual_user = await test_db.users_collection.find_one({"email": "expired@example.com"})
        assert actual_user is None

    async def test_confirm_email_can_login_after_confirmation(self, client, test_db):
        """Test user can login after confirming email."""
        # Create pending user
        from putplace.user_auth import get_password_hash
        from putplace.email_tokens import generate_confirmation_token, calculate_expiration_time

        token = generate_confirmation_token()
        password = "logintest123"
        hashed_password = get_password_hash(password)

        await test_db.create_pending_user(
            username="loginuser",
            email="login@example.com",
            hashed_password=hashed_password,
            confirmation_token=token,
            expires_at=calculate_expiration_time(hours=24)
        )

        # Confirm email
        confirm_response = await client.get(f"/api/confirm-email?token={token}")
        assert confirm_response.status_code == 200

        # Try to login
        login_response = await client.post("/api/login", json={
            "username": "loginuser",
            "password": password
        })

        assert login_response.status_code == 200
        assert "access_token" in login_response.json()


@pytest.mark.asyncio
class TestPendingUserCleanup:
    """Test cleanup of expired pending users."""

    async def test_cleanup_expired_pending_users(self, test_db):
        """Test cleanup deletes expired pending users."""
        from putplace.user_auth import get_password_hash
        from putplace.email_tokens import generate_confirmation_token
        from datetime import datetime

        hashed_password = get_password_hash("testpass123")

        # Create expired pending user
        expired_token = generate_confirmation_token()
        expired_time = datetime.utcnow() - timedelta(hours=25)

        await test_db.create_pending_user(
            username="expiredcleanup",
            email="expiredcleanup@example.com",
            hashed_password=hashed_password,
            confirmation_token=expired_token,
            expires_at=expired_time
        )

        # Create valid pending user
        valid_token = generate_confirmation_token()
        valid_time = datetime.utcnow() + timedelta(hours=23)

        await test_db.create_pending_user(
            username="validpending",
            email="validpending@example.com",
            hashed_password=hashed_password,
            confirmation_token=valid_token,
            expires_at=valid_time
        )

        # Run cleanup
        deleted_count = await test_db.cleanup_expired_pending_users()

        assert deleted_count == 1

        # Verify expired user was deleted
        expired_user = await test_db.pending_users_collection.find_one({"confirmation_token": expired_token})
        assert expired_user is None

        # Verify valid user still exists
        valid_user = await test_db.pending_users_collection.find_one({"confirmation_token": valid_token})
        assert valid_user is not None

    async def test_cleanup_no_expired_users(self, test_db):
        """Test cleanup returns 0 when no expired users."""
        deleted_count = await test_db.cleanup_expired_pending_users()
        assert deleted_count == 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestEmailConfirmationIntegration:
    """Integration tests for complete email confirmation flow."""

    async def test_complete_registration_flow(self, client, test_db):
        """Test complete flow: register -> confirm -> login."""
        with patch('putplace.email_service.get_email_service') as mock_email:
            email_service = Mock()
            captured_token = None

            def capture_token(recipient_email, username, confirmation_token):
                nonlocal captured_token
                captured_token = confirmation_token
                return True

            email_service.send_confirmation_email = Mock(side_effect=capture_token)
            mock_email.return_value = email_service

            # Step 1: Register
            user_data = {
                "username": "flowtest",
                "email": "flowtest@example.com",
                "password": "flowpassword123",
                "full_name": "Flow Test User"
            }

            register_response = await client.post("/api/register", json=user_data)
            assert register_response.status_code == 200

            # Verify token was captured
            assert captured_token is not None

            # Step 2: Confirm email
            confirm_response = await client.get(f"/api/confirm-email?token={captured_token}")
            assert confirm_response.status_code == 200

            # Step 3: Login
            login_response = await client.post("/api/login", json={
                "username": user_data["username"],
                "password": user_data["password"]
            })
            assert login_response.status_code == 200
            assert "access_token" in login_response.json()
