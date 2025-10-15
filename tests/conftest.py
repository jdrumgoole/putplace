"""Pytest configuration and shared fixtures."""

import asyncio
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from putplace.config import Settings
from putplace.database import MongoDB
from putplace.main import app


@pytest.fixture
def test_settings() -> Settings:
    """Test settings with test database."""
    return Settings(
        mongodb_url="mongodb://localhost:27017",
        mongodb_database="putplace_test",
        mongodb_collection="file_metadata_test",
    )


@pytest.fixture
async def test_db(test_settings: Settings) -> AsyncGenerator[MongoDB, None]:
    """Create test database instance."""
    db = MongoDB()
    db.client = AsyncIOMotorClient(test_settings.mongodb_url)
    test_db_instance = db.client[test_settings.mongodb_database]
    db.collection = test_db_instance[test_settings.mongodb_collection]

    # Drop collection first to ensure clean state
    await db.collection.drop()

    # Create indexes
    await db.collection.create_index("sha256")
    await db.collection.create_index([("hostname", 1), ("filepath", 1)])

    yield db

    # Cleanup
    try:
        await db.collection.drop()
    except Exception:
        pass  # Ignore cleanup errors

    if db.client:
        db.client.close()


@pytest.fixture
async def client(test_db: MongoDB) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client."""
    from httpx import ASGITransport

    # Override the database dependency
    from putplace import database

    original_mongodb = database.mongodb
    database.mongodb = test_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    # Restore original
    database.mongodb = original_mongodb


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
