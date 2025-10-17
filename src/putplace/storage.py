"""Storage backend abstraction for file content storage."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def store(self, sha256: str, content: bytes) -> bool:
        """Store file content.

        Args:
            sha256: SHA256 hash of the file (used as key)
            content: File content bytes

        Returns:
            True if stored successfully, False otherwise
        """
        pass

    @abstractmethod
    async def retrieve(self, sha256: str) -> Optional[bytes]:
        """Retrieve file content.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            File content bytes or None if not found
        """
        pass

    @abstractmethod
    async def exists(self, sha256: str) -> bool:
        """Check if file content exists.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            True if file exists, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, sha256: str) -> bool:
        """Delete file content.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            True if deleted successfully, False if not found
        """
        pass

    @abstractmethod
    def get_storage_path(self, sha256: str) -> str:
        """Get the storage path/URI for a given SHA256.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            Full storage path or URI (e.g., "/var/putplace/files/e3/e3b..." or "s3://bucket/files/e3/e3b...")
        """
        pass


class LocalStorage(StorageBackend):
    """Local filesystem storage backend.

    Stores files in a directory structure: {base_path}/{sha256[:2]}/{sha256}
    This spreads files across 256 subdirectories to avoid too many files in one directory.
    """

    def __init__(self, base_path: str = "/var/putplace/files"):
        """Initialize local storage.

        Args:
            base_path: Base directory path for file storage
        """
        self.base_path = Path(base_path)
        logger.info(f"Initialized LocalStorage with base_path: {self.base_path}")

    def _get_file_path(self, sha256: str) -> Path:
        """Get file path for a given SHA256.

        Args:
            sha256: SHA256 hash

        Returns:
            Path object for the file
        """
        # Use first 2 characters as subdirectory to distribute files
        subdir = sha256[:2]
        return self.base_path / subdir / sha256

    async def store(self, sha256: str, content: bytes) -> bool:
        """Store file content to local filesystem.

        Args:
            sha256: SHA256 hash of the file
            content: File content bytes

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            file_path = self._get_file_path(sha256)

            # Create parent directory if it doesn't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content to file
            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(f"Stored file: {sha256} ({len(content)} bytes) at {file_path}")
            return True

        except (IOError, OSError) as e:
            logger.error(f"Failed to store file {sha256}: {e}")
            return False

    async def retrieve(self, sha256: str) -> Optional[bytes]:
        """Retrieve file content from local filesystem.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            File content bytes or None if not found
        """
        try:
            file_path = self._get_file_path(sha256)

            if not file_path.exists():
                logger.debug(f"File not found: {sha256}")
                return None

            with open(file_path, "rb") as f:
                content = f.read()

            logger.debug(f"Retrieved file: {sha256} ({len(content)} bytes)")
            return content

        except (IOError, OSError) as e:
            logger.error(f"Failed to retrieve file {sha256}: {e}")
            return None

    async def exists(self, sha256: str) -> bool:
        """Check if file exists in local filesystem.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            True if file exists, False otherwise
        """
        file_path = self._get_file_path(sha256)
        return file_path.exists()

    async def delete(self, sha256: str) -> bool:
        """Delete file from local filesystem.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            True if deleted successfully, False if not found
        """
        try:
            file_path = self._get_file_path(sha256)

            if not file_path.exists():
                logger.debug(f"File not found for deletion: {sha256}")
                return False

            file_path.unlink()
            logger.info(f"Deleted file: {sha256}")

            # Try to remove empty parent directory
            try:
                file_path.parent.rmdir()
                logger.debug(f"Removed empty directory: {file_path.parent}")
            except OSError:
                # Directory not empty or other error, ignore
                pass

            return True

        except (IOError, OSError) as e:
            logger.error(f"Failed to delete file {sha256}: {e}")
            return False

    def get_storage_path(self, sha256: str) -> str:
        """Get the storage path for a given SHA256.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            Absolute file path as string
        """
        file_path = self._get_file_path(sha256)
        return str(file_path.absolute())


class S3Storage(StorageBackend):
    """AWS S3 storage backend.

    Stores files in an S3 bucket with SHA256 as the key.
    """

    def __init__(
        self,
        bucket_name: str,
        region_name: str = "us-east-1",
        prefix: str = "files/",
        aws_profile: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ):
        """Initialize S3 storage.

        Args:
            bucket_name: S3 bucket name
            region_name: AWS region name
            prefix: Key prefix for stored files (default: "files/")
            aws_profile: AWS profile name from ~/.aws/credentials (optional)
            aws_access_key_id: AWS access key (optional, not recommended)
            aws_secret_access_key: AWS secret key (optional, not recommended)

        Note:
            If no credentials are provided, aioboto3 will use the standard AWS credential chain:
            1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
            2. AWS credentials file (~/.aws/credentials)
            3. IAM role (if running on EC2/ECS/Lambda) - RECOMMENDED for production
        """
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.prefix = prefix.rstrip("/") + "/"

        # Import boto3 here to make it optional
        try:
            import aioboto3

            # Create session with appropriate credentials
            session_kwargs = {}

            if aws_profile:
                # Use specific AWS profile from ~/.aws/credentials
                session_kwargs["profile_name"] = aws_profile
                logger.info(f"Using AWS profile: {aws_profile}")
            elif aws_access_key_id and aws_secret_access_key:
                # Use explicit credentials (not recommended for production)
                session_kwargs["aws_access_key_id"] = aws_access_key_id
                session_kwargs["aws_secret_access_key"] = aws_secret_access_key
                logger.warning("Using explicit AWS credentials - consider using IAM roles or profiles instead")
            else:
                # Use default credential chain (environment vars, ~/.aws/credentials, or IAM role)
                logger.info("Using default AWS credential chain")

            self.session = aioboto3.Session(**session_kwargs)
            logger.info(
                f"Initialized S3Storage with bucket: {bucket_name}, region: {region_name}, prefix: {prefix}"
            )
        except ImportError:
            logger.error("aioboto3 library not installed. Install with: pip install aioboto3")
            raise RuntimeError("aioboto3 library required for S3 storage")

    def _get_s3_key(self, sha256: str) -> str:
        """Get S3 key for a given SHA256.

        Args:
            sha256: SHA256 hash

        Returns:
            S3 key string
        """
        # Use first 2 characters as subdirectory for better organization
        subdir = sha256[:2]
        return f"{self.prefix}{subdir}/{sha256}"

    async def store(self, sha256: str, content: bytes) -> bool:
        """Store file content to S3.

        Args:
            sha256: SHA256 hash of the file
            content: File content bytes

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            s3_key = self._get_s3_key(sha256)

            async with self.session.client("s3", region_name=self.region_name) as s3:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=content,
                    ContentType="application/octet-stream",
                    Metadata={
                        "sha256": sha256,
                    },
                )

            logger.info(
                f"Stored file in S3: {sha256} ({len(content)} bytes) at s3://{self.bucket_name}/{s3_key}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store file {sha256} in S3: {e}")
            return False

    async def retrieve(self, sha256: str) -> Optional[bytes]:
        """Retrieve file content from S3.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            File content bytes or None if not found
        """
        try:
            s3_key = self._get_s3_key(sha256)

            async with self.session.client("s3", region_name=self.region_name) as s3:
                response = await s3.get_object(Bucket=self.bucket_name, Key=s3_key)
                content = await response["Body"].read()

            logger.debug(f"Retrieved file from S3: {sha256} ({len(content)} bytes)")
            return content

        except Exception as e:
            # Check if it's a NoSuchKey error (file not found)
            if hasattr(e, "response") and e.response.get("Error", {}).get("Code") == "NoSuchKey":
                logger.debug(f"File not found in S3: {sha256}")
                return None

            logger.error(f"Failed to retrieve file {sha256} from S3: {e}")
            return None

    async def exists(self, sha256: str) -> bool:
        """Check if file exists in S3.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            True if file exists, False otherwise
        """
        try:
            s3_key = self._get_s3_key(sha256)

            async with self.session.client("s3", region_name=self.region_name) as s3:
                await s3.head_object(Bucket=self.bucket_name, Key=s3_key)

            return True

        except Exception as e:
            # Check if it's a 404 error (file not found)
            if hasattr(e, "response") and e.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False

            logger.error(f"Failed to check existence of file {sha256} in S3: {e}")
            return False

    async def delete(self, sha256: str) -> bool:
        """Delete file from S3.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            True if deleted successfully, False if not found
        """
        try:
            # First check if file exists
            if not await self.exists(sha256):
                logger.debug(f"File not found in S3 for deletion: {sha256}")
                return False

            s3_key = self._get_s3_key(sha256)

            async with self.session.client("s3", region_name=self.region_name) as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=s3_key)

            logger.info(f"Deleted file from S3: {sha256}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete file {sha256} from S3: {e}")
            return False

    def get_storage_path(self, sha256: str) -> str:
        """Get the storage path (S3 URI) for a given SHA256.

        Args:
            sha256: SHA256 hash of the file

        Returns:
            S3 URI in the format "s3://bucket/key"
        """
        s3_key = self._get_s3_key(sha256)
        return f"s3://{self.bucket_name}/{s3_key}"


def get_storage_backend(backend_type: str, **kwargs) -> StorageBackend:
    """Factory function to get storage backend instance.

    Args:
        backend_type: Type of storage backend ("local" or "s3")
        **kwargs: Backend-specific configuration

    Returns:
        StorageBackend instance

    Raises:
        ValueError: If backend_type is not supported
    """
    if backend_type == "local":
        base_path = kwargs.get("base_path", "/var/putplace/files")
        return LocalStorage(base_path=base_path)

    elif backend_type == "s3":
        bucket_name = kwargs.get("bucket_name")
        if not bucket_name:
            raise ValueError("bucket_name is required for S3 storage")

        region_name = kwargs.get("region_name", "us-east-1")
        prefix = kwargs.get("prefix", "files/")
        aws_profile = kwargs.get("aws_profile")
        aws_access_key_id = kwargs.get("aws_access_key_id")
        aws_secret_access_key = kwargs.get("aws_secret_access_key")

        return S3Storage(
            bucket_name=bucket_name,
            region_name=region_name,
            prefix=prefix,
            aws_profile=aws_profile,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

    else:
        raise ValueError(f"Unsupported storage backend: {backend_type}")
