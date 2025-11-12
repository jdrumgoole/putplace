"""FastAPI application for file metadata storage."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse
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

logger = logging.getLogger(__name__)

# Global storage backend instance
storage_backend: StorageBackend | None = None


async def ensure_admin_exists(db: MongoDB) -> None:
    """Ensure an admin user exists using multiple fallback methods.

    This function implements a hybrid approach:
    1. If users exist, do nothing
    2. If PUTPLACE_ADMIN_USERNAME and PUTPLACE_ADMIN_PASSWORD are set, use them
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
        admin_user = os.getenv("PUTPLACE_ADMIN_USERNAME")
        admin_pass = os.getenv("PUTPLACE_ADMIN_PASSWORD")
        admin_email = os.getenv("PUTPLACE_ADMIN_EMAIL", "admin@localhost")

        if admin_user and admin_pass:
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
                "username": admin_user,
                "email": admin_email,
                "hashed_password": hashed_password,
                "full_name": "Administrator",
                "is_active": True,
                "created_at": datetime.utcnow(),
            }

            await db.users_collection.insert_one(user_doc)
            logger.info(f"✅ Created admin user from environment: {admin_user}")
            return

        # Method 2: Generate random password (fallback for development)
        import secrets
        random_password = secrets.token_urlsafe(16)  # 16 bytes = ~21 chars

        from .user_auth import get_password_hash

        hashed_password = get_password_hash(random_password)
        user_doc = {
            "username": "admin",
            "email": "admin@localhost",
            "hashed_password": hashed_password,
            "full_name": "Administrator",
            "is_active": True,
            "created_at": datetime.utcnow(),
        }

        await db.users_collection.insert_one(user_doc)

        # Display credentials prominently in logs
        logger.warning("=" * 80)
        logger.warning("🔐 INITIAL ADMIN CREDENTIALS GENERATED")
        logger.warning("=" * 80)
        logger.warning(f"   Username: admin")
        logger.warning(f"   Password: {random_password}")
        logger.warning("")
        logger.warning("⚠️  SAVE THESE CREDENTIALS NOW - They won't be shown again!")
        logger.warning("")
        logger.warning("For production, set environment variables instead:")
        logger.warning("   PUTPLACE_ADMIN_USERNAME=your-admin")
        logger.warning("   PUTPLACE_ADMIN_PASSWORD=your-secure-password")
        logger.warning("   PUTPLACE_ADMIN_EMAIL=admin@example.com")
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
                f"Username: admin\n"
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

    # Decode token to get username
    username = decode_access_token(token)

    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user = await db.get_user_by_username(username)

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
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PutPlace - File Metadata Storage</title>
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
                max-width: 900px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }
            .header h1 {
                font-size: 2.5rem;
                margin-bottom: 10px;
            }
            .header p {
                font-size: 1.2rem;
                opacity: 0.9;
            }
            .content {
                padding: 40px;
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
            .card {
                background: #f8f9fa;
                border-left: 4px solid #667eea;
                padding: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }
            .card h3 {
                color: #667eea;
                margin-bottom: 8px;
            }
            .card code {
                background: #e9ecef;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
                font-size: 0.9rem;
            }
            .btn-group {
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                margin-top: 20px;
            }
            .btn {
                display: inline-block;
                padding: 12px 24px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                font-weight: 500;
                transition: all 0.3s ease;
            }
            .btn:hover {
                background: #764ba2;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .btn-secondary {
                background: #6c757d;
            }
            .btn-secondary:hover {
                background: #5a6268;
            }
            .endpoint-list {
                list-style: none;
            }
            .endpoint-list li {
                padding: 10px;
                margin-bottom: 8px;
                background: #f8f9fa;
                border-radius: 4px;
                display: flex;
                align-items: center;
            }
            .method {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 3px;
                font-weight: 600;
                font-size: 0.85rem;
                margin-right: 10px;
                min-width: 60px;
                text-align: center;
            }
            .method-get { background: #61affe; color: white; }
            .method-post { background: #49cc90; color: white; }
            .method-put { background: #fca130; color: white; }
            .method-delete { background: #f93e3e; color: white; }
            .status-badge {
                display: inline-block;
                padding: 5px 12px;
                background: #28a745;
                color: white;
                border-radius: 20px;
                font-size: 0.9rem;
                font-weight: 500;
            }
            pre {
                background: #2d2d2d;
                color: #f8f8f2;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
                font-size: 0.9rem;
            }
            .footer {
                background: #f8f9fa;
                padding: 20px 40px;
                text-align: center;
                color: #6c757d;
                border-top: 1px solid #dee2e6;
            }
            .auth-buttons {
                display: flex;
                gap: 10px;
                justify-content: center;
                margin-top: 20px;
            }
            .auth-btn {
                display: inline-block;
                padding: 10px 20px;
                background: rgba(255, 255, 255, 0.2);
                color: white;
                text-decoration: none;
                border-radius: 5px;
                font-weight: 500;
                transition: all 0.3s ease;
                border: 2px solid white;
            }
            .auth-btn:hover {
                background: white;
                color: #667eea;
                transform: translateY(-2px);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🗄️ PutPlace</h1>
                <p>File Metadata Storage Service</p>
                <div style="margin-top: 15px;">
                    <span class="status-badge">✓ Running</span>
                </div>
                <div class="auth-buttons" id="authButtons">
                    <a href="/login" class="auth-btn">🔐 Login</a>
                    <a href="/register" class="auth-btn">📝 Register</a>
                </div>
            </div>

            <div class="content">
                <div class="section">
                    <h2>Welcome</h2>
                    <p>PutPlace is a FastAPI-based service for storing and retrieving file metadata with MongoDB backend. Track file locations, SHA256 hashes, and metadata across your infrastructure.</p>
                </div>

                <div class="section">
                    <h2>Quick Start</h2>
                    <div class="btn-group">
                        <a href="/docs" class="btn">📖 Interactive API Docs (Swagger)</a>
                        <a href="/redoc" class="btn btn-secondary">📚 Alternative Docs (ReDoc)</a>
                        <a href="/health" class="btn btn-secondary">❤️ Health Check</a>
                    </div>
                </div>

                <div class="section">
                    <h2>API Endpoints</h2>
                    <ul class="endpoint-list">
                        <li>
                            <span class="method method-get">GET</span>
                            <code>/health</code> - Health check with database status
                        </li>
                        <li>
                            <span class="method method-post">POST</span>
                            <code>/put_file</code> - Store file metadata
                        </li>
                        <li>
                            <span class="method method-get">GET</span>
                            <code>/get_file/{sha256}</code> - Retrieve file by SHA256 hash
                        </li>
                        <li>
                            <span class="method method-post">POST</span>
                            <code>/upload_file/{sha256}</code> - Upload file content
                        </li>
                        <li>
                            <span class="method method-post">POST</span>
                            <code>/api_keys</code> - Create new API key
                        </li>
                        <li>
                            <span class="method method-get">GET</span>
                            <code>/api_keys</code> - List all API keys
                        </li>
                        <li>
                            <span class="method method-delete">DELETE</span>
                            <code>/api_keys/{key_id}</code> - Delete API key
                        </li>
                        <li>
                            <span class="method method-put">PUT</span>
                            <code>/api_keys/{key_id}/revoke</code> - Revoke API key
                        </li>
                    </ul>
                </div>

                <div class="section">
                    <h2>Example Usage</h2>
                    <div class="card">
                        <h3>Store File Metadata</h3>
                        <pre>curl -X POST http://localhost:8000/put_file \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: your-api-key" \\
  -d '{
    "filepath": "/var/log/app.log",
    "hostname": "server01",
    "ip_address": "192.168.1.100",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }'</pre>
                    </div>

                    <div class="card">
                        <h3>Retrieve File Metadata</h3>
                        <pre>curl -H "X-API-Key: your-api-key" \\
  http://localhost:8000/get_file/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855</pre>
                    </div>

                    <div class="card">
                        <h3>Using the Client Tool</h3>
                        <pre># Scan a directory and send metadata to server
ppclient /var/log --api-key your-api-key

# With exclude patterns
ppclient /home/user --exclude .git --exclude "*.log"

# Dry run mode
ppclient /var/log --dry-run</pre>
                    </div>
                </div>

                <div class="section">
                    <h2>Getting Started</h2>
                    <div class="card">
                        <h3>1. Create Your First API Key</h3>
                        <p>Use the bootstrap script to create your first API key:</p>
                        <pre>python -m putplace.scripts.create_api_key</pre>
                    </div>

                    <div class="card">
                        <h3>2. Install the Client</h3>
                        <pre>pip install -e .
source .venv/bin/activate
ppclient --help</pre>
                    </div>

                    <div class="card">
                        <h3>3. Start Scanning</h3>
                        <p>Use the <code>ppclient</code> command to scan directories and send metadata to the server.</p>
                    </div>
                </div>
            </div>

            <div class="footer">
                <p>PutPlace v""" + settings.api_version + """ | Built with FastAPI & MongoDB</p>
                <p style="margin-top: 5px; font-size: 0.9rem;">
                    <a href="/docs" style="color: #667eea; text-decoration: none;">API Documentation</a> |
                    <a href="/health" style="color: #667eea; text-decoration: none;">Health Status</a>
                </p>
            </div>
        </div>
        <script>
            // Check if user is logged in and update buttons
            (function() {
                const token = localStorage.getItem('access_token');
                const authButtons = document.getElementById('authButtons');

                if (token && authButtons) {
                    // User is logged in - show My Files, API Keys and Logout buttons
                    authButtons.innerHTML = `
                        <a href="/my_files" class="auth-btn">📁 My Files</a>
                        <a href="/api_keys_page" class="auth-btn">🔑 My API Keys</a>
                        <button onclick="logout()" class="auth-btn" style="cursor: pointer;">Logout</button>
                    `;
                }
            })();

            function logout() {
                localStorage.removeItem('access_token');
                window.location.reload();
            }
        </script>
    </body>
    </html>
    """
    return html_content


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
        data["uploaded_by_username"] = current_user.get("username")

        # Insert into MongoDB
        doc_id = await db.insert_file_metadata(data)

        # Determine if upload is required
        upload_required = not has_content
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

    This endpoint is called after POST /put_file indicates upload_required=true.
    The file content is stored using the configured storage backend (local or S3).

    Args:
        sha256: SHA256 hash of the file (must match file content)
        hostname: Hostname where file is located
        filepath: Full path to the file
        file: File upload
        db: Database instance (injected)
        storage: Storage backend instance (injected)
        api_key: API key metadata (injected, for authentication)

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

    try:
        # Read and verify file content
        content = await file.read()

        # Calculate SHA256 of uploaded content
        calculated_hash = hashlib.sha256(content).hexdigest()

        if calculated_hash != sha256:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File content SHA256 ({calculated_hash}) does not match provided hash ({sha256})",
            )

        logger.info(f"File upload verified for SHA256: {sha256}, size: {len(content)} bytes")

        # Store file content using storage backend
        stored = await storage.store(sha256, content)
        if not stored:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store file content",
            )

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
            "size": str(len(content)),
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
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Login - PutPlace</title>
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
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                max-width: 450px;
                width: 100%;
                background: white;
                border-radius: 10px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                font-size: 2rem;
                margin-bottom: 5px;
            }
            .header p {
                font-size: 1rem;
                opacity: 0.9;
            }
            .content {
                padding: 40px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                margin-bottom: 8px;
                color: #333;
                font-weight: 500;
            }
            .form-group input {
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 5px;
                font-size: 1rem;
                transition: border-color 0.3s;
            }
            .form-group input:focus {
                outline: none;
                border-color: #667eea;
            }
            .btn {
                width: 100%;
                padding: 14px;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
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
            .links {
                margin-top: 20px;
                text-align: center;
                padding-top: 20px;
                border-top: 1px solid #e0e0e0;
            }
            .links a {
                color: #667eea;
                text-decoration: none;
                transition: color 0.3s;
            }
            .links a:hover {
                color: #764ba2;
            }
            .back-link {
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔐 Login</h1>
                <p>Access your PutPlace account</p>
            </div>

            <div class="content">
                <div id="message" class="message"></div>

                <form id="loginForm">
                    <div class="form-group">
                        <label for="username">Username</label>
                        <input type="text" id="username" name="username" required autofocus>
                    </div>

                    <div class="form-group">
                        <label for="password">Password</label>
                        <input type="password" id="password" name="password" required>
                    </div>

                    <button type="submit" class="btn">Login</button>
                </form>

                <div class="links">
                    <p>Don't have an account? <a href="/register">Register here</a></p>
                    <p class="back-link"><a href="/">← Back to Home</a></p>
                </div>
            </div>
        </div>

        <script>
            const form = document.getElementById('loginForm');
            const messageDiv = document.getElementById('message');

            form.addEventListener('submit', async (e) => {
                e.preventDefault();

                const username = document.getElementById('username').value;
                const password = document.getElementById('password').value;
                const submitBtn = form.querySelector('button[type="submit"]');

                // Disable button during submission
                submitBtn.disabled = true;
                submitBtn.textContent = 'Logging in...';

                // Hide previous messages
                messageDiv.style.display = 'none';

                try {
                    const response = await fetch('/api/login', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ username, password })
                    });

                    const data = await response.json();

                    if (response.ok) {
                        // Store the token
                        localStorage.setItem('access_token', data.access_token);

                        // Show success message
                        messageDiv.textContent = 'Login successful! Redirecting...';
                        messageDiv.className = 'message success';
                        messageDiv.style.display = 'block';

                        // Redirect to My Files page after 1 second
                        setTimeout(() => {
                            window.location.href = '/my_files';
                        }, 1000);
                    } else {
                        // Show error message
                        messageDiv.textContent = data.detail || 'Login failed. Please try again.';
                        messageDiv.className = 'message error';
                        messageDiv.style.display = 'block';

                        submitBtn.disabled = false;
                        submitBtn.textContent = 'Login';
                    }
                } catch (error) {
                    messageDiv.textContent = 'An error occurred. Please try again.';
                    messageDiv.className = 'message error';
                    messageDiv.style.display = 'block';

                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Login';
                }
            });
        </script>
    </body>
    </html>
    """
    return html_content


@app.get("/register", response_class=HTMLResponse, tags=["users"])
async def register_page() -> str:
    """Registration page."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Register - PutPlace</title>
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
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                max-width: 450px;
                width: 100%;
                background: white;
                border-radius: 10px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                font-size: 2rem;
                margin-bottom: 5px;
            }
            .header p {
                font-size: 1rem;
                opacity: 0.9;
            }
            .content {
                padding: 40px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                margin-bottom: 8px;
                color: #333;
                font-weight: 500;
            }
            .form-group input {
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 5px;
                font-size: 1rem;
                transition: border-color 0.3s;
            }
            .form-group input:focus {
                outline: none;
                border-color: #667eea;
            }
            .form-group small {
                display: block;
                margin-top: 5px;
                color: #666;
                font-size: 0.85rem;
            }
            .btn {
                width: 100%;
                padding: 14px;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
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
            .links {
                margin-top: 20px;
                text-align: center;
                padding-top: 20px;
                border-top: 1px solid #e0e0e0;
            }
            .links a {
                color: #667eea;
                text-decoration: none;
                transition: color 0.3s;
            }
            .links a:hover {
                color: #764ba2;
            }
            .back-link {
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📝 Register</h1>
                <p>Create your PutPlace account</p>
            </div>

            <div class="content">
                <div id="message" class="message"></div>

                <form id="registerForm">
                    <div class="form-group">
                        <label for="username">Username *</label>
                        <input type="text" id="username" name="username" required autofocus minlength="3" maxlength="50">
                        <small>3-50 characters</small>
                    </div>

                    <div class="form-group">
                        <label for="email">Email *</label>
                        <input type="email" id="email" name="email" required>
                    </div>

                    <div class="form-group">
                        <label for="full_name">Full Name</label>
                        <input type="text" id="full_name" name="full_name">
                        <small>Optional</small>
                    </div>

                    <div class="form-group">
                        <label for="password">Password *</label>
                        <input type="password" id="password" name="password" required minlength="8">
                        <small>Minimum 8 characters</small>
                    </div>

                    <div class="form-group">
                        <label for="confirm_password">Confirm Password *</label>
                        <input type="password" id="confirm_password" name="confirm_password" required minlength="8">
                    </div>

                    <button type="submit" class="btn">Register</button>
                </form>

                <div class="links">
                    <p>Already have an account? <a href="/login">Login here</a></p>
                    <p class="back-link"><a href="/">← Back to Home</a></p>
                </div>
            </div>
        </div>

        <script>
            const form = document.getElementById('registerForm');
            const messageDiv = document.getElementById('message');

            form.addEventListener('submit', async (e) => {
                e.preventDefault();

                const username = document.getElementById('username').value;
                const email = document.getElementById('email').value;
                const full_name = document.getElementById('full_name').value;
                const password = document.getElementById('password').value;
                const confirmPassword = document.getElementById('confirm_password').value;
                const submitBtn = form.querySelector('button[type="submit"]');

                // Validate passwords match
                if (password !== confirmPassword) {
                    messageDiv.textContent = 'Passwords do not match';
                    messageDiv.className = 'message error';
                    messageDiv.style.display = 'block';
                    return;
                }

                // Disable button during submission
                submitBtn.disabled = true;
                submitBtn.textContent = 'Registering...';

                // Hide previous messages
                messageDiv.style.display = 'none';

                try {
                    const requestBody = {
                        username,
                        email,
                        password
                    };

                    // Add full_name only if provided
                    if (full_name) {
                        requestBody.full_name = full_name;
                    }

                    const response = await fetch('/api/register', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(requestBody)
                    });

                    const data = await response.json();

                    if (response.ok) {
                        // Show success message
                        messageDiv.textContent = 'Registration successful! Redirecting to login...';
                        messageDiv.className = 'message success';
                        messageDiv.style.display = 'block';

                        // Redirect to login page after 2 seconds
                        setTimeout(() => {
                            window.location.href = '/login';
                        }, 2000);
                    } else {
                        // Show error message
                        messageDiv.textContent = data.detail || 'Registration failed. Please try again.';
                        messageDiv.className = 'message error';
                        messageDiv.style.display = 'block';

                        submitBtn.disabled = false;
                        submitBtn.textContent = 'Register';
                    }
                } catch (error) {
                    messageDiv.textContent = 'An error occurred. Please try again.';
                    messageDiv.className = 'message error';
                    messageDiv.style.display = 'block';

                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Register';
                }
            });
        </script>
    </body>
    </html>
    """
    return html_content


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

        # Check if username already exists
        existing_username = await db.get_user_by_username(user_data.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )

        # Hash the password
        hashed_password = get_password_hash(user_data.password)

        # Generate confirmation token
        confirmation_token = generate_confirmation_token()
        expires_at = calculate_expiration_time(hours=24)

        # Create pending user in database
        pending_user_id = await db.create_pending_user(
            username=user_data.username,
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
            username=user_data.username,
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
            "email": user_data.email,
            "expires_in_hours": 24
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
    
    # Get user from database
    user = await db.get_user_by_username(user_login.username)
    
    if not user or not verify_password(user_login.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )

    return Token(access_token=access_token)


@app.get("/api/confirm-email", tags=["users"])
async def confirm_email(token: str, db: MongoDB = Depends(get_db)) -> dict:
    """
    Confirm user email and activate account.

    Args:
        token: Email confirmation token from the confirmation link

    Returns:
        Success message with user details
    """
    from .email_tokens import is_token_expired

    # Get pending user by token
    pending_user = await db.get_pending_user_by_token(token)

    if not pending_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired confirmation link"
        )

    # Check if token is expired
    if is_token_expired(pending_user["expires_at"]):
        # Delete expired pending user
        await db.delete_pending_user(token)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation link has expired. Please register again."
        )

    # Create actual user account
    try:
        user_id = await db.create_user(
            username=pending_user["username"],
            email=pending_user["email"],
            hashed_password=pending_user["hashed_password"],
            full_name=pending_user.get("full_name")
        )

        # Delete pending user after successful creation
        await db.delete_pending_user(token)

        return {
            "message": "Email confirmed successfully! Your account is now active.",
            "user_id": user_id,
            "username": pending_user["username"],
            "email": pending_user["email"]
        }

    except Exception as e:
        # Log error and return generic message
        logger.error(f"Error creating user from pending: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate account. Please contact support."
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
            await db.users.update_one(
                {"email": email},
                {
                    "$set": {
                        "auth_provider": "google",
                        "oauth_id": google_user_id,
                        "picture": picture
                    }
                }
            )

        username = existing_user["username"]
    else:
        # Create new user with Google OAuth
        # Generate username from email
        username_base = email.split('@')[0]
        username = username_base
        counter = 1

        # Ensure username is unique
        while await db.get_user_by_username(username):
            username = f"{username_base}{counter}"
            counter += 1

        # Create user document
        user_doc = {
            "username": username,
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
            await db.users.insert_one(user_doc)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create user: {str(e)}"
            )

    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
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
                    container.innerHTML = '<p class="no-files">No files uploaded yet. Use the ppclient tool to upload file metadata!</p>';
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
