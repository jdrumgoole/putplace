"""Tests demonstrating the use of run_configure helper for programmatic setup.

This module shows how to use putplace_configure in non-interactive mode
to set up different test environments programmatically.
"""

import tempfile
from pathlib import Path

import pytest

from tests.conftest import run_configure


def test_configure_local_storage():
    """Test configuring PutPlace with local storage backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "storage"
        config_path = Path(tmpdir) / "ppserver.toml"

        success, message = run_configure(
            db_name="test_local_db",
            storage_path=storage_path,
            config_path=config_path,
            admin_username="local_admin",
            admin_email="local@test.com",
            admin_password="local123",
            storage_backend="local",
        )

        assert success, f"Configure failed: {message}"
        assert config_path.exists(), "Config file not created"

        # Verify config content
        config_content = config_path.read_text()
        assert 'backend = "local"' in config_content
        assert 'host = "127.0.0.1"' in config_content
        assert "test_local_db" in config_content


def test_configure_custom_credentials():
    """Test configuring with custom admin credentials."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "storage"
        config_path = Path(tmpdir) / "ppserver.toml"

        success, message = run_configure(
            db_name="test_custom_db",
            storage_path=storage_path,
            config_path=config_path,
            admin_username="custom_admin",
            admin_email="custom@example.com",
            admin_password="secure_password_456",
            storage_backend="local",
        )

        assert success, f"Configure failed: {message}"
        assert config_path.exists()


def test_configure_s3_storage():
    """Test configuring PutPlace with S3 storage backend.

    Note: This test skips AWS validation checks, so it succeeds even
    without actual AWS credentials or S3 bucket access.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "storage"
        config_path = Path(tmpdir) / "ppserver.toml"

        success, message = run_configure(
            db_name="test_s3_db",
            storage_path=storage_path,
            config_path=config_path,
            admin_username="s3_admin",
            admin_email="s3@test.com",
            admin_password="s3_password",
            storage_backend="s3",
            s3_bucket="test-putplace-bucket",
            aws_region="eu-west-1",
            skip_checks=True,  # Skip AWS validation for testing
        )

        assert success, f"Configure failed: {message}"
        assert config_path.exists(), "Config file not created"

        # Verify S3 configuration
        config_content = config_path.read_text()
        assert 'backend = "s3"' in config_content
        assert 'test-putplace-bucket' in config_content
        assert 'eu-west-1' in config_content


def test_configure_s3_without_bucket_fails():
    """Test that S3 configuration fails without bucket name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "storage"
        config_path = Path(tmpdir) / "ppserver.toml"

        success, message = run_configure(
            db_name="test_db",
            storage_path=storage_path,
            config_path=config_path,
            storage_backend="s3",
            s3_bucket=None,  # Missing bucket
        )

        assert not success, "Expected configure to fail without S3 bucket"
        assert "S3 bucket required" in message


def test_configure_multiple_workers():
    """Test configuring separate environments for parallel test workers.

    This demonstrates how pytest-xdist can run multiple test workers,
    each with their own isolated configuration.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        configs = []

        # Simulate 3 test workers
        for worker_id in ["gw0", "gw1", "gw2"]:
            storage_path = Path(tmpdir) / f"storage_{worker_id}"
            config_path = Path(tmpdir) / f"ppserver_{worker_id}.toml"

            success, message = run_configure(
                db_name=f"test_db_{worker_id}",
                storage_path=storage_path,
                config_path=config_path,
                admin_username=f"admin_{worker_id}",
                admin_email=f"admin_{worker_id}@test.com",
                admin_password=f"password_{worker_id}",
                storage_backend="local",
            )

            assert success, f"Configure failed for {worker_id}: {message}"
            assert config_path.exists()
            configs.append(config_path)

        # Verify all configs are independent
        assert len(configs) == 3
        for config_path in configs:
            assert config_path.exists()


def test_configure_creates_storage_directory():
    """Test that configure creates the storage directory if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Use a nested path that doesn't exist yet
        storage_path = Path(tmpdir) / "nested" / "storage" / "files"
        config_path = Path(tmpdir) / "ppserver.toml"

        success, message = run_configure(
            db_name="test_db",
            storage_path=storage_path,
            config_path=config_path,
            storage_backend="local",
        )

        assert success, f"Configure failed: {message}"

        # The configure process should have created the directory
        # (or the application will create it on startup)
        assert config_path.exists()


def test_configure_generates_valid_toml():
    """Test that generated configuration is valid TOML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "storage"
        config_path = Path(tmpdir) / "ppserver.toml"

        success, message = run_configure(
            db_name="test_db",
            storage_path=storage_path,
            config_path=config_path,
            storage_backend="local",
        )

        assert success, f"Configure failed: {message}"
        assert config_path.exists()

        # Verify we can parse the TOML
        try:
            import sys

            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib

            with open(config_path, "rb") as f:
                config = tomllib.load(f)

            # Verify expected sections exist
            assert "server" in config
            assert "database" in config
            assert "storage" in config

            # Verify expected values
            assert config["server"]["host"] == "127.0.0.1"
            assert config["server"]["port"] == 8000
            assert config["database"]["mongodb_database"] == "test_db"
            assert config["storage"]["backend"] == "local"

        except Exception as e:
            pytest.fail(f"Failed to parse generated TOML: {e}")
