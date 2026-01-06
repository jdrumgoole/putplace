"""Tests for Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from putplace_assist.models import (
    EventType,
    ExcludeCreate,
    FileStats,
    PathCreate,
    PathResponse,
    ServerCreate,
    UploadStatus,
)


class TestPathModels:
    """Tests for path-related models."""

    def test_path_create_valid(self):
        """Test valid path creation."""
        path = PathCreate(path="/var/log", recursive=True)
        assert path.path == "/var/log"
        assert path.recursive is True

    def test_path_create_defaults(self):
        """Test path creation with defaults."""
        path = PathCreate(path="/tmp")
        assert path.recursive is True

    def test_path_response(self):
        """Test path response model."""
        now = datetime.utcnow()
        path = PathResponse(
            id=1,
            path="/var/log",
            recursive=True,
            enabled=True,
            created_at=now,
            file_count=10,
        )
        assert path.id == 1
        assert path.file_count == 10


class TestExcludeModels:
    """Tests for exclude pattern models."""

    def test_exclude_create(self):
        """Test exclude pattern creation."""
        exclude = ExcludeCreate(pattern="*.log")
        assert exclude.pattern == "*.log"

    def test_exclude_create_empty(self):
        """Test exclude with empty pattern fails."""
        with pytest.raises(ValidationError):
            ExcludeCreate(pattern="")


class TestFileModels:
    """Tests for file-related models."""

    def test_file_stats(self):
        """Test file stats model."""
        stats = FileStats(
            total_files=100,
            total_size=1024 * 1024,
            pending_sha256=10,
            pending_uploads=10,
            meta_uploads=30,
            full_uploads=50,
            paths_watched=3,
        )
        assert stats.total_files == 100
        assert stats.paths_watched == 3
        assert stats.pending_sha256 == 10
        assert stats.pending_uploads == 10


class TestServerModels:
    """Tests for server configuration models."""

    def test_server_create(self):
        """Test server creation."""
        server = ServerCreate(
            name="production",
            url="https://app.putplace.org",
            username="admin",
            password="secret",
        )
        assert server.name == "production"
        assert server.url == "https://app.putplace.org"


class TestEnums:
    """Tests for enum types."""

    def test_upload_status(self):
        """Test upload status enum."""
        assert UploadStatus.PENDING.value == "pending"
        assert UploadStatus.SUCCESS.value == "success"

    def test_event_type(self):
        """Test event type enum."""
        assert EventType.FILE_DISCOVERED.value == "file_discovered"
        assert EventType.UPLOAD_COMPLETE.value == "upload_complete"
