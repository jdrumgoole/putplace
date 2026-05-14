"""Data models for file metadata and authentication."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FileMetadata(BaseModel):
    """File metadata document."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filepath": "/var/log/app.log",
                "hostname": "server01",
                "ip_address": "192.168.1.100",
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "file_size": 2048,
                "file_mode": 33188,
                "file_uid": 1000,
                "file_gid": 1000,
                "file_mtime": 1609459200.0,
                "file_atime": 1609459200.0,
                "file_ctime": 1609459200.0,
            }
        }
    )

    filepath: str = Field(..., description="Full path to the file")
    hostname: str = Field(..., description="Hostname where the file is located")
    ip_address: str = Field(..., description="IP address of the host")
    sha256: str = Field(
        ...,
        description="SHA256 hash of the file",
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$"  # Security: Prevent path traversal - must be exactly 64 hex chars
    )

    # File stat information
    file_size: int = Field(..., description="File size in bytes", ge=0)
    file_mode: int = Field(..., description="File mode (permissions)")
    file_uid: int = Field(..., description="User ID of file owner")
    file_gid: int = Field(..., description="Group ID of file owner")
    file_mtime: float = Field(..., description="Modification time (Unix timestamp)")
    file_atime: float = Field(..., description="Access time (Unix timestamp)")
    file_ctime: float = Field(..., description="Change/creation time (Unix timestamp)")

    # File content tracking
    has_file_content: bool = Field(default=False, description="Whether server has the actual file content")
    file_uploaded_at: Optional[datetime] = Field(None, description="When file content was uploaded")
    storage_path: Optional[str] = Field(None, description="Full path where file content is stored (local path or S3 URI)")

    # User tracking (who uploaded this file)
    uploaded_by_user_id: Optional[str] = Field(None, description="User ID who uploaded this file")
    uploaded_by_api_key_id: Optional[str] = Field(None, description="API key ID used to upload this file")

    # Metadata timestamp
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Database record timestamp")


