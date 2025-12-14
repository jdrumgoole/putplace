"""Pytest fixtures for putplace-assist tests."""

import asyncio
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from putplace_assist.database import Database


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db(tmp_path: Path) -> AsyncIterator[Database]:
    """Create a test database."""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    await database.connect()
    yield database
    await database.disconnect()


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Create a test client with a test database."""
    from putplace_assist import database as db_module
    from putplace_assist import watcher as watcher_module
    from putplace_assist import uploader as uploader_module
    from putplace_assist import activity as activity_module
    from putplace_assist.main import app

    # Create test database
    db_path = tmp_path / "api_test.db"
    test_database = Database(db_path)
    await test_database.connect()

    # Replace global database
    original_db = db_module.db
    db_module.db = test_database

    # Create test application transport
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup
    await test_database.disconnect()
    db_module.db = original_db


@pytest.fixture
def temp_test_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with test files."""
    test_dir = tmp_path / "test_files"
    test_dir.mkdir()

    # Create test files
    (test_dir / "file1.txt").write_text("Hello, World!")
    (test_dir / "file2.txt").write_text("Test content")
    (test_dir / "subdir").mkdir()
    (test_dir / "subdir" / "file3.txt").write_text("Nested file")
    (test_dir / ".hidden").write_text("Hidden file")

    return test_dir
