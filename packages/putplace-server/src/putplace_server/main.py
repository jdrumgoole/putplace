"""FastAPI application for file metadata storage."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pymongo.errors import ConnectionFailure

from .config import settings
from . import database
from .auth import APIKeyAuth, get_current_api_key
from .database import MongoDB
from .models import (
    APIKeyCreate,
    APIKeyInfo,
    APIKeyResponse,
    FileMetadata,
    FileMetadataResponse,
    FileMetadataUploadResponse,
    GoogleOAuthLogin,
    Token,
    User,
    UserCreate,
    UserLogin,
)
from .storage import get_storage_backend, StorageBackend
from .templates import (
    get_home_page,
    get_login_page,
    get_register_page,
    get_awaiting_confirmation_page,
)

logger = logging.getLogger(__name__)

# Global storage backend instance
storage_backend: StorageBackend | None = None


async def ensure_admin_exists(db: MongoDB) -> None:
    """Ensure an admin user exists using multiple fallback methods.

    This function implements a hybrid approach:
    1. If users exist, do nothing
    2. If PUTPLACE_ADMIN_EMAIL and PUTPLACE_ADMIN_PASSWORD are set, use them
    3. Otherwise, generate a random password and display it once

    Args:
        db: MongoDB database instance
    """
    from datetime import datetime

    try:
        # Check if any users exist
        user_count = await db.users_collection.count_documents({})
        if user_count > 0:
            logger.debug("Users already exist, skipping admin creation")
            return  # Users exist, nothing to do

        # Method 1: Try environment variables (best for production/containers)
        admin_email = os.getenv("PUTPLACE_ADMIN_EMAIL", "admin@localhost")
        admin_pass = os.getenv("PUTPLACE_ADMIN_PASSWORD")

        if admin_pass:
            # Validate password strength
            if len(admin_pass) < 8:
                logger.error(
                    "PUTPLACE_ADMIN_PASSWORD must be at least 8 characters. "
                    "Admin user not created."
                )
                return

            # Create admin from environment variables
            from .user_auth import get_password_hash

            hashed_password = get_password_hash(admin_pass)
            user_doc = {
                "email": admin_email,
                "username": admin_email,  # Use email as username
                "hashed_password": hashed_password,
                "full_name": "Administrator",
                "is_active": True,
                "is_admin": True,
                "created_at": datetime.utcnow(),
            }

            await db.users_collection.insert_one(user_doc)
            logger.info(f"✅ Created admin user from environment: {admin_email}")
            return

        # Method 2: Generate random password (fallback for development)
        import secrets
        random_password = secrets.token_urlsafe(16)  # 16 bytes = ~21 chars

        from .user_auth import get_password_hash

        hashed_password = get_password_hash(random_password)
        user_doc = {
            "email": "admin@localhost",
            "username": "admin@localhost",  # Use email as username
            "hashed_password": hashed_password,
            "full_name": "Administrator",
            "is_active": True,
            "is_admin": True,
            "created_at": datetime.utcnow(),
        }

        await db.users_collection.insert_one(user_doc)

        # Display credentials prominently in logs
        logger.warning("=" * 80)
        logger.warning("🔐 INITIAL ADMIN CREDENTIALS GENERATED")
        logger.warning("=" * 80)
        logger.warning(f"   Email: admin@localhost")
        logger.warning(f"   Password: {random_password}")
        logger.warning("")
        logger.warning("⚠️  SAVE THESE CREDENTIALS NOW - They won't be shown again!")
        logger.warning("")
        logger.warning("For production, set environment variables instead:")
        logger.warning("   PUTPLACE_ADMIN_EMAIL=admin@example.com")
        logger.warning("   PUTPLACE_ADMIN_PASSWORD=your-secure-password")
        logger.warning("=" * 80)

        # Also write to a temporary file
        from pathlib import Path
        import tempfile

        creds_dir = Path(tempfile.gettempdir())
        creds_file = creds_dir / "putplace_initial_creds.txt"

        try:
            creds_file.write_text(
                f"PutPlace Initial Admin Credentials\n"
                f"{'=' * 40}\n"
                f"Email: admin@localhost\n"
                f"Password: {random_password}\n"
                f"Created: {datetime.utcnow()}\n\n"
                f"⚠️  DELETE THIS FILE after saving credentials!\n"
            )
            creds_file.chmod(0o600)  # Owner read/write only
            logger.warning(f"📄 Credentials also written to: {creds_file}")
            logger.warning("")
        except Exception as e:
            logger.debug(f"Could not write credentials file: {e}")

    except Exception as e:
        logger.error(f"Failed to ensure admin user exists: {e}")
        # Don't raise - allow app to start even if admin creation fails


def get_db() -> MongoDB:
    """Get database instance - dependency injection."""
    return database.mongodb


def get_storage() -> StorageBackend:
    """Get storage backend instance - dependency injection."""
    if storage_backend is None:
        raise RuntimeError("Storage backend not initialized")
    return storage_backend


# JWT bearer token scheme
security = HTTPBearer()


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
    from .user_auth import decode_access_token

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan events."""
    global storage_backend

    # Startup
    try:
        await database.mongodb.connect()
        logger.info("Application startup: Database connected successfully")

        # Start cleanup task for expired pending users
        from .cleanup_tasks import start_cleanup_task
        start_cleanup_task()

    except ConnectionFailure as e:
        logger.error(f"Failed to connect to database during startup: {e}")
        logger.warning("Application starting without database connection - health endpoint will report degraded")
        # Don't raise - allow app to start in degraded mode
    except Exception as e:
        logger.error(f"Unexpected error during startup: {e}")
        raise

    # Initialize storage backend
    try:
        if settings.storage_backend == "local":
            storage_backend = get_storage_backend(
                "local",
                base_path=settings.storage_path,
            )
            logger.info(f"Initialized local storage backend at {settings.storage_path}")

            # Test write access to storage directory
            from pathlib import Path
            storage_path = Path(settings.storage_path).resolve()

            # Create directory if it doesn't exist
            if not storage_path.exists():
                try:
                    storage_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created storage directory: {storage_path}")
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to create storage directory: {storage_path}\n"
                        f"Error: {e}\n"
                        f"Please ensure the parent directory is writable or create it manually."
                    )

            if not storage_path.is_dir():
                raise RuntimeError(
                    f"Storage path is not a directory: {storage_path}\n"
                    f"Please ensure STORAGE_PATH points to a valid directory."
                )

            # Test write permission by creating and removing a test file
            import uuid
            test_filename = f".write_test_{uuid.uuid4().hex}"
            test_file = storage_path / test_filename

            # Ensure test file doesn't already exist (extremely unlikely with UUID)
            if test_file.exists():
                raise RuntimeError(
                    f"Test file unexpectedly exists: {test_file}\n"
                    f"Please remove it and restart the server."
                )

            try:
                test_file.write_text("test")
                test_file.unlink()
                logger.info(f"Storage directory write test successful: {storage_path}")
            except PermissionError as e:
                raise RuntimeError(
                    f"Cannot write to storage directory: {storage_path}\n"
                    f"Error: {e}\n"
                    f"Please check directory permissions or update STORAGE_PATH in your .env file."
                ) from e
            except Exception as e:
                # Clean up test file if it was created
                if test_file.exists():
                    try:
                        test_file.unlink()
                    except:
                        pass
                raise RuntimeError(
                    f"Failed to write to storage directory: {storage_path}\n"
                    f"Error: {e}"
                ) from e

        elif settings.storage_backend == "s3":
            if not settings.s3_bucket_name:
                raise ValueError("S3 bucket name not configured")
            storage_backend = get_storage_backend(
                "s3",
                bucket_name=settings.s3_bucket_name,
                region_name=settings.s3_region_name,
                prefix=settings.s3_prefix,
                aws_profile=settings.aws_profile,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
            logger.info(
                f"Initialized S3 storage backend: bucket={settings.s3_bucket_name}, "
                f"region={settings.s3_region_name}"
            )
        else:
            raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")
    except Exception as e:
        logger.error(f"Failed to initialize storage backend: {e}")
        raise

    # Ensure admin user exists (only creates if no users exist)
    if database.mongodb.client is not None:
        await ensure_admin_exists(database.mongodb)

    yield

    # Shutdown
    try:
        await database.mongodb.close()
        logger.info("Application shutdown: Database connection closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    lifespan=lifespan,
)

# Mount static files directory
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info(f"Static files mounted at /static from {STATIC_DIR}")


@app.get("/", response_class=HTMLResponse, tags=["health"])
async def root() -> str:
    """Root endpoint - Home page."""
    return get_home_page(settings.api_version)


@app.get("/downloads", tags=["pages"])
async def downloads_page() -> RedirectResponse:
    """Redirect to the main website downloads page."""
    return RedirectResponse(url="https://putplace.org/downloads.html", status_code=301)


@app.get("/health", tags=["health"])
async def health(db: MongoDB = Depends(get_db)) -> dict[str, str | dict]:
    """Health check endpoint with database connectivity check."""
    db_healthy = await db.is_healthy()

    if db_healthy:
        return {
            "status": "healthy",
            "database": {"status": "connected", "type": "mongodb"}
        }
    else:
        return {
            "status": "degraded",
            "database": {"status": "disconnected", "type": "mongodb"}
        }


@app.post(
    "/put_file",
    response_model=FileMetadataUploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["files"],
)
async def put_file(
    file_metadata: FileMetadata,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> FileMetadataUploadResponse:
    """Store file metadata in MongoDB.

    Requires authentication via JWT Bearer token.

    Args:
        file_metadata: File metadata containing filepath, hostname, ip_address, and sha256
        db: Database instance (injected)
        current_user: Current authenticated user (injected, for authentication)

    Returns:
        Stored file metadata with MongoDB ID and upload requirement information

    Raises:
        HTTPException: If database operation fails or authentication fails
    """
    try:
        # Check if we already have the file content for this SHA256
        has_content = await db.has_file_content(file_metadata.sha256)

        # Convert to dict for MongoDB insertion
        data = file_metadata.model_dump()

        # Track which user uploaded this file
        data["uploaded_by_user_id"] = str(current_user.get("_id"))
        data["uploaded_by_email"] = current_user.get("email")

        # Insert into MongoDB
        doc_id = await db.insert_file_metadata(data)

        # Determine if upload is required
        # Skip upload requirement for 0-byte files (no content to upload)
        is_zero_byte_file = file_metadata.file_size == 0
        upload_required = not has_content and not is_zero_byte_file
        upload_url = None
        if upload_required:
            # Provide the upload URL
            upload_url = f"/upload_file/{file_metadata.sha256}"

        # Return response with ID and upload information
        return FileMetadataUploadResponse(
            **data, _id=doc_id, upload_required=upload_required, upload_url=upload_url
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store file metadata: {str(e)}",
        ) from e


@app.get(
    "/get_file/{sha256}",
    response_model=FileMetadataResponse,
    tags=["files"],
)
async def get_file(
    sha256: str,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> FileMetadataResponse:
    """Retrieve file metadata by SHA256 hash.

    Requires authentication via JWT Bearer token.

    Args:
        sha256: SHA256 hash of the file (64 characters)
        db: Database instance (injected)
        api_key: API key metadata (injected, for authentication)

    Returns:
        File metadata if found

    Raises:
        HTTPException: If file not found, invalid hash, or authentication fails
    """
    if len(sha256) != 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SHA256 hash must be exactly 64 characters",
        )

    result = await db.find_by_sha256(sha256)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with SHA256 {sha256} not found",
        )

    # Convert MongoDB _id to string
    result["_id"] = str(result["_id"])

    return FileMetadataResponse(**result)


@app.post(
    "/upload_file/{sha256}",
    status_code=status.HTTP_200_OK,
    tags=["files"],
)
async def upload_file(
    sha256: str,
    hostname: str,
    filepath: str,
    file: UploadFile = File(...),
    db: MongoDB = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Upload actual file content for a previously registered file metadata.

    Requires authentication via JWT Bearer token.

    This endpoint supports streaming uploads for large files (up to 50GB).
    File content is streamed in chunks to avoid memory issues:
    - SHA256 hash is calculated incrementally during streaming
    - Content is stored using the configured storage backend (local or S3)
    - For S3, multipart upload is used for efficient large file handling

    Args:
        sha256: SHA256 hash of the file (must match file content)
        hostname: Hostname where file is located
        filepath: Full path to the file
        file: File upload
        db: Database instance (injected)
        storage: Storage backend instance (injected)
        current_user: Authenticated user (injected)

    Returns:
        Success message with details

    Raises:
        HTTPException: If validation fails, database operation fails, or authentication fails
    """
    import hashlib

    if len(sha256) != 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SHA256 hash must be exactly 64 characters",
        )

    # Streaming chunk size: 1MB chunks for efficient memory usage
    CHUNK_SIZE = 1024 * 1024  # 1MB

    # Hash calculator for incremental SHA256
    hash_calculator = hashlib.sha256()
    total_size = 0

    async def streaming_hash_generator():
        """Async generator that reads file in chunks and calculates hash incrementally."""
        nonlocal total_size
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            hash_calculator.update(chunk)
            total_size += len(chunk)
            yield chunk

    try:
        # Get content length from headers if available (for logging)
        content_length = file.size or 0

        logger.info(
            f"Starting streaming upload for SHA256: {sha256}, "
            f"expected size: {content_length} bytes"
        )

        # Store file content using streaming
        stored = await storage.store_stream(
            sha256,
            streaming_hash_generator(),
            content_length,
        )

        if not stored:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store file content",
            )

        # Verify hash after streaming completes
        calculated_hash = hash_calculator.hexdigest()

        if calculated_hash != sha256:
            # Hash mismatch - delete the stored file
            logger.error(
                f"SHA256 mismatch for upload: expected {sha256}, got {calculated_hash}"
            )
            try:
                await storage.delete(sha256)
                logger.info(f"Deleted mismatched file: {sha256}")
            except Exception as delete_error:
                logger.error(f"Failed to delete mismatched file {sha256}: {delete_error}")

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File content SHA256 ({calculated_hash}) does not match provided hash ({sha256})",
            )

        logger.info(f"File upload verified for SHA256: {sha256}, size: {total_size} bytes")

        # Get the storage path where file was stored
        storage_path = storage.get_storage_path(sha256)

        # Mark the file as uploaded in database with storage path
        updated = await db.mark_file_uploaded(sha256, hostname, filepath, storage_path)

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No metadata found for sha256={sha256}, hostname={hostname}, filepath={filepath}",
            )

        return {
            "message": "File uploaded successfully",
            "sha256": sha256,
            "size": str(total_size),
            "hostname": hostname,
            "filepath": filepath,
            "status": "uploaded",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        ) from e


# API Key Management Endpoints


@app.post(
    "/api_keys",
    response_model=APIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
async def create_api_key(
    key_data: APIKeyCreate,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> APIKeyResponse:
    """Create a new API key.

    Requires user authentication via JWT Bearer token.
    Include the token in the Authorization header: `Authorization: Bearer <token>`

    Args:
        key_data: API key creation data (name, description)
        db: Database instance (injected)
        current_user: Current logged-in user (injected, for authentication)

    Returns:
        The new API key and its metadata. SAVE THE API KEY - it won't be shown again!

    Raises:
        HTTPException: If database operation fails or authentication fails
    """
    auth = APIKeyAuth(db)

    try:
        # Create new API key associated with the current user
        new_api_key, key_metadata = await auth.create_api_key(
            name=key_data.name,
            user_id=str(current_user["_id"]),  # Associate with logged-in user
            description=key_data.description,
        )

        # Return the key (only time it's shown)
        return APIKeyResponse(
            api_key=new_api_key,
            **key_metadata,
        )

    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}",
        ) from e


@app.get(
    "/api_keys",
    response_model=list[APIKeyInfo],
    tags=["auth"],
)
async def list_api_keys(
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[APIKeyInfo]:
    """List all API keys for the current user (without showing the actual keys).

    Requires user authentication via JWT Bearer token.

    Args:
        db: Database instance (injected)
        current_user: Current logged-in user (injected, for authentication)

    Returns:
        List of API key metadata owned by the current user

    Raises:
        HTTPException: If database operation fails or authentication fails
    """
    auth = APIKeyAuth(db)

    try:
        # List only the keys owned by the current user
        keys = await auth.list_api_keys(user_id=str(current_user["_id"]))
        return [APIKeyInfo(**key) for key in keys]

    except Exception as e:
        logger.error(f"Error listing API keys: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list API keys: {str(e)}",
        ) from e


@app.delete(
    "/api_keys/{key_id}",
    status_code=status.HTTP_200_OK,
    tags=["auth"],
)
async def delete_api_key(
    key_id: str,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Permanently delete an API key.

    Requires user authentication via JWT Bearer token.

    WARNING: This cannot be undone! Consider using PUT /api_keys/{key_id}/revoke instead.

    Args:
        key_id: API key ID to delete
        db: Database instance (injected)
        current_user: Current logged-in user (injected, for authentication)

    Returns:
        Success message

    Raises:
        HTTPException: If key not found, database operation fails, or authentication fails
    """
    auth = APIKeyAuth(db)

    try:
        deleted = await auth.delete_api_key(key_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key {key_id} not found",
            )

        return {"message": f"API key {key_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}",
        ) from e


@app.put(
    "/api_keys/{key_id}/revoke",
    status_code=status.HTTP_200_OK,
    tags=["auth"],
)
async def revoke_api_key(
    key_id: str,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Revoke (deactivate) an API key without deleting it.

    Requires user authentication via JWT Bearer token.

    The key will be marked as inactive and can no longer be used for authentication,
    but its metadata is retained for audit purposes.

    Args:
        key_id: API key ID to revoke
        db: Database instance (injected)
        current_user: Current logged-in user (injected, for authentication)

    Returns:
        Success message

    Raises:
        HTTPException: If key not found, database operation fails, or authentication fails
    """
    auth = APIKeyAuth(db)

    try:
        revoked = await auth.revoke_api_key(key_id)

        if not revoked:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key {key_id} not found",
            )

        return {"message": f"API key {key_id} revoked successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke API key: {str(e)}",
        ) from e


# User Authentication Endpoints


@app.get("/api_keys_page", response_class=HTMLResponse, tags=["users"])
async def api_keys_page() -> str:
    """API Keys management page."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>API Keys - PutPlace</title>
        <link rel="icon" type="image/svg+xml" href="/static/images/favicon.svg">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .header h1 {
                font-size: 2rem;
            }
            .logout-btn {
                padding: 8px 16px;
                background: rgba(255, 255, 255, 0.2);
                color: white;
                border: 2px solid white;
                border-radius: 5px;
                cursor: pointer;
                font-weight: 500;
                text-decoration: none;
                transition: all 0.3s ease;
            }
            .logout-btn:hover {
                background: white;
                color: #667eea;
            }
            .content {
                padding: 40px;
            }
            .message {
                padding: 12px;
                border-radius: 5px;
                margin-bottom: 20px;
                display: none;
            }
            .message.error {
                background: #fee;
                color: #c33;
                border: 1px solid #fcc;
            }
            .message.success {
                background: #efe;
                color: #3c3;
                border: 1px solid #cfc;
            }
            .message.info {
                background: #e7f3ff;
                color: #004085;
                border: 1px solid #b8daff;
            }
            .section {
                margin-bottom: 30px;
            }
            .section h2 {
                color: #667eea;
                margin-bottom: 15px;
                font-size: 1.5rem;
                border-bottom: 2px solid #667eea;
                padding-bottom: 5px;
            }
            .form-group {
                margin-bottom: 15px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 500;
            }
            .form-group input,
            .form-group textarea {
                width: 100%;
                padding: 10px;
                border: 2px solid #e0e0e0;
                border-radius: 5px;
                font-size: 1rem;
            }
            .form-group input:focus,
            .form-group textarea:focus {
                outline: none;
                border-color: #667eea;
            }
            .btn {
                padding: 10px 20px;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 1rem;
                font-weight: 500;
                transition: all 0.3s ease;
            }
            .btn:hover {
                background: #764ba2;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .btn:disabled {
                background: #ccc;
                cursor: not-allowed;
                transform: none;
            }
            .btn-danger {
                background: #dc3545;
            }
            .btn-danger:hover {
                background: #c82333;
            }
            .btn-warning {
                background: #ffc107;
                color: #333;
            }
            .btn-warning:hover {
                background: #e0a800;
            }
            .btn-small {
                padding: 5px 10px;
                font-size: 0.85rem;
            }
            .keys-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }
            .keys-table th,
            .keys-table td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #e0e0e0;
            }
            .keys-table th {
                background: #f8f9fa;
                font-weight: 600;
                color: #667eea;
            }
            .keys-table tr:hover {
                background: #f8f9fa;
            }
            .status-active {
                color: #28a745;
                font-weight: 500;
            }
            .status-inactive {
                color: #dc3545;
                font-weight: 500;
            }
            .key-actions {
                display: flex;
                gap: 5px;
            }
            .no-keys {
                text-align: center;
                padding: 40px;
                color: #6c757d;
            }
            .key-display {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 5px;
                border: 2px solid #667eea;
                margin: 15px 0;
                font-family: 'Courier New', monospace;
                word-break: break-all;
            }
            .key-warning {
                background: #fff3cd;
                border: 1px solid #ffc107;
                padding: 15px;
                border-radius: 5px;
                margin: 15px 0;
            }
            .back-link {
                display: inline-block;
                margin-top: 20px;
                color: #667eea;
                text-decoration: none;
            }
            .back-link:hover {
                color: #764ba2;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔑 My API Keys</h1>
                <div>
                    <a href="/" class="logout-btn">← Home</a>
                    <button onclick="logout()" class="logout-btn" style="margin-left: 10px;">Logout</button>
                </div>
            </div>

            <div class="content">
                <div id="message" class="message"></div>

                <!-- Create New API Key Section -->
                <div class="section">
                    <h2>Create New API Key</h2>
                    <form id="createKeyForm">
                        <div class="form-group">
                            <label for="keyName">Name *</label>
                            <input type="text" id="keyName" required placeholder="e.g., Production Server">
                        </div>
                        <div class="form-group">
                            <label for="keyDescription">Description</label>
                            <textarea id="keyDescription" rows="3" placeholder="Optional description"></textarea>
                        </div>
                        <button type="submit" class="btn">Create API Key</button>
                    </form>

                    <div id="newKeyDisplay" style="display: none;">
                        <div class="key-warning">
                            <strong>⚠️ Save this API key now!</strong> You won't be able to see it again.
                        </div>
                        <div class="key-display" id="newKeyValue"></div>
                        <button onclick="copyKey()" class="btn">Copy to Clipboard</button>
                        <button onclick="closeKeyDisplay()" class="btn btn-warning">Done</button>
                    </div>
                </div>

                <!-- Existing API Keys Section -->
                <div class="section">
                    <h2>Your API Keys</h2>
                    <div id="keysContainer">
                        <p class="no-keys">Loading...</p>
                    </div>
                </div>

                <a href="/" class="back-link">← Back to Home</a>
            </div>
        </div>

        <script>
            let currentToken = null;
            let newApiKey = null;

            // Check if user is logged in
            function checkAuth() {
                currentToken = localStorage.getItem('access_token');
                if (!currentToken) {
                    window.location.href = '/login';
                    return false;
                }
                return true;
            }

            // Logout function
            function logout() {
                localStorage.removeItem('access_token');
                window.location.href = '/';
            }

            // Load API keys
            async function loadApiKeys() {
                if (!checkAuth()) return;

                try {
                    const response = await fetch('/api_keys', {
                        headers: {
                            'Authorization': `Bearer ${currentToken}`
                        }
                    });

                    if (response.status === 401) {
                        logout();
                        return;
                    }

                    if (!response.ok) {
                        throw new Error('Failed to load API keys');
                    }

                    const keys = await response.json();
                    displayApiKeys(keys);
                } catch (error) {
                    showMessage('Error loading API keys: ' + error.message, 'error');
                }
            }

            // Display API keys in table
            function displayApiKeys(keys) {
                const container = document.getElementById('keysContainer');

                if (keys.length === 0) {
                    container.innerHTML = '<p class="no-keys">No API keys yet. Create one above to get started!</p>';
                    return;
                }

                let html = '<table class="keys-table"><thead><tr>';
                html += '<th>Name</th><th>Description</th><th>Created</th><th>Last Used</th><th>Status</th><th>Actions</th>';
                html += '</tr></thead><tbody>';

                keys.forEach(key => {
                    const createdDate = new Date(key.created_at).toLocaleDateString();
                    const lastUsed = key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never';
                    const statusClass = key.is_active ? 'status-active' : 'status-inactive';
                    const status = key.is_active ? 'Active' : 'Inactive';

                    html += '<tr>';
                    html += `<td><strong>${escapeHtml(key.name)}</strong></td>`;
                    html += `<td>${escapeHtml(key.description || '-')}</td>`;
                    html += `<td>${createdDate}</td>`;
                    html += `<td>${lastUsed}</td>`;
                    html += `<td class="${statusClass}">${status}</td>`;
                    html += '<td><div class="key-actions">';

                    if (key.is_active) {
                        html += `<button class="btn btn-warning btn-small" onclick="revokeKey('${key._id}')">Revoke</button>`;
                    }
                    html += `<button class="btn btn-danger btn-small" onclick="deleteKey('${key._id}')">Delete</button>`;
                    html += '</div></td>';
                    html += '</tr>';
                });

                html += '</tbody></table>';
                container.innerHTML = html;
            }

            // Escape HTML to prevent XSS
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            // Create new API key
            document.getElementById('createKeyForm').addEventListener('submit', async (e) => {
                e.preventDefault();

                const name = document.getElementById('keyName').value;
                const description = document.getElementById('keyDescription').value;
                const submitBtn = e.target.querySelector('button[type="submit"]');

                submitBtn.disabled = true;
                submitBtn.textContent = 'Creating...';

                try {
                    const response = await fetch('/api_keys', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${currentToken}`
                        },
                        body: JSON.stringify({ name, description: description || null })
                    });

                    if (response.status === 401) {
                        logout();
                        return;
                    }

                    const data = await response.json();

                    if (response.ok) {
                        newApiKey = data.api_key;
                        document.getElementById('newKeyValue').textContent = newApiKey;
                        document.getElementById('newKeyDisplay').style.display = 'block';
                        document.getElementById('createKeyForm').reset();
                        showMessage('API key created successfully!', 'success');
                        loadApiKeys();
                    } else {
                        showMessage(data.detail || 'Failed to create API key', 'error');
                    }
                } catch (error) {
                    showMessage('Error: ' + error.message, 'error');
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Create API Key';
                }
            });

            // Copy key to clipboard
            function copyKey() {
                navigator.clipboard.writeText(newApiKey).then(() => {
                    showMessage('API key copied to clipboard!', 'success');
                });
            }

            // Close new key display
            function closeKeyDisplay() {
                document.getElementById('newKeyDisplay').style.display = 'none';
                newApiKey = null;
            }

            // Revoke API key
            async function revokeKey(keyId) {
                if (!confirm('Are you sure you want to revoke this API key? It will no longer work.')) {
                    return;
                }

                try {
                    const response = await fetch(`/api_keys/${keyId}/revoke`, {
                        method: 'PUT',
                        headers: {
                            'Authorization': `Bearer ${currentToken}`
                        }
                    });

                    if (response.status === 401) {
                        logout();
                        return;
                    }

                    if (response.ok) {
                        showMessage('API key revoked successfully', 'success');
                        loadApiKeys();
                    } else {
                        const data = await response.json();
                        showMessage(data.detail || 'Failed to revoke API key', 'error');
                    }
                } catch (error) {
                    showMessage('Error: ' + error.message, 'error');
                }
            }

            // Delete API key
            async function deleteKey(keyId) {
                if (!confirm('Are you sure you want to permanently delete this API key? This cannot be undone!')) {
                    return;
                }

                try {
                    const response = await fetch(`/api_keys/${keyId}`, {
                        method: 'DELETE',
                        headers: {
                            'Authorization': `Bearer ${currentToken}`
                        }
                    });

                    if (response.status === 401) {
                        logout();
                        return;
                    }

                    if (response.ok) {
                        showMessage('API key deleted successfully', 'success');
                        loadApiKeys();
                    } else {
                        const data = await response.json();
                        showMessage(data.detail || 'Failed to delete API key', 'error');
                    }
                } catch (error) {
                    showMessage('Error: ' + error.message, 'error');
                }
            }

            // Show message
            function showMessage(text, type) {
                const messageDiv = document.getElementById('message');
                messageDiv.textContent = text;
                messageDiv.className = 'message ' + type;
                messageDiv.style.display = 'block';

                setTimeout(() => {
                    messageDiv.style.display = 'none';
                }, 5000);
            }

            // Initialize
            if (checkAuth()) {
                loadApiKeys();
            }
        </script>
    </body>
    </html>
    """
    return html_content


@app.get("/login", response_class=HTMLResponse, tags=["users"])
async def login_page() -> str:
    """Login page."""
    return get_login_page()


@app.get("/register", response_class=HTMLResponse, tags=["users"])
async def register_page() -> str:
    """Registration page."""
    return get_register_page()


@app.post("/api/register", tags=["users"])
async def register_user(user_data: UserCreate, db: MongoDB = Depends(get_db)) -> dict:
    """
    Register a new user (creates pending user and sends confirmation email).

    User must confirm their email within 24 hours to activate the account.
    """
    from pymongo.errors import DuplicateKeyError
    from .user_auth import get_password_hash
    from .email_tokens import generate_confirmation_token, calculate_expiration_time
    from .email_service import get_email_service

    # Check if registration is enabled
    if not settings.registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled. Please contact the administrator."
        )

    try:
        # Check if user already exists (active)
        existing_user = await db.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Hash the password
        hashed_password = get_password_hash(user_data.password)

        # Generate confirmation token
        confirmation_token = generate_confirmation_token()
        expires_at = calculate_expiration_time(hours=24)

        # Create pending user in database
        pending_user_id = await db.create_pending_user(
            email=user_data.email,
            hashed_password=hashed_password,
            confirmation_token=confirmation_token,
            expires_at=expires_at,
            full_name=user_data.full_name
        )

        # Send confirmation email
        email_service = get_email_service()
        email_sent = email_service.send_confirmation_email(
            recipient_email=user_data.email,
            confirmation_token=confirmation_token
        )

        if not email_sent:
            # If email fails, delete pending user
            await db.delete_pending_user(confirmation_token)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send confirmation email. Please try again later."
            )

        return {
            "message": "Registration successful! Please check your email to confirm your account.",
            "detail": "You must confirm your email address before you can log in. Check your inbox for a confirmation link.",
            "email": user_data.email,
            "expires_in_hours": 24,
            "next_step": "Check your email and click the confirmation link to activate your account"
        }

    except DuplicateKeyError as e:
        if "email" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered (pending or active)"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@app.post("/api/login", response_model=Token, tags=["users"])
async def login_user(user_login: UserLogin, db: MongoDB = Depends(get_db)) -> Token:
    """Login and get access token."""
    from .user_auth import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
    from datetime import timedelta

    # Get user from database by email
    user = await db.get_user_by_email(user_login.email)

    if not user or not verify_password(user_login.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )

    # Create access token with email as subject
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )

    return Token(access_token=access_token)


@app.get("/api/check-confirmation-status", tags=["users"])
async def check_confirmation_status(email: str, db: MongoDB = Depends(get_db)) -> dict:
    """
    Check if a user's email has been confirmed.

    This endpoint is used by the awaiting-confirmation page to poll for confirmation status.

    Args:
        email: The email address to check

    Returns:
        Dictionary with confirmation status
    """
    # Check if user exists in the users collection (confirmed)
    user = await db.get_user_by_email(email)
    if user:
        return {
            "confirmed": True,
            "message": "Email confirmed! You can now log in."
        }

    # Check if user exists in pending_users collection (still waiting)
    if db.pending_users_collection is not None:
        pending = await db.pending_users_collection.find_one({"email": email})
        if pending:
            return {
                "confirmed": False,
                "message": "Awaiting email confirmation. Please check your inbox."
            }

    # Email not found in either collection
    return {
        "confirmed": False,
        "message": "Email not found. Please register first.",
        "not_found": True
    }


@app.get("/awaiting-confirmation", response_class=HTMLResponse, tags=["pages"])
async def awaiting_confirmation_page(email: str = "") -> str:
    """Display the awaiting email confirmation page."""
    return get_awaiting_confirmation_page(email)


@app.get("/api/confirm-email", tags=["users"], response_class=HTMLResponse)
async def confirm_email(token: str, db: MongoDB = Depends(get_db)):
    """
    Confirm user email and activate account.

    Args:
        token: Email confirmation token from the confirmation link

    Returns:
        HTML page with confirmation result
    """
    from .email_tokens import is_token_expired

    def render_confirmation_page(success: bool, title: str, message: str):
        """Render a styled confirmation result page."""
        icon = "✓" if success else "✗"
        icon_color = "#28a745" if success else "#dc3545"
        button_text = "Login to Your Account" if success else "Register Again"
        button_link = "/login" if success else "/register"

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title} - PutPlace</title>
            <link rel="icon" type="image/svg+xml" href="/static/images/favicon.svg">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    max-width: 500px;
                    width: 100%;
                    background: white;
                    border-radius: 10px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    overflow: hidden;
                    text-align: center;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                }}
                .header h1 {{
                    font-size: 1.8em;
                    margin-bottom: 5px;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .icon {{
                    font-size: 4em;
                    color: {icon_color};
                    margin-bottom: 20px;
                }}
                .message {{
                    font-size: 1.1em;
                    color: #555;
                    margin-bottom: 30px;
                }}
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-weight: bold;
                    transition: transform 0.2s, box-shadow 0.2s;
                }}
                .button:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                }}
                .footer {{
                    padding: 20px;
                    background: #f8f9fa;
                    font-size: 0.9em;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>PutPlace</h1>
                </div>
                <div class="content">
                    <div class="icon">{icon}</div>
                    <h2 style="margin-bottom: 15px;">{title}</h2>
                    <p class="message">{message}</p>
                    <a href="{button_link}" class="button">{button_text}</a>
                </div>
                <div class="footer">
                    <p>Need help? Contact support@putplace.org</p>
                </div>
            </div>
        </body>
        </html>
        """

    # Get pending user by token
    pending_user = await db.get_pending_user_by_token(token)

    if not pending_user:
        return HTMLResponse(
            content=render_confirmation_page(
                success=False,
                title="Invalid Link",
                message="This confirmation link is invalid or has already been used. If you haven't confirmed your account yet, please register again."
            ),
            status_code=404
        )

    # Check if token is expired
    if is_token_expired(pending_user["expires_at"]):
        # Delete expired pending user
        await db.delete_pending_user(token)
        return HTMLResponse(
            content=render_confirmation_page(
                success=False,
                title="Link Expired",
                message="This confirmation link has expired. Confirmation links are valid for 24 hours. Please register again to receive a new confirmation email."
            ),
            status_code=400
        )

    # Create actual user account
    from pymongo.errors import DuplicateKeyError

    try:
        user_id = await db.create_user(
            email=pending_user["email"],
            hashed_password=pending_user["hashed_password"],
            full_name=pending_user.get("full_name")
        )

        # Delete pending user after successful creation
        await db.delete_pending_user(token)

        return HTMLResponse(
            content=render_confirmation_page(
                success=True,
                title="Email Confirmed!",
                message=f"Welcome! Your email has been confirmed and your account is now active. You can now log in to start using PutPlace."
            )
        )

    except DuplicateKeyError:
        # User already exists - this can happen if the link was clicked twice
        # or if they registered again. Delete pending user and let them log in.
        await db.delete_pending_user(token)
        return HTMLResponse(
            content=render_confirmation_page(
                success=True,
                title="Account Already Active",
                message="Your account is already active! You can log in using your email and password."
            )
        )

    except Exception as e:
        # Log error and return generic message
        logger.error(f"Error creating user from pending: {e}")
        return HTMLResponse(
            content=render_confirmation_page(
                success=False,
                title="Activation Failed",
                message="We encountered an error while activating your account. Please try again or contact support if the problem persists."
            ),
            status_code=500
        )


@app.post("/api/auth/google", response_model=Token, tags=["users"])
async def google_oauth_login(
    oauth_data: GoogleOAuthLogin,
    db: MongoDB = Depends(get_db)
) -> Token:
    """Login or register using Google OAuth.

    The client sends a Google ID token obtained from Google Sign-In.
    We verify the token and either:
    1. Login existing user (if email matches)
    2. Create new user (if email is new)
    """
    from google.oauth2 import id_token
    from google.auth.transport import requests
    from .user_auth import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
    from datetime import timedelta, datetime
    import secrets

    # Verify the Google ID token
    try:
        if not settings.google_client_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth not configured on server"
            )

        # Verify token with Google
        idinfo = id_token.verify_oauth2_token(
            oauth_data.id_token,
            requests.Request(),
            settings.google_client_id
        )

        # Extract user info from token
        google_user_id = idinfo['sub']
        email = idinfo['email']
        email_verified = idinfo.get('email_verified', False)
        name = idinfo.get('name', '')
        picture = idinfo.get('picture', '')

        if not email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not verified by Google"
            )

    except ValueError as e:
        # Invalid token
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google ID token: {str(e)}"
        )

    # Check if user exists (by email or oauth_id)
    existing_user = await db.get_user_by_email(email)

    if existing_user:
        # User exists - update OAuth info if needed
        if existing_user.get("auth_provider") != "google":
            # Update user to use Google OAuth
            await db.users_collection.update_one(
                {"email": email},
                {
                    "$set": {
                        "auth_provider": "google",
                        "oauth_id": google_user_id,
                        "picture": picture
                    }
                }
            )
    else:
        # Create new user with Google OAuth
        user_doc = {
            "email": email,
            "full_name": name,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "auth_provider": "google",
            "oauth_id": google_user_id,
            "picture": picture,
            # No password hash for OAuth users
        }

        try:
            await db.users_collection.insert_one(user_doc)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create user: {str(e)}"
            )

    # Create access token with email as subject
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": email}, expires_delta=access_token_expires
    )

    return Token(access_token=access_token)


@app.get("/api/oauth/config", tags=["users"])
async def get_oauth_config() -> dict:
    """Get OAuth configuration for client.

    Returns only non-sensitive configuration like client IDs.
    Client secrets are never exposed to the frontend.
    """
    return {
        "google_client_id": settings.google_client_id,
        "google_enabled": bool(settings.google_client_id)
    }


@app.get("/api/my_files", response_model=list[FileMetadataResponse], tags=["files"])
async def get_my_files(
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = 100,
    skip: int = 0,
) -> list[FileMetadataResponse]:
    """Get all files uploaded by the current user.

    Requires user authentication via JWT Bearer token.

    Args:
        db: Database instance (injected)
        current_user: Current logged-in user (injected, for authentication)
        limit: Maximum number of files to return (default 100)
        skip: Number of files to skip for pagination (default 0)

    Returns:
        List of file metadata uploaded by the current user

    Raises:
        HTTPException: If database operation fails or authentication fails
    """
    try:
        # Get files uploaded by this user
        files = await db.get_files_by_user(
            user_id=str(current_user["_id"]),
            limit=limit,
            skip=skip
        )

        return [FileMetadataResponse(**file) for file in files]

    except Exception as e:
        logger.error(f"Error getting user files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user files: {str(e)}",
        ) from e


@app.get("/api/clones/{sha256}", response_model=list[FileMetadataResponse], tags=["files"])
async def get_clones(
    sha256: str,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[FileMetadataResponse]:
    """Get all files with the same SHA256 hash (clones) across all users.

    This endpoint returns ALL files with the same SHA256, including the epoch file
    (the first one uploaded with content) even if it was uploaded by a different user.

    Requires user authentication via JWT Bearer token.

    Args:
        sha256: SHA256 hash to search for
        db: Database instance (injected)
        current_user: Current logged-in user (injected, for authentication)

    Returns:
        List of all file metadata with matching SHA256, sorted with epoch file first

    Raises:
        HTTPException: If validation fails or database operation fails
    """
    if len(sha256) != 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SHA256 hash must be exactly 64 characters",
        )

    try:
        # Get all files with this SHA256 across all users
        files = await db.get_files_by_sha256(sha256)

        return [FileMetadataResponse(**file) for file in files]

    except Exception as e:
        logger.error(f"Error getting clones for SHA256 {sha256}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get clones: {str(e)}",
        ) from e


@app.get("/my_files", response_class=HTMLResponse, tags=["users"])
async def my_files_page() -> str:
    """My Files page - shows files uploaded by the current user in a file system tree."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>My Files - PutPlace</title>
        <link rel="icon" type="image/svg+xml" href="/static/images/favicon.svg">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .header h1 {
                font-size: 2rem;
            }
            .header-buttons {
                display: flex;
                gap: 10px;
            }
            .logout-btn {
                padding: 8px 16px;
                background: rgba(255, 255, 255, 0.2);
                color: white;
                border: 2px solid white;
                border-radius: 5px;
                cursor: pointer;
                font-weight: 500;
                text-decoration: none;
                transition: all 0.3s ease;
            }
            .logout-btn:hover {
                background: white;
                color: #667eea;
            }
            .content {
                padding: 40px;
            }
            .message {
                padding: 12px;
                border-radius: 5px;
                margin-bottom: 20px;
                display: none;
            }
            .message.error {
                background: #fee;
                color: #c33;
                border: 1px solid #fcc;
            }
            .message.success {
                background: #efe;
                color: #3c3;
                border: 1px solid #cfc;
            }
            .section {
                margin-bottom: 30px;
            }
            .section h2 {
                color: #667eea;
                margin-bottom: 15px;
                font-size: 1.5rem;
                border-bottom: 2px solid #667eea;
                padding-bottom: 5px;
            }
            .no-files {
                text-align: center;
                padding: 40px;
                color: #6c757d;
            }
            .no-files h3 {
                color: #495057;
                margin-bottom: 10px;
                font-size: 1.3rem;
            }
            .no-files p {
                margin-bottom: 20px;
            }
            .install-info {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 20px 30px;
                text-align: left;
                display: inline-block;
                margin-top: 10px;
                border: 1px solid #dee2e6;
            }
            .install-info h4 {
                color: #667eea;
                font-size: 0.95rem;
                margin: 15px 0 8px 0;
            }
            .install-info h4:first-child {
                margin-top: 0;
            }
            .install-info pre {
                background: #2d2d2d;
                color: #f8f8f2;
                padding: 12px 16px;
                border-radius: 5px;
                font-family: 'Courier New', monospace;
                font-size: 0.9rem;
                overflow-x: auto;
            }
            .install-info .hint {
                margin-top: 15px;
                font-size: 0.9rem;
                color: #6c757d;
            }
            .install-info .hint a {
                color: #667eea;
                text-decoration: none;
            }
            .install-info .hint a:hover {
                text-decoration: underline;
            }
            .back-link {
                display: inline-block;
                margin-top: 20px;
                color: #667eea;
                text-decoration: none;
            }
            .back-link:hover {
                color: #764ba2;
            }

            /* File tree styles */
            .file-tree {
                font-family: 'Courier New', monospace;
                font-size: 0.9rem;
            }
            .tree-host {
                margin-bottom: 25px;
                background: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
                border-left: 4px solid #667eea;
            }
            .tree-host-header {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 8px;
                background: white;
                border-radius: 5px;
                margin-bottom: 10px;
                cursor: pointer;
                transition: background 0.2s;
            }
            .tree-host-header:hover {
                background: #e9ecef;
            }
            .tree-host-icon {
                font-size: 1.2rem;
                transition: transform 0.2s;
            }
            .tree-host-icon.collapsed {
                transform: rotate(-90deg);
            }
            .tree-host-name {
                font-weight: 600;
                color: #667eea;
                font-size: 1rem;
            }
            .tree-host-count {
                margin-left: auto;
                background: #667eea;
                color: white;
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.85rem;
            }
            .tree-host-content {
                padding-left: 20px;
            }
            .tree-host-content.collapsed {
                display: none;
            }
            .tree-folder {
                margin: 8px 0;
                padding-left: 15px;
            }
            .tree-folder-header {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 6px 8px;
                background: white;
                border-radius: 4px;
                cursor: pointer;
                transition: background 0.2s;
            }
            .tree-folder-header:hover {
                background: #fff3cd;
            }
            .tree-folder-icon {
                font-size: 1rem;
                transition: transform 0.2s;
            }
            .tree-folder-icon.collapsed {
                transform: rotate(-90deg);
            }
            .tree-folder-name {
                font-weight: 500;
                color: #495057;
            }
            .tree-folder-count {
                margin-left: auto;
                color: #6c757d;
                font-size: 0.85rem;
            }
            .tree-folder-content {
                padding-left: 20px;
                margin-top: 5px;
            }
            .tree-folder-content.collapsed {
                display: none;
            }
            .tree-file {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 8px;
                margin: 4px 0;
                background: white;
                border-radius: 4px;
                transition: all 0.2s;
            }
            .tree-file:hover {
                background: #e7f3ff;
                transform: translateX(5px);
            }
            .file-icon {
                font-size: 1rem;
            }
            .file-name {
                flex: 1;
                color: #333;
            }
            .file-size {
                color: #6c757d;
                font-size: 0.85rem;
                min-width: 80px;
                text-align: right;
            }
            .file-status {
                font-size: 0.75rem;
                padding: 2px 8px;
                border-radius: 10px;
                font-weight: 500;
            }
            .file-status.uploaded {
                background: #d4edda;
                color: #155724;
            }
            .file-status.metadata {
                background: #fff3cd;
                color: #856404;
            }
            .action-btn {
                border: none;
                padding: 3px 8px;
                border-radius: 3px;
                cursor: pointer;
                font-size: 0.75rem;
                transition: all 0.2s;
                font-weight: 500;
            }
            .info-btn {
                background: #667eea;
                color: white;
            }
            .info-btn:hover {
                background: #764ba2;
                transform: scale(1.05);
            }
            .clone-btn {
                background: #28a745;
                color: white;
            }
            .clone-btn:hover:not(.disabled) {
                background: #218838;
                transform: scale(1.05);
            }
            .clone-btn.disabled {
                background: #ccc;
                color: #666;
                cursor: not-allowed;
                opacity: 0.6;
            }

            /* Modal styles */
            .modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                overflow: auto;
                background-color: rgba(0, 0, 0, 0.5);
                animation: fadeIn 0.3s;
            }
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            .modal-content {
                background-color: white;
                margin: 5% auto;
                padding: 0;
                border-radius: 10px;
                width: 90%;
                max-width: 1200px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                animation: slideIn 0.3s;
                max-height: 85vh;
                display: flex;
                flex-direction: column;
            }
            @keyframes slideIn {
                from {
                    transform: translateY(-50px);
                    opacity: 0;
                }
                to {
                    transform: translateY(0);
                    opacity: 1;
                }
            }
            .modal-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px 30px;
                border-radius: 10px 10px 0 0;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .modal-header h3 {
                font-size: 1.3rem;
                font-weight: 600;
            }
            .modal-close {
                color: white;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
                background: none;
                border: none;
                padding: 0;
                line-height: 1;
                transition: transform 0.2s;
            }
            .modal-close:hover {
                transform: scale(1.2);
            }
            .modal-body {
                padding: 30px;
                overflow-y: auto;
                overflow-x: auto;
                flex: 1;
            }
            .modal-body table {
                table-layout: fixed;
                width: 100%;
            }
            .modal-body table th:nth-child(1) {
                width: 15%;
            }
            .modal-body table th:nth-child(2) {
                width: 55%;
            }
            .modal-body table th:nth-child(3) {
                width: 12%;
            }
            .modal-body table th:nth-child(4) {
                width: 18%;
            }
            .modal-body table td {
                word-wrap: break-word;
                word-break: break-all;
                overflow-wrap: break-word;
            }
            .detail-grid {
                display: grid;
                grid-template-columns: 1fr 2fr;
                gap: 15px;
                margin-bottom: 15px;
            }
            .detail-label {
                font-weight: 600;
                color: #667eea;
            }
            .detail-value {
                word-break: break-all;
                font-family: 'Courier New', monospace;
                font-size: 0.9rem;
                background: #f8f9fa;
                padding: 5px 10px;
                border-radius: 4px;
            }
            .detail-value.normal {
                font-family: inherit;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📁 My Files</h1>
                <div class="header-buttons">
                    <a href="/api_keys_page" class="logout-btn">🔑 API Keys</a>
                    <a href="/" class="logout-btn">← Home</a>
                    <button onclick="logout()" class="logout-btn">Logout</button>
                </div>
            </div>

            <div class="content">
                <div id="message" class="message"></div>

                <div class="section">
                    <h2>File System</h2>
                    <div id="filesContainer">
                        <p class="no-files">Loading...</p>
                    </div>
                </div>

                <a href="/" class="back-link">← Back to Home</a>
            </div>
        </div>

        <!-- Modal for file details -->
        <div id="fileModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>📄 File Details</h3>
                    <button class="modal-close" onclick="closeModal()">&times;</button>
                </div>
                <div class="modal-body" id="modalBody">
                    <!-- File details will be inserted here -->
                </div>
            </div>
        </div>

        <!-- Modal for clones -->
        <div id="clonesModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>👥 File Clones (Identical SHA256)</h3>
                    <button class="modal-close" onclick="closeClonesModal()">&times;</button>
                </div>
                <div class="modal-body" id="clonesModalBody">
                    <!-- Clone list will be inserted here -->
                </div>
            </div>
        </div>

        <script>
            let currentToken = null;
            let allFiles = [];

            // Check if user is logged in
            function checkAuth() {
                currentToken = localStorage.getItem('access_token');
                if (!currentToken) {
                    window.location.href = '/login';
                    return false;
                }
                return true;
            }

            // Logout function
            function logout() {
                localStorage.removeItem('access_token');
                window.location.href = '/';
            }

            // Load user files
            async function loadFiles() {
                if (!checkAuth()) return;

                try {
                    const response = await fetch('/api/my_files', {
                        headers: {
                            'Authorization': `Bearer ${currentToken}`
                        }
                    });

                    if (response.status === 401) {
                        logout();
                        return;
                    }

                    if (!response.ok) {
                        throw new Error('Failed to load files');
                    }

                    allFiles = await response.json();
                    buildFileTree(allFiles);
                } catch (error) {
                    showMessage('Error loading files: ' + error.message, 'error');
                }
            }

            // Build file system tree structure
            function buildFileTree(files) {
                const container = document.getElementById('filesContainer');

                if (files.length === 0) {
                    container.innerHTML = `
                        <div class="no-files">
                            <h3>No files uploaded yet</h3>
                            <p>Use the desktop app or command-line tool to scan directories and upload file metadata.</p>
                            <div class="install-info">
                                <h4>Desktop App (Recommended)</h4>
                                <p style="margin: 8px 0;">Download the PutPlace Client for macOS, Windows, or Linux:</p>
                                <p><a href="https://putplace.org/downloads.html" style="color: #667eea; font-weight: 600;">Download Desktop App</a></p>
                                <h4>Command Line (Python)</h4>
                                <pre>pip install putplace-client</pre>
                                <h4>Usage</h4>
                                <pre>ppclient /path/to/scan --email you@example.com --password yourpass</pre>
                                <p class="hint">Or use an API key from the <a href="/api_keys_page">My API Keys</a> page.</p>
                            </div>
                        </div>
                    `;
                    return;
                }

                // Create SHA256 map to count clones (files with same hash)
                const sha256Map = {};
                files.forEach(file => {
                    sha256Map[file.sha256] = (sha256Map[file.sha256] || 0) + 1;
                });

                // Organize files by hostname and path
                const tree = {};
                files.forEach(file => {
                    if (!tree[file.hostname]) {
                        tree[file.hostname] = {};
                    }

                    // Parse filepath into directory structure
                    const parts = file.filepath.split('/');
                    const filename = parts.pop();
                    const dirPath = parts.join('/') || '/';

                    if (!tree[file.hostname][dirPath]) {
                        tree[file.hostname][dirPath] = [];
                    }
                    tree[file.hostname][dirPath].push({ ...file, filename });
                });

                // Build HTML
                let html = '<div class="file-tree">';

                Object.keys(tree).sort().forEach(hostname => {
                    const hostFiles = Object.values(tree[hostname]).flat();
                    html += `
                        <div class="tree-host">
                            <div class="tree-host-header" onclick="toggleHost(this)">
                                <span class="tree-host-icon">🔽</span>
                                <span class="tree-host-name">🖥️ ${escapeHtml(hostname)}</span>
                                <span class="tree-host-count">${hostFiles.length} files</span>
                            </div>
                            <div class="tree-host-content">
                    `;

                    Object.keys(tree[hostname]).sort().forEach(dirPath => {
                        const files = tree[hostname][dirPath];
                        html += `
                            <div class="tree-folder">
                                <div class="tree-folder-header" onclick="toggleFolder(this)">
                                    <span class="tree-folder-icon">🔽</span>
                                    <span class="tree-folder-name">📁 ${escapeHtml(dirPath)}</span>
                                    <span class="tree-folder-count">${files.length}</span>
                                </div>
                                <div class="tree-folder-content">
                        `;

                        files.forEach(file => {
                            const status = file.has_file_content ? 'uploaded' : 'metadata';
                            const statusText = file.has_file_content ? 'Full' : 'Meta';
                            const cloneCount = sha256Map[file.sha256] || 0;
                            const isZeroLength = file.file_size === 0;

                            // For zero-length files, show a special icon and non-clickable "0" for clones
                            const fileIcon = isZeroLength ? '📭' : '📄';

                            // Clone button logic:
                            // - Zero-length files: always show "0" disabled
                            // - Metadata-only files: always clickable (must have epoch file somewhere)
                            // - Files with content: always clickable (may have clones from other users)
                            const cloneButton = isZeroLength
                                ? '<span class="action-btn clone-btn disabled" style="cursor: default;">0</span>'
                                : `<button class="action-btn clone-btn" onclick="showClones('${file.sha256}')">${cloneCount > 1 ? cloneCount : '👥'}</button>`;

                            html += `
                                <div class="tree-file">
                                    <span class="file-icon">${fileIcon}</span>
                                    <span class="file-name">${escapeHtml(file.filename)}</span>
                                    <span class="file-size">${formatFileSize(file.file_size)}</span>
                                    <span class="file-status ${status}">${statusText}</span>
                                    <button class="action-btn info-btn" onclick='showFileDetails(${JSON.stringify(file)})'>ℹ️</button>
                                    ${cloneButton}
                                </div>
                            `;
                        });

                        html += `
                                </div>
                            </div>
                        `;
                    });

                    html += `
                            </div>
                        </div>
                    `;
                });

                html += '</div>';
                container.innerHTML = html;
            }

            // Toggle host visibility
            function toggleHost(element) {
                const content = element.nextElementSibling;
                const icon = element.querySelector('.tree-host-icon');
                content.classList.toggle('collapsed');
                icon.classList.toggle('collapsed');
            }

            // Toggle folder visibility
            function toggleFolder(element) {
                const content = element.nextElementSibling;
                const icon = element.querySelector('.tree-folder-icon');
                content.classList.toggle('collapsed');
                icon.classList.toggle('collapsed');
            }

            // Show file details in modal
            function showFileDetails(file) {
                const modal = document.getElementById('fileModal');
                const modalBody = document.getElementById('modalBody');

                const uploadedDate = file.created_at ? new Date(file.created_at).toLocaleString() : 'N/A';
                const fileUploadedDate = file.file_uploaded_at ? new Date(file.file_uploaded_at).toLocaleString() : 'N/A';

                modalBody.innerHTML = `
                    <div class="detail-grid">
                        <div class="detail-label">Filepath:</div>
                        <div class="detail-value">${escapeHtml(file.filepath)}</div>

                        <div class="detail-label">Hostname:</div>
                        <div class="detail-value normal">${escapeHtml(file.hostname)}</div>

                        <div class="detail-label">IP Address:</div>
                        <div class="detail-value normal">${escapeHtml(file.ip_address)}</div>

                        <div class="detail-label">SHA256:</div>
                        <div class="detail-value">${escapeHtml(file.sha256)}</div>

                        <div class="detail-label">File Size:</div>
                        <div class="detail-value normal">${formatFileSize(file.file_size)} (${file.file_size.toLocaleString()} bytes)</div>

                        <div class="detail-label">Permissions:</div>
                        <div class="detail-value normal">${formatPermissions(file.file_mode)}</div>

                        <div class="detail-label">Owner:</div>
                        <div class="detail-value normal">UID: ${file.file_uid} / GID: ${file.file_gid}</div>

                        <div class="detail-label">Modified Time:</div>
                        <div class="detail-value normal">${new Date(file.file_mtime * 1000).toLocaleString()}</div>

                        <div class="detail-label">Access Time:</div>
                        <div class="detail-value normal">${new Date(file.file_atime * 1000).toLocaleString()}</div>

                        <div class="detail-label">Change Time:</div>
                        <div class="detail-value normal">${new Date(file.file_ctime * 1000).toLocaleString()}</div>

                        <div class="detail-label">Metadata Created:</div>
                        <div class="detail-value normal">${uploadedDate}</div>

                        <div class="detail-label">File Content:</div>
                        <div class="detail-value normal">${file.has_file_content ? `✅ Uploaded at ${fileUploadedDate}` : '❌ Not uploaded'}</div>
                    </div>
                `;

                modal.style.display = 'block';
            }

            // Close modal
            function closeModal() {
                document.getElementById('fileModal').style.display = 'none';
            }

            // Close clones modal
            function closeClonesModal() {
                document.getElementById('clonesModal').style.display = 'none';
            }

            // Show clones for a given SHA256
            async function showClones(sha256) {
                const modal = document.getElementById('clonesModal');
                const modalBody = document.getElementById('clonesModalBody');

                // Show loading message
                modalBody.innerHTML = '<p style="text-align: center; color: #667eea;">Loading clones...</p>';
                modal.style.display = 'block';

                try {
                    // Fetch all clones across all users from the server
                    const response = await fetch(`/api/clones/${sha256}`, {
                        headers: {
                            'Authorization': `Bearer ${currentToken}`
                        }
                    });

                    if (!response.ok) {
                        throw new Error(`Failed to load clones: ${response.statusText}`);
                    }

                    const clones = await response.json();

                    // Sort clones: epoch file (first uploaded) first, then others
                    // (Backend already sorts, but we keep this for safety)
                    clones.sort((a, b) => {
                        // Files with content come before files without content
                        if (a.has_file_content && !b.has_file_content) return -1;
                        if (!a.has_file_content && b.has_file_content) return 1;

                        // Among files with content, sort by upload time (earliest first - epoch file)
                        if (a.has_file_content && b.has_file_content) {
                            const timeA = a.file_uploaded_at ? new Date(a.file_uploaded_at).getTime() : 0;
                            const timeB = b.file_uploaded_at ? new Date(b.file_uploaded_at).getTime() : 0;
                            return timeA - timeB;
                        }

                        // Among files without content, sort by metadata creation time
                        const createdA = a.created_at ? new Date(a.created_at).getTime() : 0;
                        const createdB = b.created_at ? new Date(b.created_at).getTime() : 0;
                        return createdA - createdB;
                    });

                    if (clones.length === 0) {
                        modalBody.innerHTML = '<p>No clone files found.</p>';
                    } else {
                        let html = `
                            <p style="margin-bottom: 15px; color: #667eea; font-weight: 500;">
                                Found ${clones.length} file(s) with identical SHA256: <code style="background: #f8f9fa; padding: 2px 6px; border-radius: 3px;">${sha256.substring(0, 16)}...</code>
                            </p>
                            <table style="width: 100%; border-collapse: collapse;">
                                <thead>
                                    <tr style="background: #f8f9fa; border-bottom: 2px solid #667eea;">
                                        <th style="padding: 10px; text-align: left; font-weight: 600; color: #667eea;">Hostname</th>
                                        <th style="padding: 10px; text-align: left; font-weight: 600; color: #667eea;">File Path</th>
                                        <th style="padding: 10px; text-align: left; font-weight: 600; color: #667eea;">Size</th>
                                        <th style="padding: 10px; text-align: center; font-weight: 600; color: #667eea;">Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                        `;

                        clones.forEach((file, index) => {
                            const status = file.has_file_content ? 'uploaded' : 'metadata';
                            const statusText = file.has_file_content ? '✅ Full' : '📝 Meta';
                            // Highlight the epoch file (first row with content)
                            const isEpoch = index === 0 && file.has_file_content;
                            const rowBg = isEpoch ? '#d4edda' : (index % 2 === 0 ? '#ffffff' : '#f8f9fa');
                            const rowBorder = isEpoch ? 'border-left: 4px solid #28a745; border-bottom: 2px solid #28a745;' : 'border-bottom: 1px solid #e0e0e0;';
                            const epochBadge = isEpoch ? '<span style="background: #28a745; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-left: 8px; font-weight: 600;">EPOCH</span>' : '';
                            const fontWeight = isEpoch ? '600' : '500';
                            html += `
                                <tr style="background: ${rowBg}; ${rowBorder}">
                                    <td style="padding: 10px; font-weight: ${fontWeight};">${escapeHtml(file.hostname)}${epochBadge}</td>
                                    <td style="padding: 10px; font-family: 'Courier New', monospace; font-size: 0.85rem; font-weight: ${isEpoch ? '500' : 'normal'};">${escapeHtml(file.filepath)}</td>
                                    <td style="padding: 10px; font-weight: ${isEpoch ? '500' : 'normal'};">${formatFileSize(file.file_size)}</td>
                                    <td style="padding: 10px; text-align: center; font-weight: ${isEpoch ? '500' : 'normal'};">${statusText}</td>
                                </tr>
                            `;
                        });

                        html += `
                                </tbody>
                            </table>
                        `;
                        modalBody.innerHTML = html;
                    }
                } catch (error) {
                    console.error('Error loading clones:', error);
                    modalBody.innerHTML = `<p style="color: #dc3545;">Error loading clones: ${error.message}</p>`;
                }
            }

            // Close modal when clicking outside
            window.onclick = function(event) {
                const fileModal = document.getElementById('fileModal');
                const clonesModal = document.getElementById('clonesModal');
                if (event.target == fileModal) {
                    fileModal.style.display = 'none';
                }
                if (event.target == clonesModal) {
                    clonesModal.style.display = 'none';
                }
            }

            // Format file size
            function formatFileSize(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
            }

            // Format file permissions
            function formatPermissions(mode) {
                const perms = [];
                const types = ['---', '--x', '-w-', '-wx', 'r--', 'r-x', 'rw-', 'rwx'];
                perms.push(types[(mode >> 6) & 7]);
                perms.push(types[(mode >> 3) & 7]);
                perms.push(types[mode & 7]);
                return perms.join('') + ` (${mode.toString(8)})`;
            }

            // Escape HTML to prevent XSS
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            // Show message
            function showMessage(text, type) {
                const messageDiv = document.getElementById('message');
                messageDiv.textContent = text;
                messageDiv.className = 'message ' + type;
                messageDiv.style.display = 'block';

                setTimeout(() => {
                    messageDiv.style.display = 'none';
                }, 5000);
            }

            // Initialize
            if (checkAuth()) {
                loadFiles();
            }
        </script>
    </body>
    </html>
    """
    return html_content


@app.get("/admin/dashboard", response_class=HTMLResponse, tags=["admin"])
async def admin_dashboard(
    db: MongoDB = Depends(get_db),
    admin_user: dict = Depends(get_current_admin_user),
) -> str:
    """Admin dashboard showing all users and their statistics.

    Requires admin privileges to access.

    Args:
        db: Database instance (injected)
        admin_user: Current admin user (injected)

    Returns:
        HTML dashboard page
    """
    # Get dashboard data
    stats = await db.get_dashboard_stats()
    users = await db.get_all_users()
    pending_users = await db.get_all_pending_users()
    file_counts = await db.get_user_file_counts()

    # Build users table rows
    users_rows = ""
    for user in users:
        user_id = user.get("_id", "")
        email = user.get("email", "")
        full_name = user.get("full_name", "") or ""
        is_active = "Active" if user.get("is_active", False) else "Inactive"
        is_admin = "Yes" if user.get("is_admin", False) else "No"
        created_at = user.get("created_at", "")
        if created_at:
            created_at = created_at.strftime("%Y-%m-%d %H:%M") if hasattr(created_at, 'strftime') else str(created_at)
        file_count = file_counts.get(user_id, 0)

        users_rows += f"""
            <tr>
                <td>{email}</td>
                <td>{full_name}</td>
                <td><span class="status-badge {'status-active' if user.get('is_active') else 'status-inactive'}">{is_active}</span></td>
                <td>{is_admin}</td>
                <td>{file_count}</td>
                <td>{created_at}</td>
            </tr>
        """

    # Build pending users table rows
    pending_rows = ""
    for pending in pending_users:
        email = pending.get("email", "")
        full_name = pending.get("full_name", "") or ""
        created_at = pending.get("created_at", "")
        expires_at = pending.get("expires_at", "")
        if created_at:
            created_at = created_at.strftime("%Y-%m-%d %H:%M") if hasattr(created_at, 'strftime') else str(created_at)
        if expires_at:
            expires_at = expires_at.strftime("%Y-%m-%d %H:%M") if hasattr(expires_at, 'strftime') else str(expires_at)

        pending_rows += f"""
            <tr>
                <td>{email}</td>
                <td>{full_name}</td>
                <td>{created_at}</td>
                <td>{expires_at}</td>
            </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Admin Dashboard - PutPlace</title>
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                min-height: 100vh;
                color: #e0e0e0;
                padding: 20px;
            }}

            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 1px solid #333;
            }}

            .header h1 {{
                color: #fff;
                font-size: 2rem;
            }}

            .header-info {{
                text-align: right;
                color: #888;
            }}

            .back-link {{
                color: #4da6ff;
                text-decoration: none;
                margin-top: 10px;
                display: inline-block;
            }}

            .back-link:hover {{
                text-decoration: underline;
            }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 20px;
                margin-bottom: 40px;
            }}

            .stat-card {{
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 24px;
                text-align: center;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}

            .stat-value {{
                font-size: 2.5rem;
                font-weight: 700;
                color: #4da6ff;
                margin-bottom: 8px;
            }}

            .stat-label {{
                font-size: 0.9rem;
                color: #888;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}

            .section {{
                margin-bottom: 40px;
            }}

            .section h2 {{
                color: #fff;
                font-size: 1.5rem;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 2px solid #4da6ff;
            }}

            .table-container {{
                background: rgba(255, 255, 255, 0.03);
                border-radius: 12px;
                overflow: hidden;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
            }}

            th, td {{
                padding: 14px 16px;
                text-align: left;
            }}

            th {{
                background: rgba(77, 166, 255, 0.1);
                color: #4da6ff;
                font-weight: 600;
                text-transform: uppercase;
                font-size: 0.8rem;
                letter-spacing: 1px;
            }}

            tr:hover {{
                background: rgba(255, 255, 255, 0.05);
            }}

            tr:not(:last-child) td {{
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }}

            .status-badge {{
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 0.85rem;
                font-weight: 500;
            }}

            .status-active {{
                background: rgba(40, 167, 69, 0.2);
                color: #28a745;
            }}

            .status-inactive {{
                background: rgba(220, 53, 69, 0.2);
                color: #dc3545;
            }}

            .empty-message {{
                text-align: center;
                padding: 40px;
                color: #666;
            }}

            @media (max-width: 768px) {{
                .stats-grid {{
                    grid-template-columns: repeat(2, 1fr);
                }}

                .table-container {{
                    overflow-x: auto;
                }}

                table {{
                    min-width: 600px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <h1>Admin Dashboard</h1>
                <a href="/" class="back-link">&larr; Back to Home</a>
            </div>
            <div class="header-info">
                <div>Logged in as: {admin_user.get('email', 'Admin')}</div>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{stats.get('total_users', 0)}</div>
                <div class="stat-label">Total Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('active_users', 0)}</div>
                <div class="stat-label">Active Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('admin_users', 0)}</div>
                <div class="stat-label">Admins</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('pending_users', 0)}</div>
                <div class="stat-label">Pending Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('total_files', 0)}</div>
                <div class="stat-label">Total Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('files_with_content', 0)}</div>
                <div class="stat-label">Files with Content</div>
            </div>
        </div>

        <div class="section">
            <h2>Registered Users</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Email</th>
                            <th>Full Name</th>
                            <th>Status</th>
                            <th>Admin</th>
                            <th>Files Uploaded</th>
                            <th>Created At</th>
                        </tr>
                    </thead>
                    <tbody>
                        {users_rows if users_rows else '<tr><td colspan="6" class="empty-message">No registered users found</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="section">
            <h2>Pending Registrations</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Email</th>
                            <th>Full Name</th>
                            <th>Registered At</th>
                            <th>Expires At</th>
                        </tr>
                    </thead>
                    <tbody>
                        {pending_rows if pending_rows else '<tr><td colspan="4" class="empty-message">No pending registrations</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content
