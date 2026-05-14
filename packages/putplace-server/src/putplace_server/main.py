"""FastAPI application for file metadata storage."""

import hashlib
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Body, Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pymongo.errors import ConnectionFailure

from .config import settings
from . import database
from . import dependencies
from .auth import APIKeyAuth, get_current_api_key
from .regstack_integration import get_regstack, reset_regstack
from .database import MongoDB
from .models import (
    APIKeyCreate,
    APIKeyInfo,
    APIKeyResponse,
    ChunkUploadResponse,
    FileDeletionNotification,
    FileDeletionResponse,
    FileMetadata,
    FileMetadataResponse,
    FileMetadataUploadResponse,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadSessionInitiate,
    UploadSessionResponse,
    User,
)
from .storage import get_storage_backend, StorageBackend
from .templates import get_home_page

logger = logging.getLogger(__name__)


async def ensure_admin_exists() -> None:
    """Create or promote a regstack superuser on first startup.

    Hybrid strategy:
    1. If any user already exists in regstack, do nothing.
    2. If PUTPLACE_ADMIN_EMAIL and PUTPLACE_ADMIN_PASSWORD are set, use them.
    3. Otherwise generate a random password and log/write it once.
    """
    from datetime import datetime

    rs = get_regstack()

    try:
        existing_count = await rs.users.count()
        if existing_count > 0:
            logger.debug("Users already exist, skipping admin bootstrap")
            return

        admin_email = os.getenv("PUTPLACE_ADMIN_EMAIL", "admin@putplace.example.com")
        admin_pass = os.getenv("PUTPLACE_ADMIN_PASSWORD")

        if admin_pass:
            if len(admin_pass) < 8:
                logger.error(
                    "PUTPLACE_ADMIN_PASSWORD must be at least 8 characters. "
                    "Admin user not created."
                )
                return
            await rs.bootstrap_admin(email=admin_email, password=admin_pass)
            logger.info(f"✅ Created admin user from environment: {admin_email}")
            return

        import secrets
        random_password = secrets.token_urlsafe(16)  # ~21 chars
        await rs.bootstrap_admin(email="admin@putplace.example.com", password=random_password)

        logger.warning("=" * 80)
        logger.warning("🔐 INITIAL ADMIN CREDENTIALS GENERATED")
        logger.warning("=" * 80)
        logger.warning("   Email: admin@putplace.example.com")
        logger.warning(f"   Password: {random_password}")
        logger.warning("")
        logger.warning("⚠️  SAVE THESE CREDENTIALS NOW - They won't be shown again!")
        logger.warning("")
        logger.warning("For production, set environment variables instead:")
        logger.warning("   PUTPLACE_ADMIN_EMAIL=admin@putplace.example.com")
        logger.warning("   PUTPLACE_ADMIN_PASSWORD=your-secure-password")
        logger.warning("=" * 80)

        from pathlib import Path
        import tempfile

        creds_file = Path(tempfile.gettempdir()) / "putplace_initial_creds.txt"
        try:
            creds_file.write_text(
                f"PutPlace Initial Admin Credentials\n"
                f"{'=' * 40}\n"
                f"Email: admin@putplace.example.com\n"
                f"Password: {random_password}\n"
                f"Created: {datetime.utcnow()}\n\n"
                f"⚠️  DELETE THIS FILE after saving credentials!\n"
            )
            creds_file.chmod(0o600)
            logger.warning(f"📄 Credentials also written to: {creds_file}")
            logger.warning("")
        except Exception as e:
            logger.debug(f"Could not write credentials file: {e}")

    except Exception as e:
        logger.error(f"Failed to ensure admin user exists: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan events."""
    # Startup - Database connection is CRITICAL
    try:
        await database.mongodb.connect()
        logger.info("Application startup: Database connected successfully")

        # Start cleanup task for expired pending users
        from .cleanup_tasks import start_cleanup_task
        start_cleanup_task()

    except ConnectionFailure as e:
        logger.critical(f"CRITICAL: Failed to connect to database during startup: {e}")
        logger.critical("Database connection is required - server cannot start")
        raise  # Exit immediately - database is required
    except Exception as e:
        logger.error(f"Unexpected error during startup: {e}")
        raise

    # Initialize storage backend
    try:
        if settings.storage_backend == "local":
            dependencies.storage_backend = get_storage_backend(
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
            dependencies.storage_backend = get_storage_backend(
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

    # Install regstack schema, then bootstrap the admin user via regstack.
    # Order matters: bootstrap_admin needs the unique-email index in place.
    regstack = get_regstack()
    try:
        await regstack.install_schema()
        logger.info("regstack schema installed")
    except Exception as e:
        logger.error(f"Failed to install regstack schema: {e}")
        raise

    await ensure_admin_exists()

    yield

    # Shutdown
    # Drop the singleton entirely so a subsequent lifespan (e.g. in tests that
    # reuse this app object) gets a freshly-bound Mongo client. PyMongo binds
    # the AsyncMongoClient to the event loop on first I/O, and an aclose()-d
    # client cannot be reopened.
    try:
        await reset_regstack()
    except Exception as e:
        logger.error(f"Error closing regstack backend: {e}")
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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    # Prevent clickjacking attacks
    response.headers["X-Frame-Options"] = "DENY"

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Enable browser XSS protection (legacy, but doesn't hurt)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Content Security Policy - restrictive for API
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # Allow inline scripts for HTML pages
        "style-src 'self' 'unsafe-inline'; "  # Allow inline styles for HTML pages
        "img-src 'self' data: https:; "  # Allow images from self, data URIs, and HTTPS
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"  # Equivalent to X-Frame-Options: DENY
    )

    # Referrer Policy - don't leak URLs
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions Policy (formerly Feature-Policy)
    response.headers["Permissions-Policy"] = (
        "geolocation=(), "
        "microphone=(), "
        "camera=(), "
        "payment=(), "
        "usb=(), "
        "magnetometer=(), "
        "gyroscope=(), "
        "accelerometer=()"
    )

    return response


# Mount static files directory
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info(f"Static files mounted at /static from {STATIC_DIR}")


# Import dependency functions from dependencies module
from .dependencies import (
    get_db,
    get_storage,
    get_current_user,
    get_current_admin_user,
    get_chunk_storage_dir,
)

# Import and register routers
from .routers import (
    pages_router,
    files_router,
    api_keys_router,
    deletion_router,
    admin_router,
)
from .routers.uploads import router as uploads_router

# Register routers (auth routes live entirely under regstack at /api/v2/auth/*
# and /account/*; those are mounted below.)
app.include_router(pages_router)
app.include_router(files_router)
app.include_router(api_keys_router)
app.include_router(uploads_router)
app.include_router(deletion_router)
app.include_router(admin_router)

# Phase 1 of regstack migration: mount regstack's JSON + SSR routers and
# static assets alongside putplace's existing routes. New paths are namespaced
# (api_prefix=/api/v2/auth, ui_prefix=/account, static_prefix=/regstack-static),
# so nothing existing breaks. The instance is built in get_regstack() and
# shared with the lifespan handler.
_regstack_app = get_regstack()
app.include_router(_regstack_app.router, prefix=_regstack_app.config.api_prefix)
if _regstack_app.config.enable_ui_router:
    app.include_router(_regstack_app.ui_router, prefix=_regstack_app.config.ui_prefix)
app.mount(_regstack_app.config.static_prefix, _regstack_app.static_files)


# Chunked upload endpoints are now in uploads_router









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























