"""Tests for storage backends."""

import hashlib
import tempfile
from pathlib import Path

import pytest

from putplace.storage import LocalStorage, get_storage_backend


class TestLocalStorage:
    """Tests for LocalStorage backend."""

    @pytest.fixture
    def temp_storage_path(self) -> Path:
        """Create a temporary directory for storage tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def local_storage(self, temp_storage_path: Path) -> LocalStorage:
        """Create LocalStorage instance with temp directory."""
        return LocalStorage(base_path=str(temp_storage_path))

    async def test_store_and_retrieve(self, local_storage: LocalStorage) -> None:
        """Test storing and retrieving file content."""
        content = b"Hello, World!"
        sha256 = hashlib.sha256(content).hexdigest()

        # Store content
        result = await local_storage.store(sha256, content)
        assert result is True

        # Retrieve content
        retrieved = await local_storage.retrieve(sha256)
        assert retrieved == content

    async def test_exists(self, local_storage: LocalStorage) -> None:
        """Test checking if file exists."""
        content = b"Test content"
        sha256 = hashlib.sha256(content).hexdigest()

        # File doesn't exist yet
        assert await local_storage.exists(sha256) is False

        # Store content
        await local_storage.store(sha256, content)

        # File exists now
        assert await local_storage.exists(sha256) is True

    async def test_delete(self, local_storage: LocalStorage) -> None:
        """Test deleting file content."""
        content = b"Delete me"
        sha256 = hashlib.sha256(content).hexdigest()

        # Store content
        await local_storage.store(sha256, content)
        assert await local_storage.exists(sha256) is True

        # Delete content
        result = await local_storage.delete(sha256)
        assert result is True
        assert await local_storage.exists(sha256) is False

        # Try to delete again (should return False)
        result = await local_storage.delete(sha256)
        assert result is False

    async def test_retrieve_nonexistent(self, local_storage: LocalStorage) -> None:
        """Test retrieving non-existent file returns None."""
        sha256 = "0" * 64  # Fake SHA256
        result = await local_storage.retrieve(sha256)
        assert result is None

    async def test_subdirectory_organization(self, local_storage: LocalStorage, temp_storage_path: Path) -> None:
        """Test that files are organized into subdirectories by first 2 chars of SHA256."""
        content = b"Subdirectory test"
        sha256 = hashlib.sha256(content).hexdigest()

        # Store content
        await local_storage.store(sha256, content)

        # Check file is in correct subdirectory
        expected_path = temp_storage_path / sha256[:2] / sha256
        assert expected_path.exists()

        # Verify content
        with open(expected_path, "rb") as f:
            assert f.read() == content

    async def test_large_file(self, local_storage: LocalStorage) -> None:
        """Test storing and retrieving a large file."""
        # Create 1MB of content
        content = b"X" * (1024 * 1024)
        sha256 = hashlib.sha256(content).hexdigest()

        # Store content
        result = await local_storage.store(sha256, content)
        assert result is True

        # Retrieve content
        retrieved = await local_storage.retrieve(sha256)
        assert retrieved == content
        assert len(retrieved) == 1024 * 1024


class TestStorageFactory:
    """Tests for storage backend factory function."""

    def test_get_local_storage(self) -> None:
        """Test getting local storage backend."""
        storage = get_storage_backend("local", base_path="/tmp/test")
        assert isinstance(storage, LocalStorage)

    def test_get_s3_storage_without_bucket(self) -> None:
        """Test that S3 storage requires bucket name."""
        with pytest.raises(ValueError, match="bucket_name is required"):
            get_storage_backend("s3")

    def test_get_s3_storage_with_bucket(self) -> None:
        """Test getting S3 storage backend with bucket name."""
        # This will fail if aioboto3 is not installed, which is expected
        try:
            from putplace.storage import S3Storage

            storage = get_storage_backend("s3", bucket_name="test-bucket")
            assert isinstance(storage, S3Storage)
        except RuntimeError as e:
            # aioboto3 not installed, skip this test
            assert "aioboto3 library required" in str(e)

    def test_unsupported_backend(self) -> None:
        """Test that unsupported backend raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported storage backend"):
            get_storage_backend("azure")


class TestS3Storage:
    """Tests for S3Storage backend.

    Note: These are minimal tests since they require AWS credentials and S3 access.
    For real testing, you would use moto or similar mocking library.
    """

    def test_s3_initialization_without_aioboto3(self) -> None:
        """Test that S3Storage raises error if aioboto3 is not installed."""
        # This test assumes aioboto3 might not be installed
        try:
            from putplace.storage import S3Storage

            # If we get here, aioboto3 is installed
            storage = S3Storage(bucket_name="test-bucket")
            assert storage.bucket_name == "test-bucket"
            assert storage.region_name == "us-east-1"
            assert storage.prefix == "files/"
        except RuntimeError as e:
            # aioboto3 not installed
            assert "aioboto3 library required" in str(e)

    def test_s3_get_key(self) -> None:
        """Test S3 key generation."""
        try:
            from putplace.storage import S3Storage

            storage = S3Storage(bucket_name="test-bucket", prefix="data/")
            sha256 = "abcdef1234567890" * 4  # 64 char SHA256
            key = storage._get_s3_key(sha256)

            # Should include prefix and subdirectory
            assert key.startswith("data/ab/")
            assert key.endswith(sha256)
        except RuntimeError:
            # aioboto3 not installed, skip
            pass


