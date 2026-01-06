"""File uploader for putplace-assist.

Component 3 of the 3-component queue-based architecture.

This module provides background tasks that:
1. Upload Worker: Processes queue_pending_upload (FIFO) and uploads files with chunked uploads
2. Deletion Worker: Processes queue_pending_deletion (FIFO) and notifies server of deletions
3. Implements retry logic with exponential backoff (3 retries)
4. Handles authentication with access tokens
"""

import asyncio
import hashlib
import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx
from cryptography.fernet import Fernet

from .config import settings
from .database import db
from .models import EventType, UploadStatus, UploadType

logger = logging.getLogger(__name__)

# Encryption key for storing passwords (should be persisted securely)
# In production, this would come from a secure key store
_ENCRYPTION_KEY: Optional[bytes] = None


def get_encryption_key() -> bytes:
    """Get or generate encryption key for password storage."""
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is None:
        # Try to load from file
        key_file = settings.db_path_resolved.parent / ".key"
        if key_file.exists():
            _ENCRYPTION_KEY = key_file.read_bytes()
        else:
            # Generate new key
            _ENCRYPTION_KEY = Fernet.generate_key()
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_bytes(_ENCRYPTION_KEY)
            key_file.chmod(0o600)
    return _ENCRYPTION_KEY


def encrypt_password(password: str) -> str:
    """Encrypt a password for storage."""
    f = Fernet(get_encryption_key())
    return f.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Decrypt a stored password."""
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted.encode()).decode()


def get_hostname() -> str:
    """Get the current hostname."""
    return socket.gethostname()


def get_ip_address() -> str:
    """Get the primary IP address of this machine."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


@dataclass
class UploadProgress:
    """Progress information for an upload."""

    file_id: int
    filepath: str
    status: UploadStatus
    progress_percent: float = 0.0
    bytes_uploaded: int = 0
    total_bytes: int = 0
    error_message: Optional[str] = None


@dataclass
class UploadQueueItem:
    """An item in the upload queue."""

    file_id: int
    filepath: str
    sha256: str
    file_size: int
    upload_content: bool = False


