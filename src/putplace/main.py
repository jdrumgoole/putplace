"""FastAPI application for file metadata storage."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pymongo.errors import ConnectionFailure

from .config import settings
from . import database
from .database import MongoDB
from .models import FileMetadata, FileMetadataResponse

logger = logging.getLogger(__name__)


def get_db() -> MongoDB:
    """Get database instance - dependency injection."""
    return database.mongodb


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan events."""
    # Startup
    try:
        await database.mongodb.connect()
        logger.info("Application startup: Database connected successfully")
    except ConnectionFailure as e:
        logger.error(f"Failed to connect to database during startup: {e}")
        logger.warning("Application starting without database connection - health endpoint will report degraded")
        # Don't raise - allow app to start in degraded mode
    except Exception as e:
        logger.error(f"Unexpected error during startup: {e}")
        raise

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


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "PutPlace API - File Metadata Storage", "status": "running"}


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
    response_model=FileMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["files"],
)
async def put_file(
    file_metadata: FileMetadata, db: MongoDB = Depends(get_db)
) -> FileMetadataResponse:
    """Store file metadata in MongoDB.

    Args:
        file_metadata: File metadata containing filepath, hostname, ip_address, and sha256
        db: Database instance (injected)

    Returns:
        Stored file metadata with MongoDB ID

    Raises:
        HTTPException: If database operation fails
    """
    try:
        # Convert to dict for MongoDB insertion
        data = file_metadata.model_dump()

        # Insert into MongoDB
        doc_id = await db.insert_file_metadata(data)

        # Return response with ID
        return FileMetadataResponse(**data, _id=doc_id)

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
async def get_file(sha256: str, db: MongoDB = Depends(get_db)) -> FileMetadataResponse:
    """Retrieve file metadata by SHA256 hash.

    Args:
        sha256: SHA256 hash of the file (64 characters)
        db: Database instance (injected)

    Returns:
        File metadata if found

    Raises:
        HTTPException: If file not found or invalid hash
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