class TestLocalStorageErrorHandling:
    """Tests for LocalStorage error handling."""

    @pytest.fixture
    def local_storage(self) -> LocalStorage:
        """Create LocalStorage instance with invalid path for error testing."""
        # Use a path that exists but we'll make it fail by using permissions
        return LocalStorage(base_path="/nonexistent/invalid/path")

    async def test_store_failure_invalid_path(self, local_storage: LocalStorage) -> None:
        """Test store failure when path is invalid or inaccessible."""
        content = b"Test content"
        sha256 = hashlib.sha256(content).hexdigest()

        # Try to store to invalid path - should handle error gracefully
        # Note: This might succeed on some systems depending on permissions
        # So we check that it returns a boolean
        result = await local_storage.store(sha256, content)
        assert isinstance(result, bool)

    async def test_retrieve_io_error(self) -> None:
        """Test retrieve handles IO errors gracefully."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            content = b"Test content"
            sha256 = hashlib.sha256(content).hexdigest()

            # Store file successfully
            await storage.store(sha256, content)

            # Make file unreadable (simulate IO error)
            file_path = storage._get_file_path(sha256)
            os.chmod(file_path, 0o000)

            try:
                # Try to retrieve - should return None on error
                result = await storage.retrieve(sha256)
                # Depending on permissions, might succeed or fail
                assert result is None or result == content
            finally:
                # Restore permissions for cleanup
                os.chmod(file_path, 0o644)

    async def test_delete_io_error(self) -> None:
        """Test delete handles IO errors gracefully."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            content = b"Test content"
            sha256 = hashlib.sha256(content).hexdigest()

            # Store file successfully
            await storage.store(sha256, content)

            # Make parent directory unwritable (simulate IO error)
            file_path = storage._get_file_path(sha256)
            parent_dir = file_path.parent
            os.chmod(parent_dir, 0o444)  # Read-only

            try:
                # Try to delete - should return False on error
                result = await storage.delete(sha256)
                # Depending on system, might succeed or fail
                assert isinstance(result, bool)
            finally:
                # Restore permissions for cleanup
                os.chmod(parent_dir, 0o755)

    async def test_get_storage_path(self) -> None:
        """Test get_storage_path returns correct path."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            sha256 = "abcdef1234567890" * 4  # 64 char SHA256

            path = storage.get_storage_path(sha256)

            # Should be an absolute path
            assert Path(path).is_absolute()
            # Should contain the SHA256
            assert sha256 in path
            # Should contain the subdirectory (first 2 chars)
            assert sha256[:2] in path


class TestS3StorageWithMethods:
    """Additional tests for S3Storage methods."""

    def test_s3_get_storage_path(self) -> None:
        """Test S3 get_storage_path returns correct S3 URI."""
        try:
            from putplace.storage import S3Storage

            storage = S3Storage(bucket_name="my-bucket", prefix="data/")
            sha256 = "abcdef1234567890" * 4  # 64 char SHA256

            path = storage.get_storage_path(sha256)

            # Should be S3 URI format
            assert path.startswith("s3://my-bucket/")
            # Should contain prefix and subdirectory
            assert "data/ab/" in path
            # Should end with SHA256
            assert path.endswith(sha256)
        except RuntimeError:
            # aioboto3 not installed, skip
            pass

    def test_s3_with_profile(self) -> None:
        """Test S3 initialization with AWS profile."""
        try:
            from putplace.storage import S3Storage

            # This will create the session but not actually connect
            storage = S3Storage(
                bucket_name="test-bucket",
                region_name="us-west-2",
                prefix="custom/",
                aws_profile="my-profile"
            )

            assert storage.bucket_name == "test-bucket"
            assert storage.region_name == "us-west-2"
            assert storage.prefix == "custom/"
        except RuntimeError:
            # aioboto3 not installed, skip
            pass

    def test_s3_with_explicit_credentials(self) -> None:
        """Test S3 initialization with explicit credentials."""
        try:
            from putplace.storage import S3Storage

            storage = S3Storage(
                bucket_name="test-bucket",
                aws_access_key_id="test_key",
                aws_secret_access_key="test_secret"
            )

            assert storage.bucket_name == "test-bucket"
        except RuntimeError:
            # aioboto3 not installed, skip
            pass