class Uploader:
    """Handles file uploads to remote putplace server."""

    def __init__(
        self,
        parallel_uploads: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        retry_delay: Optional[float] = None,
        timeout_seconds: Optional[int] = None,
    ):
        """Initialize uploader.

        Args:
            parallel_uploads: Number of parallel uploads
            retry_attempts: Number of retry attempts
            retry_delay: Delay between retries in seconds
            timeout_seconds: Timeout for each file upload in seconds
        """
        self.parallel_uploads = parallel_uploads or settings.uploader_parallel_uploads
        self.retry_attempts = retry_attempts or settings.uploader_retry_attempts
        self.retry_delay = retry_delay or settings.uploader_retry_delay_seconds
        self.timeout_seconds = timeout_seconds or settings.uploader_timeout_seconds

        self._queue: asyncio.Queue[UploadQueueItem] = asyncio.Queue()
        self._running = False
        self._workers: list[asyncio.Task] = []
        self._access_tokens: dict[str, str] = {}  # server_url -> token
        self._progress: dict[int, UploadProgress] = {}
        self._completed_count = 0
        self._failed_count = 0

    async def start(self) -> None:
        """Start the uploader workers."""
        if self._running:
            logger.warning("Uploader already running")
            return

        logger.info(f"Starting uploader with {self.parallel_uploads} workers...")
        self._running = True

        # Start worker tasks
        for i in range(self.parallel_uploads):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)

        logger.info("Uploader started")

    async def stop(self) -> None:
        """Stop the uploader workers."""
        if not self._running:
            return

        logger.info("Stopping uploader...")
        self._running = False

        # Cancel all workers
        for worker in self._workers:
            worker.cancel()

        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        self._access_tokens.clear()
        logger.info("Uploader stopped")

    async def _worker(self, worker_id: int) -> None:
        """Worker task that processes upload queue items."""
        logger.debug(f"Worker {worker_id} started")

        while self._running:
            try:
                # Get item from queue with timeout
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                try:
                    await self._process_upload(item)
                finally:
                    self._queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

        logger.debug(f"Worker {worker_id} stopped")

    async def queue_file(
        self,
        file_id: int,
        filepath: str,
        sha256: str,
        file_size: int,
        upload_content: bool = False,
    ) -> None:
        """Add a file to the upload queue.

        Args:
            file_id: Database file ID
            filepath: Path to the file
            sha256: SHA256 hash of the file
            file_size: Size of the file in bytes
            upload_content: Whether to upload file content (not just metadata)
        """
        item = UploadQueueItem(
            file_id=file_id,
            filepath=filepath,
            sha256=sha256,
            file_size=file_size,
            upload_content=upload_content,
        )
        await self._queue.put(item)

        # Initialize progress
        self._progress[file_id] = UploadProgress(
            file_id=file_id,
            filepath=filepath,
            status=UploadStatus.PENDING,
            total_bytes=file_size,
        )

        logger.debug(f"Queued file for upload: {filepath}")

    async def queue_pending_files(
        self, path_prefix: Optional[str] = None, upload_content: bool = False
    ) -> int:
        """Queue all files that need uploading.

        Args:
            path_prefix: Optional path prefix filter
            upload_content: Whether to upload file content

        Returns:
            Number of files queued
        """
        count = 0

        # Canonicalize path_prefix to handle symlinks (e.g., /tmp -> /private/tmp on macOS)
        if path_prefix:
            try:
                path_prefix = str(Path(path_prefix).expanduser().resolve())
            except Exception:
                pass  # If canonicalization fails, use the original path

        # Get pending uploads from database
        pending = await db.get_pending_uploads(limit=1000)

        # Filter by path prefix if specified
        if path_prefix:
            pending = [e for e in pending if e.filepath.startswith(path_prefix)]

        # Queue each file
        for file in pending:
            await self.queue_file(
                file_id=file.id,
                filepath=file.filepath,
                sha256=file.sha256,
                file_size=file.file_size,
                upload_content=upload_content,
            )
            count += 1

        logger.info(f"Queued {count} files for upload")
        return count

    async def queue_unprocessed_files(
        self, path_prefix: Optional[str] = None, upload_content: bool = False, limit: int = 100
    ) -> int:
        """Queue files directly from filelog tables, calculating SHA256 inline.

        This processes files that haven't been SHA256'd yet, calculating the hash
        immediately before upload for faster feedback.

        Args:
            path_prefix: Optional path prefix filter
            upload_content: Whether to upload file content
            limit: Maximum number of files to process

        Returns:
            Number of files queued
        """
        count = 0

        # Canonicalize path_prefix to handle symlinks (e.g., /tmp -> /private/tmp on macOS)
        if path_prefix:
            try:
                path_prefix = str(Path(path_prefix).expanduser().resolve())
            except Exception:
                pass  # If canonicalization fails, use the original path

        # Get unprocessed entries from monthly filelog tables
        entries = await db.get_unprocessed_entries(limit=limit)

        # Filter by path prefix if specified
        if path_prefix:
            entries = [e for e in entries if e.filepath.startswith(path_prefix)]

        # Process each file: calculate SHA256 and queue for upload
        for entry in entries:
            filepath = Path(entry.filepath)

            # Check if file still exists and get current stats
            if not filepath.exists():
                logger.warning(f"File no longer exists, skipping: {filepath}")
                continue

            # Get current file stats (file may have changed since scan)
            try:
                stat_info = os.stat(filepath)
                current_file_size = stat_info.st_size
                current_mtime = stat_info.st_mtime
            except Exception as e:
                logger.error(f"Failed to stat file {filepath}: {e}")
                continue

            # Calculate SHA256 inline
            try:
                sha256 = await self._calculate_sha256(filepath)
            except Exception as e:
                logger.error(f"Failed to calculate SHA256 for {filepath}: {e}")
                await db.log_activity(
                    EventType.UPLOAD_FAILED,
                    filepath=str(filepath),
                    message=f"SHA256 calculation failed: {filepath.name}",
                    details={"error": str(e)},
                )
                continue

            # Store SHA256 in database with current file stats
            try:
                sha256_entry_id = await db.add_sha256_entry(
                    filepath=entry.filepath,
                    ctime=stat_info.st_ctime,
                    mtime=current_mtime,
                    atime=stat_info.st_atime,
                    file_size=current_file_size,  # Use current file size, not stale database value
                    sha256=sha256,
                    source_table=entry.source_table,
                    source_id=entry.id,
                    permissions=stat_info.st_mode,
                    uid=stat_info.st_uid,
                    gid=stat_info.st_gid,
                )
            except Exception as e:
                logger.error(f"Failed to store SHA256 for {filepath}: {e}")
                continue

            # Mark as pending upload so queue_pending_files() doesn't re-queue it
            # This is done BEFORE queueing to prevent race conditions
            await db.update_upload_status(sha256_entry_id, "queued")

            # Queue for upload with current file size
            await self.queue_file(
                file_id=sha256_entry_id,
                filepath=str(filepath),
                sha256=sha256,
                file_size=current_file_size,  # Use current file size
                upload_content=upload_content,
            )
            count += 1

            logger.info(f"Calculated SHA256 and queued: {filepath.name} ({sha256[:16]}...) size={current_file_size}")

        logger.info(f"Processed and queued {count} files for upload")
        return count

    async def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash for a file.

        Args:
            file_path: Path to the file

        Returns:
            Hexadecimal SHA256 hash string
        """
        sha256_hash = hashlib.sha256()

        # Run file reading in thread pool to avoid blocking
        loop = asyncio.get_event_loop()

        def read_and_hash():
            """Read file and calculate hash."""
            try:
                with open(file_path, "rb") as f:
                    # Read in chunks to handle large files
                    while True:
                        chunk = f.read(65536)  # 64KB chunks
                        if not chunk:
                            break
                        sha256_hash.update(chunk)
                return sha256_hash.hexdigest()
            except Exception as e:
                logger.error(f"Error calculating SHA256 for {file_path}: {e}")
                raise

        return await loop.run_in_executor(None, read_and_hash)

    async def _get_access_token(
        self,
        server_url: str,
        username: str,
        password: str,
        server_id: Optional[int] = None,
    ) -> Optional[str]:
        """Get or refresh access token for a server.

        Args:
            server_url: Base URL of the server
            username: Username for authentication
            password: Password for authentication
            server_id: Server ID for credential invalidation (optional)

        Returns:
            Access token or None if authentication failed
        """
        # Check cached token
        if server_url in self._access_tokens:
            return self._access_tokens[server_url]

        login_url = f"{server_url.rstrip('/')}/api/login"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    login_url,
                    json={"email": username, "password": password},
                )

                if response.status_code == 200:
                    data = response.json()
                    token = data.get("access_token")
                    if token:
                        self._access_tokens[server_url] = token
                        return token
                elif response.status_code == 401:
                    # Unauthorized - credentials are invalid (user deleted or password changed)
                    logger.warning(
                        f"Authentication failed with 401 Unauthorized for {username}@{server_url}. "
                        "This usually means the user has been deleted or credentials are invalid."
                    )

                    # Remove invalid credentials from database
                    if server_id:
                        logger.info(f"Removing invalid server credentials (ID: {server_id}) from database")
                        try:
                            await db.delete_server(server_id)
                            logger.info(f"Successfully removed server credentials for {server_url}")

                            # Log activity for visibility
                            await db.log_activity(
                                EventType.UPLOAD_FAILED,
                                filepath="N/A",
                                message=f"Server credentials auto-removed: {username}@{server_url}",
                                details={
                                    "reason": "401 Unauthorized - user deleted or credentials invalid",
                                    "server_id": server_id,
                                    "server_url": server_url,
                                    "username": username,
                                },
                            )
                        except Exception as e:
                            logger.error(f"Failed to remove server credentials: {e}")

                    return None
                else:
                    logger.error(f"Login failed: {response.status_code} - {response.text}")
                    return None

        except httpx.ConnectError:
            logger.error(f"Could not connect to server: {server_url}")
            return None
        except Exception as e:
            logger.error(f"Login error: {e}")
            return None

    async def _process_upload(self, item: UploadQueueItem) -> bool:
        """Process a single upload.

        Returns:
            True if upload was successful
        """
        filepath = Path(item.filepath)
        logger.info(f"[UPLOAD] Starting processing for file_id={item.file_id}, filepath={filepath}")

        # Check if file has changed since it was scanned
        try:
            current_stat = os.stat(filepath)
            current_mtime = current_stat.st_mtime
            current_size = current_stat.st_size

            # Get stored file info from database
            stored_entry = await db.get_sha256_by_id(item.file_id)
            if stored_entry:
                stored_mtime = stored_entry.mtime
                stored_size = stored_entry.file_size

                # Compare current stat with stored values
                if current_mtime != stored_mtime or current_size != stored_size:
                    logger.warning(
                        f"File changed since scan: {filepath} "
                        f"(mtime: {stored_mtime} -> {current_mtime}, size: {stored_size} -> {current_size})"
                    )

                    # Remove from upload queue (delete from filelog_sha256)
                    await db.delete_sha256_entry(item.file_id)

                    # Requeue for processing (will trigger rescan and SHA256 recalculation)
                    await db.log_activity(
                        EventType.FILE_MODIFIED,
                        filepath=item.filepath,
                        message=f"File modified, requeuing for scan: {filepath.name}",
                        details={
                            "old_mtime": stored_mtime,
                            "new_mtime": current_mtime,
                            "old_size": stored_size,
                            "new_size": current_size
                        }
                    )

                    # Add back to source table for rescanning
                    await db.add_file_to_monthly_table(
                        filepath=item.filepath,
                        file_size=current_size,
                        file_mtime=current_mtime
                    )

                    logger.info(f"File {filepath} requeued for processing due to changes")
                    return False
        except FileNotFoundError:
            logger.error(f"File not found: {filepath}")
            await self._handle_upload_failure(item, "File not found")
            return False
        except Exception as e:
            logger.error(f"Failed to check file stat for {filepath}: {e}")
            # Continue with upload if stat check fails
            pass

        # Update progress
        self._progress[item.file_id] = UploadProgress(
            file_id=item.file_id,
            filepath=item.filepath,
            status=UploadStatus.IN_PROGRESS,
            total_bytes=item.file_size,
        )
        logger.info(f"[UPLOAD] Progress updated to IN_PROGRESS for file_id={item.file_id}")

        # Log upload started
        logger.info(f"[UPLOAD] Logging activity for file_id={item.file_id}")
        await db.log_activity(
            EventType.UPLOAD_STARTED,
            filepath=item.filepath,
            message=f"Starting upload: {filepath.name}",
            details={"upload_content": item.upload_content, "file_id": item.file_id},
        )
        logger.info(f"[UPLOAD] Activity logged for file_id={item.file_id}")

        # Get server configuration
        logger.info(f"[UPLOAD] Getting server config for file_id={item.file_id}")
        server_result = await db.get_default_server()
        logger.info(f"[UPLOAD] Server config retrieved for file_id={item.file_id}: {server_result is not None}")
        if not server_result:
            error_msg = "No server configured"
            await self._handle_upload_failure(item, error_msg)
            return False

        server, encrypted_password = server_result
        password = decrypt_password(encrypted_password)

        # Get access token (pass server_id for automatic credential invalidation on 401)
        token = await self._get_access_token(server.url, server.username, password, server.id)
        if not token:
            error_msg = "Authentication failed"
            await self._handle_upload_failure(item, error_msg)
            return False

        # Prepare headers
        headers = {"Authorization": f"Bearer {token}"}

        # Upload with retry
        for attempt in range(self.retry_attempts):
            try:
                success = await self._do_upload(
                    item=item,
                    server_url=server.url,
                    headers=headers,
                )

                if success:
                    # Update progress
                    self._progress[item.file_id] = UploadProgress(
                        file_id=item.file_id,
                        filepath=item.filepath,
                        status=UploadStatus.SUCCESS,
                        progress_percent=100.0,
                        bytes_uploaded=item.file_size,
                        total_bytes=item.file_size,
                    )

                    # Update upload status in database
                    upload_type = "full" if item.upload_content else "meta"
                    await db.update_upload_status(
                        entry_id=item.file_id,
                        status=upload_type,
                    )

                    await db.log_activity(
                        EventType.UPLOAD_COMPLETE,
                        filepath=item.filepath,
                        message=f"Upload complete: {filepath.name}",
                        details={"server": server.name, "upload_type": upload_type, "file_id": item.file_id},
                    )

                    self._completed_count += 1
                    return True

            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    await self._handle_upload_failure(item, str(e))

        return False

    async def _do_upload(
        self,
        item: UploadQueueItem,
        server_url: str,
        headers: dict,
    ) -> bool:
        """Perform the actual upload.

        Returns:
            True if upload was successful
        """
        filepath = Path(item.filepath)
        hostname = get_hostname()
        ip_address = get_ip_address()

        # Prepare metadata
        metadata = {
            "filepath": str(filepath.absolute()),
            "hostname": hostname,
            "ip_address": ip_address,
            "sha256": item.sha256,
        }

        # Get file stats if file exists
        if filepath.exists():
            import os
            stat_info = os.stat(filepath)
            metadata.update({
                "file_size": stat_info.st_size,
                "file_mode": stat_info.st_mode,
                "file_uid": stat_info.st_uid,
                "file_gid": stat_info.st_gid,
                "file_mtime": stat_info.st_mtime,
                "file_atime": stat_info.st_atime,
                "file_ctime": stat_info.st_ctime,
            })

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Send metadata
            metadata_url = f"{server_url.rstrip('/')}/put_file"
            response = await client.post(metadata_url, json=metadata, headers=headers)
            response.raise_for_status()

            data = response.json()

            # Check if content upload is required
            if item.upload_content and data.get("upload_required", False):
                upload_url = data.get("upload_url")
                if upload_url:
                    # Skip content upload for 0-byte files (no content to upload)
                    file_size = metadata.get("file_size", 0)
                    if file_size == 0:
                        logger.info(f"Skipping content upload for 0-byte file: {filepath.name}")
                    else:
                        await self._upload_content(
                            item=item,
                            filepath=filepath,
                            server_url=server_url,
                            upload_url=upload_url,
                            hostname=hostname,
                            headers=headers,
                        )

        return True

    async def _upload_content(
        self,
        item: UploadQueueItem,
        filepath: Path,
        server_url: str,
        upload_url: str,
        hostname: str,
        headers: dict,
    ) -> None:
        """Upload file content."""
        full_url = f"{server_url.rstrip('/')}{upload_url}"

        params = {
            "hostname": hostname,
            "filepath": str(filepath.absolute()),
        }

        # Read file and upload
        async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
            with open(filepath, "rb") as f:
                files = {"file": (filepath.name, f, "application/octet-stream")}
                response = await client.post(
                    full_url,
                    files=files,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()

        logger.info(f"Uploaded content: {filepath.name}")

    async def _handle_upload_failure(self, item: UploadQueueItem, error_message: str) -> None:
        """Handle upload failure."""
        filepath = Path(item.filepath)

        # Update progress
        self._progress[item.file_id] = UploadProgress(
            file_id=item.file_id,
            filepath=item.filepath,
            status=UploadStatus.FAILED,
            error_message=error_message,
        )

        # Mark as failed in database so it's not retried as pending
        # Use 'failed' status to distinguish from successful uploads ('meta'/'full')
        await db.update_upload_status(item.file_id, "failed")

        # Log failure
        await db.log_activity(
            EventType.UPLOAD_FAILED,
            filepath=item.filepath,
            message=f"Upload failed: {filepath.name}",
            details={"error": error_message, "file_id": item.file_id},
        )

        self._failed_count += 1
        logger.error(f"Upload failed for {filepath}: {error_message}")

    @property
    def is_running(self) -> bool:
        """Check if uploader is running."""
        return self._running

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    @property
    def completed_count(self) -> int:
        """Get count of completed uploads."""
        return self._completed_count

    @property
    def failed_count(self) -> int:
        """Get count of failed uploads."""
        return self._failed_count

    def get_progress(self, file_id: int) -> Optional[UploadProgress]:
        """Get progress for a specific file."""
        return self._progress.get(file_id)

    def get_all_progress(self) -> list[UploadProgress]:
        """Get progress for all files being uploaded."""
        return list(self._progress.values())

    def get_in_progress(self) -> list[UploadProgress]:
        """Get progress for files currently uploading."""
        return [p for p in self._progress.values() if p.status == UploadStatus.IN_PROGRESS]


# Global uploader instance
uploader = Uploader()
