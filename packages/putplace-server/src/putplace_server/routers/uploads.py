"""Chunked upload operations router for PutPlace API."""

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile, status

from ..database import MongoDB
from ..dependencies import get_db, get_storage, get_current_user, get_chunk_storage_dir
from ..models import (
    ChunkUploadResponse,
    FileDeletionNotification,
    FileDeletionResponse,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadSessionInitiate,
    UploadSessionResponse,
)
from ..storage import StorageBackend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/uploads", tags=["chunked_uploads"])


@router.post("/initiate", response_model=UploadSessionResponse, status_code=status.HTTP_201_CREATED)
async def initiate_upload(
    request: UploadSessionInitiate,
    db: MongoDB = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> UploadSessionResponse:
    """Initiate a chunked upload session.

    Creates a new upload session for uploading a file in chunks.
    The session expires after 1 hour if not completed.

    Args:
        request: Upload session initialization request
        db: Database instance (injected)
        storage: Storage backend (injected)
        current_user: Current authenticated user (injected)

    Returns:
        Upload session information with upload_id

    Raises:
        HTTPException: If validation fails or session creation fails
    """
    try:
        # Generate unique upload ID
        upload_id = str(uuid.uuid4())

        # Determine storage backend type
        storage_backend = "s3" if hasattr(storage, "s3_client") else "local"

        # Create upload session in database
        await db.create_upload_session(
            upload_id=upload_id,
            filepath=request.filepath,
            hostname=request.hostname,
            sha256=request.sha256,
            file_size=request.file_size,
            chunk_size=request.chunk_size,
            total_chunks=request.total_chunks,
            storage_backend=storage_backend,
            user_id=str(current_user.get("_id")),
        )

        # Create temporary directory for chunks (local storage)
        if storage_backend == "local":
            chunk_dir = get_chunk_storage_dir() / upload_id
            chunk_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created chunk directory: {chunk_dir}")

        # Get session to return expiration time
        session = await db.get_upload_session(upload_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create upload session"
            )

        logger.info(
            f"Upload session initiated: {upload_id} for {request.filepath} "
            f"({request.file_size} bytes, {request.total_chunks} chunks)"
        )

        return UploadSessionResponse(
            upload_id=upload_id,
            expires_at=session["expires_at"],
            message="Upload session created successfully"
        )

    except Exception as e:
        logger.error(f"Failed to initiate upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate upload: {str(e)}"
        ) from e


@router.put("/{upload_id}/chunk/{chunk_num}", response_model=ChunkUploadResponse)
async def upload_chunk(
    upload_id: str,
    chunk_num: int,
    request: Request,
    db: MongoDB = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> ChunkUploadResponse:
    """Upload a single chunk for an upload session.

    Accepts raw binary data as the request body (application/octet-stream).

    Args:
        upload_id: Upload session identifier
        chunk_num: Chunk number (0-indexed)
        request: FastAPI request object (to read body)
        db: Database instance (injected)
        storage: Storage backend (injected)
        current_user: Current authenticated user (injected)

    Returns:
        Chunk upload confirmation with etag

    Raises:
        HTTPException: If session not found, chunk number invalid, or upload fails
    """
    try:
        # Read chunk data from request body
        chunk_data = await request.body()
        # Get upload session
        session = await db.get_upload_session(upload_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Upload session {upload_id} not found"
            )

        # Check if session expired
        from datetime import datetime
        if session["expires_at"] < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Upload session has expired"
            )

        # Verify user owns this session
        if str(session["user_id"]) != str(current_user.get("_id")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to upload to this session"
            )

        # Validate chunk number
        if chunk_num < 0 or chunk_num >= session["total_chunks"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid chunk number: {chunk_num} (must be 0-{session['total_chunks']-1})"
            )

        # Check if chunk already uploaded
        uploaded_chunks = session.get("uploaded_chunks", [])
        if any(chunk["chunk_num"] == chunk_num for chunk in uploaded_chunks):
            # Chunk already uploaded, return existing etag
            existing_chunk = next(c for c in uploaded_chunks if c["chunk_num"] == chunk_num)
            logger.info(f"Chunk {chunk_num} already uploaded for session {upload_id}")
            return ChunkUploadResponse(
                chunk_num=chunk_num,
                etag=existing_chunk["etag"],
                received_bytes=0,
                uploaded_chunks=len(uploaded_chunks),
                total_chunks=session["total_chunks"]
            )

        # Chunk data already provided as parameter
        received_bytes = len(chunk_data)

        # Calculate chunk hash (etag)
        chunk_hash = hashlib.sha256(chunk_data).hexdigest()

        # Store chunk (temporarily for local, directly to S3 for s3 backend)
        if session["storage_backend"] == "local":
            # Store chunk to temporary file
            chunk_dir = get_chunk_storage_dir() / upload_id
            chunk_file = chunk_dir / f"chunk_{chunk_num:06d}"
            chunk_file.write_bytes(chunk_data)
            logger.debug(f"Stored chunk {chunk_num} to {chunk_file}")
        else:
            # For S3, would use multipart upload API
            # TODO: Implement S3 multipart upload
            logger.warning("S3 chunked upload not yet implemented")

        # Update session in database
        await db.add_uploaded_chunk(upload_id, chunk_num, chunk_hash)

        # Get updated session
        updated_session = await db.get_upload_session(upload_id)
        uploaded_chunks_count = len(updated_session.get("uploaded_chunks", []))

        logger.info(
            f"Chunk {chunk_num} uploaded for session {upload_id} "
            f"({uploaded_chunks_count}/{session['total_chunks']} chunks)"
        )

        return ChunkUploadResponse(
            chunk_num=chunk_num,
            etag=chunk_hash,
            received_bytes=received_bytes,
            uploaded_chunks=uploaded_chunks_count,
            total_chunks=session["total_chunks"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload chunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload chunk: {str(e)}"
        ) from e


@router.post("/{upload_id}/complete", response_model=UploadCompleteResponse)
async def complete_upload(
    upload_id: str,
    request: UploadCompleteRequest,
    db: MongoDB = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> UploadCompleteResponse:
    """Complete a chunked upload session.

    Assembles all chunks into final file and verifies integrity.

    Args:
        upload_id: Upload session identifier
        request: List of uploaded parts with etags
        db: Database instance (injected)
        storage: Storage backend (injected)
        current_user: Current authenticated user (injected)

    Returns:
        File metadata with storage location

    Raises:
        HTTPException: If session not found, chunks missing, or verification fails
    """
    try:
        # Get upload session
        session = await db.get_upload_session(upload_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Upload session {upload_id} not found"
            )

        # Verify user owns this session
        if str(session["user_id"]) != str(current_user.get("_id")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to complete this upload"
            )

        # Verify all chunks are uploaded
        uploaded_chunks = session.get("uploaded_chunks", [])
        if len(uploaded_chunks) != session["total_chunks"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Not all chunks uploaded: {len(uploaded_chunks)}/{session['total_chunks']}"
            )

        # Verify etags match
        for part in request.parts:
            chunk_num = part.get("chunk_num")
            expected_etag = part.get("etag")

            matching_chunk = next((c for c in uploaded_chunks if c["chunk_num"] == chunk_num), None)
            if not matching_chunk:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Chunk {chunk_num} not found in session"
                )

            if matching_chunk["etag"] != expected_etag:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"ETag mismatch for chunk {chunk_num}"
                )

        logger.info(f"Assembling {session['total_chunks']} chunks for upload {upload_id}")

        # Assemble chunks into final file
        if session["storage_backend"] == "local":
            # Concatenate chunks
            chunk_dir = get_chunk_storage_dir() / upload_id
            final_file_path = chunk_dir / "assembled_file"

            # Calculate SHA256 while assembling
            hash_calculator = hashlib.sha256()

            with open(final_file_path, "wb") as final_file:
                for i in range(session["total_chunks"]):
                    chunk_file = chunk_dir / f"chunk_{i:06d}"
                    if not chunk_file.exists():
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Chunk file {i} missing"
                        )

                    chunk_data = chunk_file.read_bytes()
                    hash_calculator.update(chunk_data)
                    final_file.write(chunk_data)

            # Verify final SHA256
            calculated_hash = hash_calculator.hexdigest()
            if calculated_hash != session["sha256"]:
                # Hash mismatch - delete assembled file
                final_file_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SHA256 mismatch: expected {session['sha256']}, got {calculated_hash}"
                )

            logger.info(f"SHA256 verified for upload {upload_id}: {calculated_hash}")

            # Store final file using storage backend
            with open(final_file_path, "rb") as f:
                file_data = f.read()
                stored = await storage.store(session["sha256"], file_data)

            if not stored:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to store assembled file"
                )

            # Clean up temporary files
            import shutil
            shutil.rmtree(chunk_dir, ignore_errors=True)
            logger.info(f"Cleaned up temporary chunks for {upload_id}")

        else:
            # For S3, complete multipart upload
            # TODO: Implement S3 multipart completion
            logger.warning("S3 multipart completion not yet implemented")

        # Get storage path
        storage_path = storage.get_storage_path(session["sha256"])

        # Create file metadata entry
        from ..models import FileMetadata
        file_metadata = FileMetadata(
            filepath=session["filepath"],
            hostname=session["hostname"],
            ip_address="",  # Not provided in chunked upload
            sha256=session["sha256"],
            file_size=session["file_size"],
            file_mode=0,
            file_uid=0,
            file_gid=0,
            file_mtime=0.0,
            file_atime=0.0,
            file_ctime=0.0,
            has_file_content=True,
            storage_path=storage_path,
            uploaded_by_user_id=str(current_user.get("_id")),
        )

        # Insert file metadata
        file_id = await db.insert_file_metadata(file_metadata.model_dump())

        # Mark upload session as completed
        await db.complete_upload_session(upload_id)

        logger.info(f"Upload completed: {upload_id} -> file_id: {file_id}")

        return UploadCompleteResponse(
            file_id=file_id,
            sha256=session["sha256"],
            file_size=session["file_size"],
            status="completed",
            storage_location=storage_path
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to complete upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete upload: {str(e)}"
        ) from e


