"""Tests for security configuration."""

import pytest

from putplace.config import sanitize_mongodb_url


def test_sanitize_mongodb_url_with_password():
    """Test that passwords are sanitized in MongoDB URLs."""
    url = "mongodb://user:password123@localhost:27017/dbname"
    sanitized = sanitize_mongodb_url(url)

    assert "password123" not in sanitized
    assert "****" in sanitized
    assert "user" in sanitized
    assert "localhost:27017" in sanitized
    assert sanitized == "mongodb://user:****@localhost:27017/dbname"


def test_sanitize_mongodb_url_with_special_chars_in_password():
    """Test sanitization with special characters in password."""
    url = "mongodb://admin:P@ssw0rd!#$@localhost:27017/mydb"
    sanitized = sanitize_mongodb_url(url)

    assert "P@ssw0rd!#$" not in sanitized
    assert "****" in sanitized
    assert "admin" in sanitized
    assert sanitized == "mongodb://admin:****@localhost:27017/mydb"


def test_sanitize_mongodb_url_without_password():
    """Test that URLs without passwords are unchanged."""
    url = "mongodb://localhost:27017/dbname"
    sanitized = sanitize_mongodb_url(url)

    assert sanitized == url


def test_sanitize_mongodb_url_with_replica_set():
    """Test sanitization with replica set URLs."""
    url = "mongodb://user:secret@host1:27017,host2:27017,host3:27017/dbname?replicaSet=rs0"
    sanitized = sanitize_mongodb_url(url)

    assert "secret" not in sanitized
    assert "****" in sanitized
    assert "host1:27017" in sanitized
    assert "replicaSet=rs0" in sanitized


def test_sanitize_mongodb_url_with_srv():
    """Test sanitization with mongodb+srv protocol."""
    url = "mongodb+srv://user:password@cluster.mongodb.net/database"
    sanitized = sanitize_mongodb_url(url)

    assert "password" not in sanitized
    assert "****" in sanitized
    # Note: The regex works with mongodb:// but might need adjustment for mongodb+srv://
    # This test documents current behavior


def test_sanitize_mongodb_url_multiple_colons():
    """Test sanitization when password contains colons."""
    url = "mongodb://user:pass:word:123@localhost:27017/db"
    sanitized = sanitize_mongodb_url(url)

    # Should sanitize the first password field
    assert "pass:word:123" not in sanitized
    assert "****" in sanitized


def test_sanitize_mongodb_url_empty():
    """Test sanitization with empty URL."""
    url = ""
    sanitized = sanitize_mongodb_url(url)
    assert sanitized == url


def test_sanitize_mongodb_url_no_auth():
    """Test URLs without authentication section."""
    url = "mongodb://localhost:27017"
    sanitized = sanitize_mongodb_url(url)
    assert sanitized == url


def test_sanitize_mongodb_url_with_options():
    """Test sanitization preserves query options."""
    url = "mongodb://admin:secret123@localhost:27017/db?authSource=admin&retryWrites=true"
    sanitized = sanitize_mongodb_url(url)

    assert "secret123" not in sanitized
    assert "****" in sanitized
    assert "authSource=admin" in sanitized
    assert "retryWrites=true" in sanitized


def test_config_settings_defaults():
    """Test that security settings have sensible defaults."""
    from putplace.config import Settings

    settings = Settings()

    # JWT settings
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_token_expire_minutes == 30

    # CORS settings
    assert settings.cors_allow_origins == "*"
    assert settings.cors_allow_credentials is True
    assert settings.cors_allow_methods == "GET,POST,PUT,DELETE,OPTIONS"

    # Rate limiting
    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_login == "5/minute"
    assert settings.rate_limit_api == "100/minute"

    # Application settings
    assert settings.debug_mode is False


def test_config_cors_origins_splitting():
    """Test that CORS origins can be properly split."""
    from putplace.config import Settings

    # Test with multiple origins
    settings = Settings(cors_allow_origins="https://app.com,https://admin.com")

    origins = settings.cors_allow_origins.split(",")
    assert len(origins) == 2
    assert "https://app.com" in origins
    assert "https://admin.com" in origins


def test_config_cors_wildcard():
    """Test that CORS wildcard is preserved."""
    from putplace.config import Settings

    settings = Settings(cors_allow_origins="*")
    assert settings.cors_allow_origins == "*"
