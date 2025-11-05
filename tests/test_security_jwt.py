"""Tests for JWT secret key security."""

import os
import pytest
from unittest.mock import patch

from putplace.user_auth import get_jwt_secret_key, create_access_token, decode_access_token


def test_jwt_secret_key_from_env():
    """Test that JWT secret is loaded from environment."""
    test_secret = "test-secret-key-for-testing"

    with patch.dict(os.environ, {"PUTPLACE_JWT_SECRET_KEY": test_secret}):
        # Need to reload settings to pick up env var
        from putplace import config
        config.settings.jwt_secret_key = test_secret

        secret = get_jwt_secret_key()
        assert secret == test_secret


def test_jwt_secret_key_missing_raises_error():
    """Test that missing JWT secret raises RuntimeError."""
    with patch.dict(os.environ, {}, clear=True):
        # Clear the jwt_secret_key in settings
        from putplace import config
        config.settings.jwt_secret_key = None

        with pytest.raises(RuntimeError) as exc_info:
            get_jwt_secret_key()

        assert "JWT secret key not configured" in str(exc_info.value)
        assert "PUTPLACE_JWT_SECRET_KEY" in str(exc_info.value)


def test_create_token_with_secret():
    """Test token creation with configured secret."""
    test_secret = "test-secret-key-for-testing-creation"

    with patch.dict(os.environ, {"PUTPLACE_JWT_SECRET_KEY": test_secret}):
        from putplace import config
        config.settings.jwt_secret_key = test_secret

        token = create_access_token(data={"sub": "testuser"})
        assert isinstance(token, str)
        assert len(token) > 0


def test_decode_token_with_secret():
    """Test token decoding with configured secret."""
    test_secret = "test-secret-key-for-testing-decode"

    with patch.dict(os.environ, {"PUTPLACE_JWT_SECRET_KEY": test_secret}):
        from putplace import config
        config.settings.jwt_secret_key = test_secret

        # Create and decode token
        token = create_access_token(data={"sub": "testuser"})
        username = decode_access_token(token)

        assert username == "testuser"


def test_token_with_different_secrets_fails():
    """Test that token created with one secret cannot be decoded with another."""
    secret1 = "first-secret-key"
    secret2 = "second-secret-key"

    # Create token with secret1
    with patch.dict(os.environ, {"PUTPLACE_JWT_SECRET_KEY": secret1}):
        from putplace import config
        config.settings.jwt_secret_key = secret1
        token = create_access_token(data={"sub": "testuser"})

    # Try to decode with secret2
    with patch.dict(os.environ, {"PUTPLACE_JWT_SECRET_KEY": secret2}):
        from putplace import config
        config.settings.jwt_secret_key = secret2
        username = decode_access_token(token)

        # Should return None (invalid token)
        assert username is None


def test_token_expiration():
    """Test that token expiration is set."""
    from datetime import timedelta
    test_secret = "test-secret-key-for-expiration"

    with patch.dict(os.environ, {"PUTPLACE_JWT_SECRET_KEY": test_secret}):
        from putplace import config
        config.settings.jwt_secret_key = test_secret

        # Create token with custom expiration
        token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(minutes=5)
        )

        # Decode should work immediately
        username = decode_access_token(token)
        assert username == "testuser"


def test_invalid_token_format():
    """Test that invalid token format returns None."""
    test_secret = "test-secret-key-for-invalid"

    with patch.dict(os.environ, {"PUTPLACE_JWT_SECRET_KEY": test_secret}):
        from putplace import config
        config.settings.jwt_secret_key = test_secret

        # Try to decode invalid token
        username = decode_access_token("not.a.valid.jwt.token")
        assert username is None


def test_empty_token():
    """Test that empty token returns None."""
    test_secret = "test-secret-key-for-empty"

    with patch.dict(os.environ, {"PUTPLACE_JWT_SECRET_KEY": test_secret}):
        from putplace import config
        config.settings.jwt_secret_key = test_secret

        username = decode_access_token("")
        assert username is None
