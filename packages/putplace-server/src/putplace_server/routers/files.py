"""File operations router for PutPlace API."""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ..database import MongoDB
from ..dependencies import get_db, get_storage, get_current_user
from ..models import FileMetadata, FileMetadataResponse, FileMetadataUploadResponse
from ..storage import StorageBackend

logger = logging.getLogger(__name__)

router = APIRouter(tags=["files"])


@router.post(
    "/put_file",
    response_model=FileMetadataUploadResponse,
    status_code=status.HTTP_201_CREATED,
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
        current_user: Current authenticated user (injected)

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


@router.get(
    "/get_file/{sha256}",
    response_model=FileMetadataResponse,
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
        current_user: Current authenticated user (injected)

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


@router.post(
    "/upload_file/{sha256}",
    status_code=status.HTTP_200_OK,
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


@router.get("/api/my_files", response_model=list[FileMetadataResponse])
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
        current_user: Current logged-in user (injected)
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


@router.get("/api/clones/{sha256}", response_model=list[FileMetadataResponse])
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
        current_user: Current logged-in user (injected)

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
