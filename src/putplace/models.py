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
    sha256: str = Field(..., description="SHA256 hash of the file", min_length=64, max_length=64)

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


# User authentication models


class UserCreate(BaseModel):
    """Request model for user registration."""

    username: str = Field(..., description="Username", min_length=3, max_length=50)
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="Password", min_length=8)
    full_name: Optional[str] = Field(None, description="Full name")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "johndoe",
                "email": "john@example.com",
                "password": "securepassword123",
                "full_name": "John Doe"
            }
        }
    )


class UserLogin(BaseModel):
    """Request model for user login."""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "johndoe",
                "password": "securepassword123"
            }
        }
    )


class GoogleOAuthLogin(BaseModel):
    """Request model for Google OAuth login."""

    id_token: str = Field(..., description="Google ID token")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6..."
            }
        }
    )


class User(BaseModel):
    """User model (without password)."""

    id: Optional[str] = Field(None, alias="_id", description="User ID")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")
    full_name: Optional[str] = Field(None, description="Full name")
    is_active: bool = Field(default=True, description="Whether the user account is active")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When the user was created")
    # OAuth fields
    auth_provider: Optional[str] = Field(None, description="OAuth provider (e.g., 'google', 'local')")
    oauth_id: Optional[str] = Field(None, description="OAuth provider user ID")
    picture: Optional[str] = Field(None, description="Profile picture URL")

    model_config = ConfigDict(populate_by_name=True)


class Token(BaseModel):
    """JWT token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class TokenData(BaseModel):
    """Data stored in JWT token."""

    username: Optional[str] = None


class PendingUser(BaseModel):
    """Pending user awaiting email confirmation."""

    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")
    hashed_password: str = Field(..., description="Hashed password")
    full_name: Optional[str] = Field(None, description="Full name")
    confirmation_token: str = Field(..., description="Email confirmation token")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When pending user was created")
    expires_at: datetime = Field(..., description="When confirmation expires (24 hours)")

    model_config = ConfigDict(populate_by_name=True)


class EmailConfirmationResponse(BaseModel):
    """Response after successful email confirmation."""

    message: str = Field(..., description="Success message")
    user_id: str = Field(..., description="Created user ID")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")
