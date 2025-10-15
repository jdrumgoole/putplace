"""Data models for file metadata."""

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
    sha256: str = Field(..., description="SHA256 hash of the file", min_length=64, max_length=64)

    # File stat information
    file_size: int = Field(..., description="File size in bytes", ge=0)
    file_mode: int = Field(..., description="File mode (permissions)")
    file_uid: int = Field(..., description="User ID of file owner")
    file_gid: int = Field(..., description="Group ID of file owner")
    file_mtime: float = Field(..., description="Modification time (Unix timestamp)")
    file_atime: float = Field(..., description="Access time (Unix timestamp)")
    file_ctime: float = Field(..., description="Change/creation time (Unix timestamp)")

    # Metadata timestamp
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Database record timestamp")


class FileMetadataResponse(FileMetadata):
    """Response model with MongoDB ID."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id", description="MongoDB document ID")
