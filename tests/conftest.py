"""Pytest configuration and shared fixtures."""

import asyncio
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
from httpx import AsyncClient
from pymongo import AsyncMongoClient

from putplace.config import Settings
from putplace.database import MongoDB
from putplace.main import app


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_databases():
    """Clean up all test databases at the end of the test session.

    This runs automatically after all tests complete to ensure
    worker-specific databases don't accumulate.
    """
    yield

    # Cleanup all test databases after tests complete
    async def _cleanup():
        client = AsyncMongoClient("mongodb://localhost:27017")
        try:
            # Get all database names
            db_names = await client.list_database_names()

            # Drop all test databases
            for db_name in db_names:
                if db_name.startswith("putplace_test_"):
                    await client.drop_database(db_name)
        finally:
            await client.close()

    # Run the async cleanup
    asyncio.run(_cleanup())


@pytest.fixture
def test_settings(worker_id: str, tmp_path_factory) -> Settings:
    """Test settings with test database and temporary storage.

    Each pytest-xdist worker gets its own database to avoid race conditions.
    In serial mode (no worker_id), uses 'master' as the identifier.

    Args:
        worker_id: pytest-xdist worker identifier (e.g., 'gw0', 'gw1', 'master')
        tmp_path_factory: pytest fixture for creating temporary directories
    """
    # pytest-xdist provides worker_id (e.g., 'gw0', 'gw1')
    # In serial mode, worker_id is 'master'
    db_name = f"putplace_test_{worker_id}"

    # Create a temporary storage directory for this worker
    storage_path = tmp_path_factory.mktemp(f"storage_{worker_id}")

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
    db.users_collection = test_db_instance["users_test"]

    # Drop collections first to ensure clean state
    await db.collection.drop()
    await db.users_collection.drop()

    # Create indexes for file metadata
    await db.collection.create_index("sha256")
    await db.collection.create_index([("hostname", 1), ("filepath", 1)])

    # Create indexes for users collection
    await db.users_collection.create_index("username", unique=True)
    await db.users_collection.create_index("email", unique=True)

    yield db

    # Cleanup
    try:
        await db.collection.drop()
        await db.users_collection.drop()
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
    from putplace.storage import LocalStorage
    from putplace.main import get_db, get_storage
    from putplace.auth import get_auth_db

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
    from putplace.auth import APIKeyAuth

    auth = APIKeyAuth(test_db)
    api_key, _ = await auth.create_api_key(
        name="test_key",
        user_id=None,  # Bootstrap API key without user
        description="Test API key for pytest"
    )
    return api_key


@pytest.fixture
async def test_user_token(test_db: MongoDB) -> str:
    """Create a test user and return their JWT token."""
    from putplace.user_auth import get_password_hash, create_access_token
    from datetime import timedelta

    # Create test user
    user_id = await test_db.create_user(
        username="testuser",
        email="testuser@example.com",
        hashed_password=get_password_hash("testpassword123"),
        full_name="Test User"
    )

    # Generate JWT token for the user
    access_token = create_access_token(
        data={"sub": "testuser"},
        expires_delta=timedelta(minutes=30)
    )

    return access_token


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
