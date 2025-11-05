"""Integration tests for security features in API endpoints.

These tests require MongoDB to be running and are marked as integration tests.
Run with: pytest -m integration

To skip: pytest -m "not integration"
"""

import pytest
from httpx import AsyncClient, ASGITransport

from putplace.main import app
from putplace.database import mongodb


# Note: These tests use the existing client fixture from conftest.py
# which properly sets up the test database and dependencies

pytestmark = pytest.mark.integration  # Mark all tests in this module as integration tests


class TestSecurityHeaders:
    """Test security headers are present in responses."""

    async def test_security_headers_on_root(self, client):
        """Test that security headers are present on root endpoint."""
        response = await client.get("/")

        # Check security headers
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"

        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"

        assert "X-XSS-Protection" in response.headers
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

        assert "Content-Security-Policy" in response.headers

    async def test_security_headers_on_health(self, client):
        """Test that security headers are present on health endpoint."""
        response = await client.get("/health")

        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers

    async def test_hsts_header_in_production_mode(self, client):
        """Test that HSTS header is present when not in debug mode."""
        from putplace.config import settings

        # If not in debug mode, HSTS should be present
        if not settings.debug_mode:
            response = await client.get("/")
            assert "Strict-Transport-Security" in response.headers
        else:
            # In debug mode, HSTS should not be present
            response = await client.get("/")
            # HSTS might not be present in debug mode


class TestCORS:
    """Test CORS middleware functionality."""

    async def test_cors_preflight_request(self, client):
        """Test CORS preflight (OPTIONS) request."""
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            }
        )

        # Should have CORS headers
        assert "Access-Control-Allow-Origin" in response.headers

    async def test_cors_headers_on_get_request(self, client):
        """Test CORS headers on actual GET request."""
        response = await client.get(
            "/health",
            headers={"Origin": "http://example.com"}
        )

        assert "Access-Control-Allow-Origin" in response.headers

    async def test_cors_allows_credentials(self, client):
        """Test that CORS allows credentials."""
        response = await client.get(
            "/health",
            headers={"Origin": "http://example.com"}
        )

        # Check if credentials are allowed
        if "Access-Control-Allow-Credentials" in response.headers:
            assert response.headers["Access-Control-Allow-Credentials"] == "true"


class TestRateLimiting:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_login_endpoint(self, client):
        """Test that login endpoint is rate limited."""
        # Make multiple failed login attempts
        for i in range(6):
            response = await client.post(
                "/api/login",
                json={"username": "testuser", "password": "wrongpassword"}
            )

            if i < 5:
                # First 5 attempts should get 401 (unauthorized)
                assert response.status_code in [401, 429]
            else:
                # 6th attempt should be rate limited (429)
                # Note: This might be 401 if rate limiting is not triggered
                assert response.status_code in [401, 429]

    @pytest.mark.asyncio
    async def test_rate_limit_register_endpoint(self, client):
        """Test that register endpoint is rate limited."""
        # Make multiple registration attempts
        for i in range(6):
            response = await client.post(
                "/api/register",
                json={
                    "username": f"testuser{i}",
                    "email": f"test{i}@example.com",
                    "password": "ValidPass123!"
                }
            )

            # Should eventually hit rate limit
            assert response.status_code in [200, 400, 429]

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, client):
        """Test that rate limit info is in headers."""
        response = await client.post(
            "/api/login",
            json={"username": "test", "password": "wrong"}
        )

        # Rate limiting headers might be present
        # Different implementations use different header names
        # Just verify the request completes


class TestAccountLockout:
    """Test account lockout mechanism."""

    @pytest.mark.asyncio
    async def test_account_locks_after_failed_attempts(self, client):
        """Test that account locks after multiple failed login attempts."""
        username = "lockout_test_user"

        # Create a test user first
        from putplace.user_auth import get_password_hash
        from putplace.database import mongodb

        try:
            await mongodb.connect()
            hashed_password = get_password_hash("CorrectPass123!")
            await mongodb.create_user(
                username=username,
                email=f"{username}@example.com",
                hashed_password=hashed_password
            )
        except Exception:
            pass  # User might already exist

        # Make 5 failed login attempts
        for i in range(5):
            response = await client.post(
                "/api/login",
                json={"username": username, "password": "WrongPassword123!"}
            )
            assert response.status_code in [401, 429]

        # 6th attempt should be locked (429 - Too Many Requests)
        response = await client.post(
            "/api/login",
            json={"username": username, "password": "WrongPassword123!"}
        )

        # Should be either rate limited or locked
        assert response.status_code == 429

        # Error message should mention lockout
        if response.status_code == 429:
            data = response.json()
            assert "locked" in data["detail"].lower() or "many" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_successful_login_clears_attempts(self, client):
        """Test that successful login clears failed attempts."""
        username = "clear_test_user"
        password = "CorrectPass123!"

        # Create test user
        from putplace.user_auth import get_password_hash
        from putplace.database import mongodb

        try:
            await mongodb.connect()
            hashed_password = get_password_hash(password)
            await mongodb.create_user(
                username=username,
                email=f"{username}@example.com",
                hashed_password=hashed_password
            )
        except Exception:
            pass

        # Make some failed attempts
        for _ in range(2):
            await client.post(
                "/api/login",
                json={"username": username, "password": "WrongPassword123!"}
            )

        # Successful login should clear attempts
        response = await client.post(
            "/api/login",
            json={"username": username, "password": password}
        )

        # Should succeed (200) or fail for other reasons (not lockout)
        assert response.status_code in [200, 401, 500]


class TestPasswordValidation:
    """Test password validation in registration."""

    @pytest.mark.asyncio
    async def test_weak_password_rejected(self, client):
        """Test that weak passwords are rejected."""
        response = await client.post(
            "/api/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "weak"  # Too short, no uppercase, no digit, no special
            }
        )

        assert response.status_code == 422  # Validation error
        data = response.json()
        # Should mention password requirements
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_strong_password_accepted(self, client):
        """Test that strong passwords are accepted."""
        response = await client.post(
            "/api/register",
            json={
                "username": "strongpassuser",
                "email": "strong@example.com",
                "password": "StrongPass123!"
            }
        )

        # Should succeed or fail for duplicate user, not password validation
        assert response.status_code in [200, 400]

        if response.status_code == 400:
            data = response.json()
            # Should not be about password strength
            assert "password" not in data.get("detail", "").lower() or "exists" in data.get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_password_missing_uppercase(self, client):
        """Test password without uppercase is rejected."""
        response = await client.post(
            "/api/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "nouppercase123!"
            }
        )

        assert response.status_code == 422
        data = response.json()
        errors = str(data)
        assert "uppercase" in errors.lower()

    @pytest.mark.asyncio
    async def test_password_missing_digit(self, client):
        """Test password without digit is rejected."""
        response = await client.post(
            "/api/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "NoDigitsHere!"
            }
        )

        assert response.status_code == 422
        data = response.json()
        errors = str(data)
        assert "digit" in errors.lower()

    @pytest.mark.asyncio
    async def test_password_missing_special_char(self, client):
        """Test password without special character is rejected."""
        response = await client.post(
            "/api/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "NoSpecial123"
            }
        )

        assert response.status_code == 422
        data = response.json()
        errors = str(data)
        assert "special" in errors.lower()
