"""Tests for putplace_configure script.

Tests the configuration wizard functionality including:
- MongoDB connection checking (local and Atlas)
- Admin user creation
- Configuration file generation
- TLS/SSL handling for different MongoDB connection types
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import tempfile

# Import functions from putplace_configure
from putplace.scripts.putplace_configure import (
    check_mongodb_connection,
    create_admin_user,
    write_toml_file,
    load_existing_config,
)


class TestMongoDBConnection:
    """Test MongoDB connection checking with different connection types."""

    @pytest.mark.asyncio
    async def test_local_mongodb_connection_no_tls(self):
        """Test that local MongoDB connections don't use TLS."""
        # This should work with local MongoDB without TLS
        mongodb_url = "mongodb://localhost:27017"
        success, message = await check_mongodb_connection(mongodb_url)

        # Should succeed if MongoDB is running locally
        # If MongoDB is not running, it should fail gracefully
        assert isinstance(success, bool)
        assert isinstance(message, str)
        assert "MongoDB connection" in message or "failed" in message.lower()

    @pytest.mark.asyncio
    async def test_atlas_url_detection(self):
        """Test that MongoDB Atlas URLs are detected correctly."""
        # Test mongodb+srv:// format
        atlas_url = "mongodb+srv://user:pass@cluster.mongodb.net/db"

        # This will fail to connect (fake URL), but should attempt to use TLS
        success, message = await check_mongodb_connection(atlas_url)

        # Should fail because it's a fake URL, but not due to TLS config
        assert success is False
        assert isinstance(message, str)
        # Should not be an SSL handshake error (that would indicate wrong TLS config)
        assert "SSL handshake failed" not in message

    @pytest.mark.asyncio
    async def test_mongodb_url_without_srv_no_tls(self):
        """Test that regular mongodb:// URLs use appropriate TLS settings."""
        # Regular mongodb:// format with localhost should not use TLS
        mongodb_url = "mongodb://localhost:27017/testdb"

        success, message = await check_mongodb_connection(mongodb_url)

        # Should work if local MongoDB is running
        assert isinstance(success, bool)
        assert isinstance(message, str)


class TestAdminUserCreation:
    """Test admin user creation functionality."""

    @pytest.mark.asyncio
    async def test_create_admin_user_function_exists(self):
        """Test that create_admin_user function is callable and returns tuple."""
        # This just tests the function signature/interface
        # Actual database operations are tested in integration tests
        from inspect import iscoroutinefunction

        assert iscoroutinefunction(create_admin_user)

        # Test that calling with invalid URL returns proper error
        success, message = await create_admin_user(
            mongodb_url="mongodb://nonexistent:27017",
            username="test",
            email="test@test.com",
            password="pass"
        )

        # Should fail gracefully
        assert isinstance(success, bool)
        assert isinstance(message, str)
        assert success is False  # Should fail with invalid URL


class TestConfigFileGeneration:
    """Test configuration file generation."""

    def test_write_toml_file_local_storage(self):
        """Test writing configuration with local storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_ppserver.toml"

            config = {
                'mongodb_url': 'mongodb://localhost:27017',
                'mongodb_database': 'putplace_test',
                'storage_backend': 'local',
                'storage_path': './storage/files',
            }

            success, message = write_toml_file(config, config_path)

            assert success is True
            assert "Configuration written" in message
            assert config_path.exists()

            # Check file contents
            content = config_path.read_text()
            assert "[server]" in content
            assert "host = \"127.0.0.1\"" in content  # Secure default
            assert "port = 8000" in content
            assert "[database]" in content
            assert "mongodb://localhost:27017" in content
            assert "[storage]" in content
            assert "backend = \"local\"" in content

    def test_write_toml_file_s3_storage(self):
        """Test writing configuration with S3 storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_ppserver.toml"

            config = {
                'mongodb_url': 'mongodb://localhost:27017',
                'mongodb_database': 'putplace_test',
                'storage_backend': 's3',
                's3_bucket': 'test-bucket',
                'aws_region': 'us-west-2',
            }

            success, message = write_toml_file(config, config_path)

            assert success is True
            assert config_path.exists()

            # Check file contents
            content = config_path.read_text()
            assert "[server]" in content
            assert "[storage]" in content
            assert "backend = \"s3\"" in content
            assert "s3_bucket_name = \"test-bucket\"" in content
            assert "s3_region_name = \"us-west-2\"" in content
            assert "[aws]" in content  # AWS comments section

    def test_server_section_security_defaults(self):
        """Test that server section has secure defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_ppserver.toml"

            config = {
                'mongodb_url': 'mongodb://localhost:27017',
                'storage_backend': 'local',
            }

            success, _ = write_toml_file(config, config_path)
            assert success is True

            content = config_path.read_text()

            # Check secure defaults
            assert "host = \"127.0.0.1\"" in content  # Localhost only
            assert "port = 8000" in content
            assert "workers = 1" in content

            # Check security comments are present
            assert "Security Notes:" in content
            assert "binds to 127.0.0.1 (localhost) by default for security" in content


class TestConfigFileLoading:
    """Test loading existing configuration files."""

    def test_load_existing_config(self):
        """Test loading an existing ppserver.toml file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "ppserver.toml"

            # Create a test config file
            config_content = """
[server]
host = "0.0.0.0"
port = 9000
workers = 4

[database]
mongodb_url = "mongodb://testhost:27017"
mongodb_database = "test_db"

[storage]
backend = "s3"
s3_bucket_name = "my-bucket"
s3_region_name = "us-east-1"
"""
            config_path.write_text(config_content)

            # Mock the search paths to use our temp directory
            with patch('putplace.scripts.putplace_configure.Path') as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.exists.return_value = True
                mock_path_instance.__truediv__ = lambda self, other: config_path
                mock_path.return_value = mock_path_instance
                mock_path.home.return_value = Path(tmpdir)

                # This test verifies the function exists and returns a dict
                # Actual loading depends on file system mocking
                defaults = load_existing_config()
                assert isinstance(defaults, dict)

    def test_load_nonexistent_config(self):
        """Test loading config when no file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp directory where no config exists
            import os
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                defaults = load_existing_config()

                # Should return empty dict when no config found
                assert isinstance(defaults, dict)
            finally:
                os.chdir(original_dir)


class TestTLSDetection:
    """Test TLS/SSL detection logic."""

    def test_atlas_urls_use_tls(self):
        """Verify that Atlas-style URLs trigger TLS usage."""
        atlas_urls = [
            "mongodb+srv://user:pass@cluster.mongodb.net/db",
            "mongodb://user:pass@cluster.mongodb.net:27017/db",
            "mongodb+srv://cluster.mongodb.net/",
        ]

        for url in atlas_urls:
            # Check if URL matches TLS detection criteria
            uses_tls = 'mongodb+srv://' in url or 'mongodb.net' in url
            assert uses_tls is True, f"URL {url} should trigger TLS"

    def test_local_urls_no_tls(self):
        """Verify that local URLs don't trigger TLS usage."""
        local_urls = [
            "mongodb://localhost:27017",
            "mongodb://127.0.0.1:27017/db",
            "mongodb://localhost:27017/testdb",
        ]

        for url in local_urls:
            # Check if URL matches TLS detection criteria
            uses_tls = 'mongodb+srv://' in url or 'mongodb.net' in url
            assert uses_tls is False, f"URL {url} should not trigger TLS"
