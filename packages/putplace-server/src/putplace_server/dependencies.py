"""FastAPI dependency injection functions.

This module centralizes all dependency providers to avoid circular imports.
Routers import from here instead of from main.py.
"""

from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import database
from .database import MongoDB
from .regstack_integration import get_regstack
from .storage import StorageBackend

# auto_error=False so tests covering "no Authorization header" reach our 401
# branch and never fall through to FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)

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
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Authenticate the request via regstack and return a putplace-shaped user dict.

    The singleton is resolved at request time (not module-load) so that
    teardown-and-rebuild flows in tests pick up a fresh client. The dict shape
    matches what the file/upload/api-key routers already expect: ``_id``,
    ``email``, ``is_active``, ``is_admin``, ``full_name``.
    """
    rs = get_regstack()
    base_user = await rs.deps._authenticate(creds)
    return {
        "_id": base_user.id,
        "email": base_user.email,
        "is_active": base_user.is_active,
        "is_admin": base_user.is_superuser,
        "full_name": base_user.full_name,
    }


async def get_current_admin_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def get_chunk_storage_dir() -> Path:
    """Get directory for temporary chunk storage."""
    chunk_dir = Path("/tmp/putplace_chunks")
    chunk_dir.mkdir(parents=True, exist_ok=True)
    return chunk_dir
