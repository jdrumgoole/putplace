"""Tests for database operations."""

import pytest

from putplace_assist.database import Database
from putplace_assist.models import EventType, UploadStatus


@pytest.mark.asyncio
class TestPathOperations:
    """Tests for path database operations."""

    async def test_add_path(self, test_db: Database):
        """Test adding a path."""
        path_id = await test_db.add_path("/var/log", recursive=True)
        assert path_id > 0

    async def test_get_path(self, test_db: Database):
        """Test getting a path by ID."""
        path_id = await test_db.add_path("/var/log")
        path = await test_db.get_path(path_id)

        assert path is not None
        assert path.id == path_id
        assert path.path == "/var/log"
        assert path.recursive is True

    async def test_get_path_by_path(self, test_db: Database):
        """Test getting a path by path string."""
        await test_db.add_path("/var/log")
        path = await test_db.get_path_by_path("/var/log")

        assert path is not None
        assert path.path == "/var/log"

    async def test_get_all_paths(self, test_db: Database):
        """Test getting all paths."""
        await test_db.add_path("/var/log")
        await test_db.add_path("/tmp")

        paths = await test_db.get_all_paths()
        assert len(paths) == 2

    async def test_delete_path(self, test_db: Database):
        """Test deleting a path."""
        path_id = await test_db.add_path("/var/log")
        deleted = await test_db.delete_path(path_id)

        assert deleted is True
        assert await test_db.get_path(path_id) is None


@pytest.mark.asyncio
class TestExcludeOperations:
    """Tests for exclude pattern database operations."""

    async def test_add_exclude(self, test_db: Database):
        """Test adding an exclude pattern."""
        exclude_id = await test_db.add_exclude("*.log")
        assert exclude_id > 0

    async def test_get_all_excludes(self, test_db: Database):
        """Test getting all exclude patterns."""
        await test_db.add_exclude("*.log")
        await test_db.add_exclude(".git")

        excludes = await test_db.get_all_excludes()
        assert len(excludes) == 2

    async def test_delete_exclude(self, test_db: Database):
        """Test deleting an exclude pattern."""
        exclude_id = await test_db.add_exclude("*.log")
        deleted = await test_db.delete_exclude(exclude_id)

        assert deleted is True
        excludes = await test_db.get_all_excludes()
        assert len(excludes) == 0


@pytest.mark.asyncio
class TestFileOperations:
    """Tests for file database operations."""

    async def test_upsert_file_new(self, test_db: Database):
        """Test inserting a new file."""
        await test_db.upsert_file(
            filepath="/var/log/test.log",
            file_size=1024,
            file_mtime=1234567890.0,
            file_mode=0o644,
            sha256="a" * 64,
        )

        # Verify file was inserted
        file = await test_db.get_file("/var/log/test.log")
        assert file is not None
        assert file["filepath"] == "/var/log/test.log"

    async def test_upsert_file_update(self, test_db: Database):
        """Test updating an existing file."""
        # Insert initial file
        await test_db.upsert_file(
            filepath="/var/log/test.log",
            file_size=1024,
            file_mtime=1234567890.0,
            sha256="a" * 64,
        )

        # Update the file
        await test_db.upsert_file(
            filepath="/var/log/test.log",
            file_size=2048,
            file_mtime=1234567900.0,
            sha256="b" * 64,
        )

        # Verify file was updated
        file = await test_db.get_file("/var/log/test.log")
        assert file["sha256"] == "b" * 64
        assert file["file_size"] == 2048

    async def test_get_file(self, test_db: Database):
        """Test getting a single file by filepath."""
        # Insert a file
        await test_db.upsert_file(
            filepath="/var/log/a.log",
            file_size=100,
            file_mtime=1234567890.0,
            sha256="a" * 64,
        )

        # Get the file
        file = await test_db.get_file("/var/log/a.log")
        assert file is not None
        assert file["filepath"] == "/var/log/a.log"
        assert file["sha256"] == "a" * 64
        assert file["file_size"] == 100

        # Get non-existent file
        file = await test_db.get_file("/var/log/nonexistent.log")
        assert file is None

    async def test_get_file_stats(self, test_db: Database):
        """Test getting file statistics."""
        path_id = await test_db.add_path("/var/log")

        # Insert files
        await test_db.upsert_file(
            filepath="/var/log/a.log",
            file_size=100,
            file_mtime=1234567890.0,
            sha256="a" * 64,
        )
        await test_db.upsert_file(
            filepath="/var/log/b.log",
            file_size=200,
            file_mtime=1234567890.0,
            sha256="b" * 64,
        )

        stats = await test_db.get_file_stats()
        assert stats.total_files == 2
        assert stats.total_size == 300
        assert stats.paths_watched == 1


@pytest.mark.asyncio
class TestActivityOperations:
    """Tests for activity log operations."""

    async def test_log_activity(self, test_db: Database):
        """Test logging an activity event."""
        event_id = await test_db.log_activity(
            event_type=EventType.SCAN_STARTED,
            message="Started scanning /var/log",
        )
        assert event_id > 0

    async def test_get_activity(self, test_db: Database):
        """Test getting activity events."""
        await test_db.log_activity(EventType.SCAN_STARTED, message="Event 1")
        await test_db.log_activity(EventType.FILE_DISCOVERED, message="Event 2")

        events, has_more = await test_db.get_activity(limit=10)
        assert len(events) == 2
        assert has_more is False

    async def test_get_activity_since_id(self, test_db: Database):
        """Test getting activity events since an ID."""
        await test_db.log_activity(EventType.SCAN_STARTED, message="Event 1")
        event_id = await test_db.log_activity(EventType.FILE_DISCOVERED, message="Event 2")
        await test_db.log_activity(EventType.FILE_CHANGED, message="Event 3")

        events, _ = await test_db.get_activity(since_id=event_id - 1)
        assert len(events) == 2

    async def test_get_activity_by_type(self, test_db: Database):
        """Test filtering activity by event type."""
        await test_db.log_activity(EventType.SCAN_STARTED, message="Event 1")
        await test_db.log_activity(EventType.FILE_DISCOVERED, message="Event 2")

        events, _ = await test_db.get_activity(event_type=EventType.SCAN_STARTED)
        assert len(events) == 1
        assert events[0].event_type == EventType.SCAN_STARTED
