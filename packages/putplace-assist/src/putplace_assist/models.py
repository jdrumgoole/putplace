"""Pydantic models for putplace-assist API."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# Enums
class UploadType(str, Enum):
    """Type of upload."""

    META = "meta"
    FULL = "full"


class EventType(str, Enum):
    """Type of activity event."""

    SCAN_STARTED = "scan_started"
    SCAN_COMPLETE = "scan_complete"
    FILE_DISCOVERED = "file_discovered"
    FILE_CHANGED = "file_changed"
    FILE_DELETED = "file_deleted"
    FILE_MODIFIED = "file_modified"
    SHA256_STARTED = "sha256_started"
    SHA256_COMPLETE = "sha256_complete"
    SHA256_FAILED = "sha256_failed"
    UPLOAD_STARTED = "upload_started"
    UPLOAD_PROGRESS = "upload_progress"
    UPLOAD_COMPLETE = "upload_complete"
    UPLOAD_FAILED = "upload_failed"
    TABLE_CLEANUP = "table_cleanup"
    ERROR = "error"


class UploadStatus(str, Enum):
    """Status of file upload."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


# Path models
class PathCreate(BaseModel):
    """Request to register a path."""

    path: str = Field(..., description="Path to watch")
    recursive: bool = Field(default=True, description="Scan recursively")


class PathResponse(BaseModel):
    """Response for a registered path."""

    id: int
    path: str
    recursive: bool
    enabled: bool
    created_at: datetime
    last_scanned_at: Optional[datetime] = None
    file_count: int = 0


class PathListResponse(BaseModel):
    """Response for listing paths."""

    paths: list[PathResponse]
    total: int


# Exclude pattern models
class ExcludeCreate(BaseModel):
    """Request to add an exclude pattern."""

    pattern: str = Field(
        ...,
        min_length=1,
        description="Pattern to exclude (e.g., '*.log', '.git')",
    )


class ExcludeResponse(BaseModel):
    """Response for an exclude pattern."""

    id: int
    pattern: str
    created_at: datetime


class ExcludeListResponse(BaseModel):
    """Response for listing exclude patterns."""

    patterns: list[ExcludeResponse]
    total: int


# File log models (new monthly table entries)
class FileLogEntry(BaseModel):
    """An entry in a monthly filelog table."""

    id: int
    filepath: str
    ctime: float
    mtime: float
    atime: Optional[float] = None
    file_size: int
    permissions: Optional[int] = None
    uid: Optional[int] = None
    gid: Optional[int] = None
    logged_at: datetime
    source_table: str  # Which monthly table this came from


class FileLogSha256Entry(BaseModel):
    """An entry in the filelog_sha256 table."""

    id: int
    filepath: str
    ctime: float
    mtime: float
    atime: Optional[float] = None
    file_size: int
    permissions: Optional[int] = None
    uid: Optional[int] = None
    gid: Optional[int] = None
    sha256: str
    upload_status: Optional[str] = None  # None, 'meta', or 'full'
    source_table: str
    source_id: int
    processed_at: datetime


class FileLogListResponse(BaseModel):
    """Response for listing file log entries."""

    entries: list[FileLogSha256Entry]
    total: int
    limit: int
    offset: int


class FileStats(BaseModel):
    """Statistics about tracked files."""

    total_files: int
    total_size: int
    pending_sha256: int  # Files awaiting SHA256 calculation
    pending_uploads: int  # Files with SHA256 but not uploaded
    meta_uploads: int  # Files uploaded as metadata only
    full_uploads: int  # Files uploaded with full content
    paths_watched: int


# Upload models
class UploadRequest(BaseModel):
    """Request to trigger uploads."""

    upload_content: bool = Field(
        default=False,
        description="Upload file content (not just metadata)"
    )
    path_prefix: Optional[str] = Field(
        default=None,
        description="Only upload files under this path"
    )
    process_inline: bool = Field(
        default=True,
        description="Calculate SHA256 inline before upload (faster feedback, default=True)"
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of files to process (for inline mode)"
    )
    server_name: Optional[str] = Field(
        default=None,
        description="Server to upload to (uses default if not specified)"
    )


class UploadProgressInfo(BaseModel):
    """Progress information for an upload."""

    entry_id: int
    filepath: str
    sha256: str
    status: str
    progress_percent: float = 0.0
    bytes_uploaded: int = 0
    total_bytes: int = 0
    error_message: Optional[str] = None


class UploadStatusResponse(BaseModel):
    """Current upload status."""

    is_uploading: bool
    queue_size: int
    in_progress: list[UploadProgressInfo]
    completed_count: int
    failed_count: int


class QueueStatus(BaseModel):
    """Upload queue status."""

    pending_sha256: int
    pending_upload: int
    in_progress: int
    completed_today: int
    failed_today: int


class UploadHistoryRecord(BaseModel):
    """A single upload history record from filelog_sha256."""

    id: int
    filepath: str
    sha256: str
    file_size: int
    upload_status: Optional[str] = None
    processed_at: datetime


class UploadHistoryResponse(BaseModel):
    """Response for upload history."""

    records: list[UploadHistoryRecord]
    total: int
    limit: int
    offset: int


# Server configuration models
class ServerCreate(BaseModel):
    """Request to add a remote server."""

    name: str = Field(..., description="Name for this server")
    url: str = Field(..., description="Server URL (e.g., https://app.putplace.org)")
    username: str = Field(..., description="Username for authentication")
    password: str = Field(..., description="Password for authentication")
    is_default: bool = Field(False, description="Set as default server")


class ServerResponse(BaseModel):
    """Response for a configured server."""

    id: int
    name: str
    url: str
    username: str
    is_default: bool
    created_at: datetime
    # Note: password is never returned


class ServerListResponse(BaseModel):
    """Response for listing servers."""

    servers: list[ServerResponse]
    total: int


# Activity models
class ActivityEvent(BaseModel):
    """An activity event."""

    id: int
    event_type: EventType
    filepath: Optional[str] = None
    path_id: Optional[int] = None
    message: Optional[str] = None
    details: Optional[dict] = None
    created_at: datetime


class ActivityListResponse(BaseModel):
    """Response for listing activity."""

    events: list[ActivityEvent]
    total: int
    has_more: bool


# Status models
class DaemonStatus(BaseModel):
    """Status of the daemon."""

    running: bool
    uptime_seconds: float
    version: str
    watcher_active: bool
    sha256_processor_active: bool
    paths_watched: int
    files_tracked: int
    pending_sha256: int
    pending_uploads: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
    database_ok: bool


# SHA256 processor status
class Sha256ProcessorStatus(BaseModel):
    """Status of the SHA256 processor."""

    is_running: bool
    pending_count: int
    processed_today: int
    failed_today: int
    current_file: Optional[str] = None


# Authentication models
class LoginRequest(BaseModel):
    """Login request."""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """Registration request."""

    username: str
    email: str
    password: str
    full_name: Optional[str] = None


class AuthResponse(BaseModel):
    """Authentication response."""

    success: bool
    token: Optional[str] = None
    error: Optional[str] = None
    user_id: Optional[int] = None
