"""FastAPI dependency injection functions.

This module centralizes all dependency providers to avoid circular imports.
Routers import from here instead of from main.py.
"""

from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import database
from .database import MongoDB
from .storage import StorageBackend
from .user_auth import decode_access_token

# JWT bearer token scheme
security = HTTPBearer()

# Global storage backend instance (set by main.py during lifespan)
storage_backend: StorageBackend | None = None


def get_db() -> MongoDB:
    """Get database instance - dependency injection."""
    return database.mongodb


def get_storage() -> StorageBackend:
    """Get storage backend instance - dependency injection."""
    if storage_backend is None:
        raise RuntimeError("Storage backend not initialized")
    return storage_backend


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: MongoDB = Depends(get_db)
) -> dict:
    """Get current user from JWT token.

    Args:
        credentials: HTTP Authorization credentials with JWT token
        db: Database instance

    Returns:
        User document from database

    Raises:
        HTTPException: If token is invalid or user not found
    """
    # Extract token
    token = credentials.credentials

    # Decode token to get email
    email = decode_access_token(token)

    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user = await db.get_user_by_email(email)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )

    return user


async def get_current_admin_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Get current user and verify they have admin privileges.

    Args:
        current_user: Current authenticated user from get_current_user

    Returns:
        User document if user is an admin

    Raises:
        HTTPException: If user is not an admin
    """
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    return current_user


def get_chunk_storage_dir() -> Path:
    """Get directory for temporary chunk storage."""
    chunk_dir = Path("/tmp/putplace_chunks")
    chunk_dir.mkdir(parents=True, exist_ok=True)
    return chunk_dir