@router.delete("/{upload_id}")
async def abort_upload(
    upload_id: str,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Abort an upload session and clean up temporary files.

    Args:
        upload_id: Upload session identifier
        db: Database instance (injected)
        current_user: Current authenticated user (injected)

    Returns:
        Abortion confirmation

    Raises:
        HTTPException: If session not found or user doesn't have permission
    """
    try:
        # Get upload session
        session = await db.get_upload_session(upload_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Upload session {upload_id} not found"
            )

        # Verify user owns this session
        if str(session["user_id"]) != str(current_user.get("_id")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to abort this upload"
            )

        # Clean up temporary chunks
        chunks_deleted = 0
        if session["storage_backend"] == "local":
            chunk_dir = get_chunk_storage_dir() / upload_id
            if chunk_dir.exists():
                import shutil
                shutil.rmtree(chunk_dir, ignore_errors=True)
                chunks_deleted = len(session.get("uploaded_chunks", []))
                logger.info(f"Cleaned up {chunks_deleted} chunks for aborted upload {upload_id}")

        # Mark session as aborted
        await db.abort_upload_session(upload_id)

        logger.info(f"Upload aborted: {upload_id}")

        return {
            "upload_id": upload_id,
            "status": "aborted",
            "chunks_uploaded": len(session.get("uploaded_chunks", [])),
            "chunks_deleted": chunks_deleted
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to abort upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to abort upload: {str(e)}"
        ) from e


# File deletion notification endpoint

deletion_router = APIRouter(prefix="/api/files", tags=["file_deletion"])


@deletion_router.delete("/{sha256}", response_model=FileDeletionResponse)
async def delete_file_notification(
    sha256: str,
    request: FileDeletionNotification,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> FileDeletionResponse:
    """Receive notification that a file has been deleted on the client.

    Marks the file as deleted (soft delete) in the database.

    Args:
        sha256: SHA256 hash of the deleted file
        request: Deletion notification details
        db: Database instance (injected)
        current_user: Current authenticated user (injected)

    Returns:
        Deletion confirmation

    Raises:
        HTTPException: If file not found or validation fails
    """
    if len(sha256) != 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SHA256 hash must be exactly 64 characters"
        )

    try:
        # Mark file as deleted
        updated = await db.mark_file_deleted(
            sha256=sha256,
            hostname=request.hostname,
            filepath=request.filepath,
            deleted_at=request.deleted_at
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {request.filepath} on {request.hostname}"
            )

        logger.info(
            f"File deletion recorded: {request.filepath} on {request.hostname} "
            f"(SHA256: {sha256})"
        )

        return FileDeletionResponse(
            sha256=sha256,
            filepath=request.filepath,
            hostname=request.hostname,
            status="deleted",
            deleted_at=request.deleted_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record file deletion: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record file deletion: {str(e)}"
        ) from e
