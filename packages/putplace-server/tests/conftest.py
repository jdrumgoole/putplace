"""Pytest configuration and shared fixtures.

This module demonstrates using putplace_configure in non-interactive mode
to set up test environments programmatically.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

# The regstack singleton is built at module-load time inside putplace_server.main,
# which means it reads settings.mongodb_database *before* any pytest fixture runs.
# To make regstack write to this worker's isolated database (putplace_test_gwN),
# we must set MONGODB_DATABASE before importing anything from putplace_server.
_worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
os.environ.setdefault("MONGODB_DATABASE", f"putplace_test_{_worker_id}")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-for-production")
os.environ.setdefault("REGSTACK_JWT_SECRET", "test-regstack-jwt-secret-not-for-production")

import pytest
from httpx import AsyncClient
from pymongo import AsyncMongoClient

from regstack.models.user import BaseUser

from putplace_server.config import Settings
from putplace_server.database import MongoDB
from putplace_server.main import app
from putplace_server.regstack_integration import get_regstack


@pytest.fixture(scope="session", autouse=True)
async def _regstack_session_lifecycle():
    # The regstack instance is built at module-load (so its routers can be
    # mounted at FastAPI app construction time). httpx ASGITransport in this
    # conftest does not run lifespan events, so the lifespan's install_schema()
    # and aclose() never fire under pytest. Drive them by hand here so
    # indexes exist (regstack.users.create() relies on the unique-email index)
    # and the Mongo client closes cleanly at session end.
    await get_regstack().install_schema()
    yield
    await get_regstack().aclose()


def run_configure(
    db_name: str,
    storage_path: Path,
    config_path: Path,
    admin_email: str = "test@test.local",
    admin_password: str = "test_password_123",
    storage_backend: str = "local",
    s3_bucket: str | None = None,
    aws_region: str = "eu-west-1",
    skip_checks: bool = True,
    # Keep admin_username parameter for backwards compatibility but ignore it
    admin_username: str | None = None,
) -> tuple[bool, str]:
    """Run putplace_configure in non-interactive mode.

    Helper function to configure PutPlace programmatically for testing.

    Args:
        db_name: MongoDB database name
        storage_path: Path to storage directory
        config_path: Path to output configuration file
        admin_email: Admin email (default: test@test.local)
        admin_password: Admin password (default: test_password_123)
        storage_backend: Storage backend ('local' or 's3', default: local)
        s3_bucket: S3 bucket name (required if storage_backend='s3')
        aws_region: AWS region (default: eu-west-1)
        skip_checks: Skip MongoDB/AWS validation checks (default: True)
        admin_username: Deprecated, ignored (kept for backwards compatibility)

    Returns:
        Tuple of (success: bool, message: str)

    Example:
        >>> storage_path = Path("/tmp/test_storage")
        >>> config_path = Path("/tmp/test_config.toml")
        >>> success, msg = run_configure(
        ...     db_name="test_db",
        ...     storage_path=storage_path,
        ...     config_path=config_path,
        ... )
        >>> print(f"Success: {success}")
        >>> print(f"Config at: {config_path}")
    """
    import subprocess
    import sys

    cmd = [
        sys.executable, "-m", "putplace_server.scripts.putplace_configure",
        "--non-interactive",
        "--mongodb-url", "mongodb://localhost:27017",
        "--mongodb-database", db_name,
        "--admin-email", admin_email,
        "--admin-password", admin_password,
        "--storage-backend", storage_backend,
        "--storage-path", str(storage_path),
        "--config-file", str(config_path),
    ]

    if skip_checks:
        cmd.append("--skip-checks")

    if storage_backend == "s3":
        if not s3_bucket:
            return False, "S3 bucket required when storage_backend='s3'"
        cmd.extend(["--s3-bucket", s3_bucket, "--aws-region", aws_region])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            return True, f"Configuration created successfully at {config_path}"
        else:
            return False, f"Configure failed: {result.stderr or result.stdout}"

    except subprocess.TimeoutExpired:
        return False, "Configure command timed out"
    except Exception as e:
        return False, f"Configure error: {str(e)}"


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_databases(worker_id: str):
    """Drop this worker's test database when its session ends.

    Each pytest-xdist worker is its own process with its own session, so this
    fires once per worker. It must drop ONLY this worker's database — the
    earlier version dropped every `putplace_test_*` database, which under
    LoadScopeScheduling routinely deleted databases still in use by sibling
    workers, wiping their unique indexes mid-test and producing flaky
    duplicate-detection failures.
    """
    yield

    db_name = f"putplace_test_{worker_id}"

    async def _cleanup():
        client = AsyncMongoClient("mongodb://localhost:27017")
        try:
            await client.drop_database(db_name)
        finally:
            await client.close()

    asyncio.run(_cleanup())


@pytest.fixture
def test_settings(worker_id: str, tmp_path_factory) -> Settings:
    """Test settings with test database and temporary storage.

    Uses putplace_configure in non-interactive mode to generate proper
    configuration for each test worker. This demonstrates how to use
    the configure script programmatically.

    Each pytest-xdist worker gets its own database to avoid race conditions.
    In serial mode (no worker_id), uses 'master' as the identifier.

    Args:
        worker_id: pytest-xdist worker identifier (e.g., 'gw0', 'gw1', 'master')
        tmp_path_factory: pytest fixture for creating temporary directories

    Returns:
        Settings object configured for this test worker
    """
    # pytest-xdist provides worker_id (e.g., 'gw0', 'gw1')
    # In serial mode, worker_id is 'master'
    db_name = f"putplace_test_{worker_id}"

    # Create temporary directories for this worker
    storage_path = tmp_path_factory.mktemp(f"storage_{worker_id}")
    config_path = tmp_path_factory.mktemp(f"config_{worker_id}") / "ppserver.toml"

    # Use putplace_configure in non-interactive mode to set up test environment
    success, message = run_configure(
        db_name=db_name,
        storage_path=storage_path,
        config_path=config_path,
        admin_username=f"test_admin_{worker_id}",
        admin_email=f"test_admin_{worker_id}@test.local",
        admin_password="test_password_123",
        storage_backend="local",
        skip_checks=True,  # Skip MongoDB and AWS checks for speed
    )

    if not success:
        # If configure fails, fall back to manual settings creation
        # This ensures tests can still run even if configure script has issues
        return Settings(
            mongodb_url="mongodb://localhost:27017",
            mongodb_database=db_name,
            mongodb_collection="file_metadata_test",
            storage_path=str(storage_path),
        )

    # Return settings that match the configuration
    # The configure script has already created the admin user and config file
    return Settings(
        mongodb_url="mongodb://localhost:27017",
        mongodb_database=db_name,
        mongodb_collection="file_metadata_test",
        storage_path=str(storage_path),
    )


@pytest.fixture
async def test_db(test_settings: Settings) -> AsyncGenerator[MongoDB, None]:
    """Create test database instance.

    Each pytest-xdist worker gets its own isolated database to prevent
    race conditions during parallel test execution. Database names are
    automatically generated based on worker ID (e.g., putplace_test_gw0).

    The database and all collections are cleaned up after each test.
    """
    db = MongoDB()
    db.client = AsyncMongoClient(test_settings.mongodb_url)
    test_db_instance = db.client[test_settings.mongodb_database]
    db.collection = test_db_instance[test_settings.mongodb_collection]
    db.upload_sessions_collection = test_db_instance["upload_sessions_test"]
    api_keys_collection = test_db_instance["api_keys"]

    # Drop collections first to ensure clean state
    await db.collection.drop()
    await db.upload_sessions_collection.drop()
    await api_keys_collection.drop()

    # Create indexes for file metadata
    await db.collection.create_index("sha256")
    await db.collection.create_index([("hostname", 1), ("filepath", 1)])

    # Create indexes for upload sessions collection
    await db.upload_sessions_collection.create_index("upload_id", unique=True)
    await db.upload_sessions_collection.create_index("expires_at")
    await db.upload_sessions_collection.create_index([("user_id", 1), ("status", 1)])

    # Create indexes for API keys collection
    await api_keys_collection.create_index("key_hash", unique=True)
    await api_keys_collection.create_index([("is_active", 1)])

    yield db

    # Cleanup
    try:
        await db.collection.drop()
        await db.upload_sessions_collection.drop()
        await api_keys_collection.drop()
    except Exception:
        pass  # Ignore cleanup errors

    if db.client:
        await db.client.close()


@pytest.fixture
def test_storage() -> Generator[Path, None, None]:
    """Create temporary storage backend for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def client(test_db: MongoDB, test_storage: Path) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client."""
    from httpx import ASGITransport
    from putplace_server.storage import LocalStorage
    from putplace_server.main import get_db, get_storage
    from putplace_server.auth import get_auth_db

    # Override dependencies using FastAPI's dependency_overrides
    # This is thread-safe for parallel test execution
    storage = LocalStorage(str(test_storage))

    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_auth_db] = lambda: test_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        # Clean up only our specific overrides (not all overrides)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_storage, None)
        app.dependency_overrides.pop(get_auth_db, None)


@pytest.fixture
async def test_api_key(test_db: MongoDB) -> str:
    """Create a test API key for authentication."""
    from putplace_server.auth import APIKeyAuth

    auth = APIKeyAuth(test_db)
    api_key, _ = await auth.create_api_key(
        name="test_key",
        user_id=None,  # Bootstrap API key without user
        description="Test API key for pytest"
    )
    return api_key


@pytest.fixture
async def test_user_token(test_db: MongoDB) -> str:
    """Seed a regstack user and return a regstack-signed JWT for them."""
    rs = get_regstack()
    existing = await rs.users.get_by_email("testuser@example.com")
    if existing is None:
        user = BaseUser(
            email="testuser@example.com",
            hashed_password=rs.password_hasher.hash("testpassword123"),
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        existing = await rs.users.create(user)
    token, _ = rs.jwt.encode(subject=existing.id)
    return token


@pytest.fixture
def sample_file_metadata() -> dict:
    """Sample file metadata for testing."""
    return {
        "filepath": "/var/log/test.log",
        "hostname": "testserver",
        "ip_address": "192.168.1.100",
        "sha256": "a" * 64,  # Valid 64-character SHA256
        "file_size": 1024,
        "file_mode": 33188,  # Regular file with rw-r--r-- permissions
        "file_uid": 1000,
        "file_gid": 1000,
        "file_mtime": 1609459200.0,
        "file_atime": 1609459200.0,
        "file_ctime": 1609459200.0,
    }


@pytest.fixture
async def test_admin_user_token(test_db: MongoDB) -> str:
    """Seed a regstack superuser and return a regstack-signed JWT for them."""
    rs = get_regstack()
    user = await rs.bootstrap_admin(email="admin@example.com", password="adminpassword123")
    token, _ = rs.jwt.encode(subject=user.id)
    return token


@pytest.fixture
def temp_test_dir() -> Generator[Path, None, None]:
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files
        (tmp_path / "file1.txt").write_text("Hello World")
        (tmp_path / "file2.log").write_text("Log entry")

        # Create subdirectory with files
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("Nested file")

        # Create .git directory (for exclude testing)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")

        # Create __pycache__ directory
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.pyc").write_text("bytecode")

        yield tmp_path