class FileMetadataResponse(FileMetadata):
    """Response model with MongoDB ID."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id", description="MongoDB document ID")


class FileMetadataUploadResponse(FileMetadataResponse):
    """Response model that includes upload requirement information."""

    upload_required: bool = Field(..., description="Whether client needs to upload file content")
    upload_url: Optional[str] = Field(None, description="URL to upload file content (if required)")


# Authentication models


class APIKeyCreate(BaseModel):
    """Request model for creating a new API key."""

    name: str = Field(..., description="Name/identifier for this API key", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="Optional description of the key's purpose")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "production-server-01",
                "description": "API key for production server #1"
            }
        }
    )


class APIKeyResponse(BaseModel):
    """Response model for API key creation (includes the actual key)."""

    api_key: str = Field(..., description="The API key - SAVE THIS! It won't be shown again.")
    id: str = Field(..., alias="_id", description="API key ID")
    name: str = Field(..., description="Name of the API key")
    description: Optional[str] = Field(None, description="Description")
    created_at: datetime = Field(..., description="When the key was created")
    is_active: bool = Field(..., description="Whether the key is active")

    model_config = ConfigDict(populate_by_name=True)


class APIKeyInfo(BaseModel):
    """Information about an API key (without the actual key)."""

    id: str = Field(..., alias="_id", description="API key ID")
    name: str = Field(..., description="Name of the API key")
    description: Optional[str] = Field(None, description="Description")
    created_at: datetime = Field(..., description="When the key was created")
    last_used_at: Optional[datetime] = Field(None, description="When the key was last used")
    is_active: bool = Field(..., description="Whether the key is active")

    model_config = ConfigDict(populate_by_name=True)


# User accounts are owned by regstack (regstack.models.user.BaseUser etc.).
# The legacy putplace user/login/OAuth/email-confirmation models lived here
# until the regstack cutover removed the endpoints that referenced them.


# Chunked upload models


class ChunkInfo(BaseModel):
    """Information about an uploaded chunk."""

    chunk_num: int = Field(..., description="Chunk number (0-indexed)")
    etag: str = Field(..., description="Chunk hash/ETag for integrity verification")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow, description="When chunk was uploaded")


class UploadSessionInitiate(BaseModel):
    """Request to initiate a chunked upload."""

    filepath: str = Field(..., description="Full path to the file")
    hostname: str = Field(..., description="Hostname where file is located")
    sha256: str = Field(
        ...,
        description="SHA256 hash of the complete file",
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$"
    )
    file_size: int = Field(..., description="Total file size in bytes", ge=0)
    chunk_size: int = Field(..., description="Size of each chunk in bytes", ge=1024, le=10485760)  # 1KB to 10MB
    total_chunks: int = Field(..., description="Total number of chunks", ge=1)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filepath": "/path/to/file.txt",
                "hostname": "client-machine",
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "file_size": 104857600,
                "chunk_size": 2097152,
                "total_chunks": 50
            }
        }
    )


class UploadSessionResponse(BaseModel):
    """Response after initiating an upload session."""

    upload_id: str = Field(..., description="Unique upload session ID")
    expires_at: datetime = Field(..., description="When this upload session expires (1 hour)")
    message: str = Field(default="Upload session created", description="Status message")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "upload_id": "uuid-1234-5678-90ab-cdef",
                "expires_at": "2026-01-05T14:00:00Z",
                "message": "Upload session created"
            }
        }
    )


class ChunkUploadResponse(BaseModel):
    """Response after uploading a chunk."""

    chunk_num: int = Field(..., description="Chunk number that was uploaded")
    etag: str = Field(..., description="Chunk hash/ETag")
    received_bytes: int = Field(..., description="Number of bytes received")
    uploaded_chunks: int = Field(..., description="Total chunks uploaded so far")
    total_chunks: int = Field(..., description="Total chunks expected")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chunk_num": 0,
                "etag": "chunk-hash-abc123",
                "received_bytes": 2097152,
                "uploaded_chunks": 1,
                "total_chunks": 50
            }
        }
    )


class UploadCompleteRequest(BaseModel):
    """Request to complete a chunked upload."""

    parts: list[dict[str, int | str]] = Field(..., description="List of uploaded chunks with etags")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "parts": [
                    {"chunk_num": 0, "etag": "chunk-hash-abc123"},
                    {"chunk_num": 1, "etag": "chunk-hash-def456"}
                ]
            }
        }
    )


class UploadCompleteResponse(BaseModel):
    """Response after completing an upload."""

    file_id: str = Field(..., description="File metadata ID")
    sha256: str = Field(..., description="SHA256 hash of the file")
    file_size: int = Field(..., description="Total file size")
    status: str = Field(default="completed", description="Upload status")
    storage_location: str = Field(..., description="Where file is stored (path or S3 URI)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "file-uuid",
                "sha256": "abc123...",
                "file_size": 104857600,
                "status": "completed",
                "storage_location": "s3://bucket/files/abc123..."
            }
        }
    )


# File deletion notification models


class FileDeletionNotification(BaseModel):
    """Notification that a file has been deleted on the client."""

    filepath: str = Field(..., description="Full path to the deleted file")
    hostname: str = Field(..., description="Hostname where file was located")
    deleted_at: datetime = Field(..., description="When file was deleted")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filepath": "/path/to/deleted/file.txt",
                "hostname": "client-machine",
                "deleted_at": "2026-01-05T12:00:00Z"
            }
        }
    )


class FileDeletionResponse(BaseModel):
    """Response after recording file deletion."""

    sha256: str = Field(..., description="SHA256 hash of deleted file")
    filepath: str = Field(..., description="Filepath")
    hostname: str = Field(..., description="Hostname")
    status: str = Field(default="deleted", description="Deletion status")
    deleted_at: datetime = Field(..., description="When file was marked as deleted")
