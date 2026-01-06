"""File uploader for putplace-assist - Component 3.

Component 3 of the 3-component queue-based architecture.

This module provides background tasks that:
1. Upload Worker: Processes queue_pending_upload (FIFO) and uploads files with chunked uploads
2. Deletion Worker: Processes queue_pending_deletion (FIFO) and notifies server of deletions
3. Implements retry logic with exponential backoff (3 retries)
4. Handles authentication with access tokens
"""

import asyncio
import logging
import os
import socket
from pathlib import Path
from typing import Optional

import httpx
from cryptography.fernet import Fernet

from .activity import activity_manager
from .config import settings
from .database import db
from .models import EventType

logger = logging.getLogger(__name__)

# Encryption key for storing passwords
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


class UploaderV3:
    """Component 3: Uploader with chunked uploads and deletion handling."""

    def __init__(self):
        """Initialize uploader."""
        self._running = False
        self._upload_task: Optional[asyncio.Task] = None
        self._deletion_task: Optional[asyncio.Task] = None
        self._access_tokens: dict[str, str] = {}  # server_url -> token
        self._current_file: Optional[str] = None
        self._uploaded_today = 0
        self._failed_today = 0

    @property
    def is_running(self) -> bool:
        """Check if uploader is running."""
        return self._running

    @property
    def current_file(self) -> Optional[str]:
        """Get the file currently being uploaded."""
        return self._current_file

    @property
    def uploaded_today(self) -> int:
        """Get count of files uploaded today."""
        return self._uploaded_today

    @property
    def failed_today(self) -> int:
        """Get count of failed uploads today."""
        return self._failed_today

    async def start(self) -> None:
        """Start the upload and deletion workers."""
        if self._running:
            logger.warning("Uploader already running")
            return

        self._running = True

        # Start upload worker
        self._upload_task = asyncio.create_task(self._upload_worker())

        # Start deletion worker
        self._deletion_task = asyncio.create_task(self._deletion_worker())

        logger.info("Uploader started (upload and deletion workers)")

    async def stop(self) -> None:
        """Stop the upload and deletion workers."""
        self._running = False

        if self._upload_task:
            self._upload_task.cancel()
            try:
                await self._upload_task
            except asyncio.CancelledError:
                pass
            self._upload_task = None

        if self._deletion_task:
            self._deletion_task.cancel()
            try:
                await self._deletion_task
            except asyncio.CancelledError:
                pass
            self._deletion_task = None

        logger.info("Uploader stopped")

    async def _upload_worker(self) -> None:
        """Upload worker - processes queue_pending_upload (FIFO)."""
        while self._running:
            try:
                # Dequeue batch from queue_pending_upload (FIFO)
                queue_entries = await db.dequeue_for_upload(limit=settings.uploader_parallel_uploads)

                if queue_entries:
                    logger.debug(f"Processing {len(queue_entries)} files from upload queue")

                    # Process uploads concurrently (up to parallel_uploads limit)
                    tasks = [self._process_upload(entry) for entry in queue_entries]
                    await asyncio.gather(*tasks, return_exceptions=True)

                else:
                    # No entries to process, wait before checking again
                    await asyncio.sleep(5.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in upload worker loop: {e}")
                await asyncio.sleep(5)

    async def _deletion_worker(self) -> None:
        """Deletion worker - processes queue_pending_deletion (FIFO)."""
        while self._running:
            try:
                # Dequeue batch from queue_pending_deletion (FIFO)
                deletion_entries = await db.dequeue_for_deletion(limit=10)

                if deletion_entries:
                    logger.debug(f"Processing {len(deletion_entries)} deletions from deletion queue")

                    for entry in deletion_entries:
                        if not self._running:
                            break
                        await self._process_deletion(entry)

                else:
                    # No entries to process, wait before checking again
                    await asyncio.sleep(10.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in deletion worker loop: {e}")
                await asyncio.sleep(5)

    async def _get_access_token(
        self, server_url: str, username: str, password: str, server_id: Optional[int] = None
    ) -> Optional[str]:
        """Get or refresh access token for a server."""
        # Check cached token
        if server_url in self._access_tokens:
            return self._access_tokens[server_url]

        login_url = f"{server_url.rstrip('/')}/api/login"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    login_url, json={"email": username, "password": password}
                )

                if response.status_code == 200:
                    data = response.json()
                    token = data.get("access_token")
                    if token:
                        self._access_tokens[server_url] = token
                        return token

                elif response.status_code == 401:
                    # Unauthorized - credentials are invalid
                    logger.warning(
                        f"Authentication failed (401) for {username}@{server_url}. "
                        "User deleted or credentials invalid."
                    )

                    # Remove invalid credentials from database
                    if server_id:
                        logger.info(f"Removing invalid server credentials (ID: {server_id})")
                        try:
                            await db.delete_server(server_id)
                            await activity_manager.emit(
                                EventType.ERROR,
                                message=f"Server credentials removed: {username}@{server_url}",
                                details={"reason": "401 Unauthorized", "server_id": server_id},
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

    async def _process_upload(self, queue_entry: dict) -> bool:
        """Process a single upload from queue_pending_upload.

        Implements the Component 3 upload algorithm with chunked uploads.

        Args:
            queue_entry: Entry from queue_pending_upload table
                        {id, filepath, sha256, queued_at, retry_count}

        Returns:
            True if successful, False otherwise
        """
        filepath = queue_entry["filepath"]
        sha256 = queue_entry["sha256"]
        queue_id = queue_entry["id"]
        retry_count = queue_entry.get("retry_count", 0)

        self._current_file = filepath

        try:
            # Get server configuration
            server_result = await db.get_default_server()
            if not server_result:
                logger.error("No server configured, cannot upload")
                # Don't retry - wait for server configuration
                await asyncio.sleep(30)  # Wait before trying again
                return False

            server, encrypted_password = server_result
            password = decrypt_password(encrypted_password)

            # Get access token
            token = await self._get_access_token(server.url, server.username, password, server.id)
            if not token:
                # Authentication failed - wait before trying again
                await asyncio.sleep(30)
                return False

            # Check if file still exists
            file_path = Path(filepath)
            if not file_path.exists():
                # File deleted - remove from queue and files table
                logger.warning(f"File no longer exists, removing: {filepath}")
                await db.remove_from_upload_queue(queue_id)
                await db.delete_file(filepath)
                self._failed_today += 1
                return False

            # Get file stats
            stat_info = os.stat(file_path)
            file_size = stat_info.st_size

            # Upload using chunked upload protocol
            success = await self._upload_file_chunked(
                filepath=file_path,
                sha256=sha256,
                file_size=file_size,
                server_url=server.url,
                token=token,
            )

            if success:
                # Update files table - mark as completed
                await db.mark_file_uploaded(filepath)

                # Remove from queue_pending_upload
                await db.remove_from_upload_queue(queue_id)

                self._uploaded_today += 1

                # Log activity
                await activity_manager.emit(
                    EventType.UPLOAD_COMPLETE,
                    filepath=filepath,
                    message=f"Upload complete: {file_path.name}",
                    details={"sha256": sha256[:16] + "...", "server": server.name},
                )

                logger.info(f"Uploaded: {filepath} ({sha256[:16]}...)")
                return True

            return False

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Unauthorized - invalidate credentials
                logger.warning(f"401 Unauthorized during upload of {filepath}")
                self._access_tokens.pop(server.url, None)  # Clear cached token

                # Requeue for retry after authentication
                if retry_count < 3:
                    delay = 5.0 * (2.0 ** retry_count)
                    await db.retry_upload_queue_entry(queue_id, delay_seconds=delay)
                else:
                    # Max retries - remove from queue and files table
                    logger.error(f"Max retries exhausted for {filepath} (401 errors)")
                    await db.remove_from_upload_queue(queue_id)
                    await db.delete_file(filepath)
                    self._failed_today += 1

                return False

            elif e.response.status_code == 409:
                # Conflict - file already exists on server
                logger.info(f"File already on server (409 Conflict): {filepath}")
                await db.mark_file_uploaded(filepath)
                await db.remove_from_upload_queue(queue_id)
                self._uploaded_today += 1
                return True

            elif e.response.status_code >= 500:
                # Server error - retry with exponential backoff
                logger.error(f"Server error ({e.response.status_code}) uploading {filepath}")
                self._failed_today += 1

                if retry_count < 3:
                    delay = 5.0 * (2.0 ** retry_count)
                    await db.retry_upload_queue_entry(queue_id, delay_seconds=delay)
                else:
                    # Max retries - remove from queue and files table
                    logger.error(f"Max retries exhausted for {filepath}")
                    await db.remove_from_upload_queue(queue_id)
                    await db.delete_file(filepath)

                return False

            else:
                # Other HTTP error - remove from queue
                logger.error(f"HTTP error {e.response.status_code} uploading {filepath}: {e}")
                await db.remove_from_upload_queue(queue_id)
                await db.delete_file(filepath)
                self._failed_today += 1
                return False

        except (httpx.NetworkError, httpx.TimeoutException) as e:
            # Network/timeout error - retry with exponential backoff
            logger.error(f"Network/timeout error uploading {filepath}: {e}")
            self._failed_today += 1

            if retry_count < 3:
                delay = 5.0 * (2.0 ** retry_count)
                await db.retry_upload_queue_entry(queue_id, delay_seconds=delay)
            else:
                # Max retries - remove from queue and files table
                logger.error(f"Max retries exhausted for {filepath}")
                await db.remove_from_upload_queue(queue_id)
                await db.delete_file(filepath)

            return False

        except Exception as e:
            # Unexpected error - retry with exponential backoff
            logger.error(f"Unexpected error uploading {filepath}: {e}")
            self._failed_today += 1

            if retry_count < 3:
                delay = 5.0 * (2.0 ** retry_count)
                await db.retry_upload_queue_entry(queue_id, delay_seconds=delay)
            else:
                # Max retries - remove from queue and files table
                logger.error(f"Max retries exhausted for {filepath}")
                await db.remove_from_upload_queue(queue_id)
                await db.delete_file(filepath)

            return False

        finally:
            self._current_file = None

    async def _upload_file_chunked(
        self,
        filepath: Path,
        sha256: str,
        file_size: int,
        server_url: str,
        token: str,
    ) -> bool:
        """Upload file using chunked upload protocol.

        Args:
            filepath: Path to the file
            sha256: SHA256 hash of the file
            file_size: Size of the file in bytes
            server_url: Base URL of the server
            token: Access token for authentication

        Returns:
            True if upload successful
        """
        headers = {"Authorization": f"Bearer {token}"}
        chunk_size = settings.uploader_chunk_size_mb * 1024 * 1024  # Convert MB to bytes
        total_chunks = (file_size + chunk_size - 1) // chunk_size  # Ceiling division

        async with httpx.AsyncClient(timeout=float(settings.uploader_timeout_seconds)) as client:
            # Step 1: Initiate upload
            initiate_url = f"{server_url.rstrip('/')}/api/uploads/initiate"
            hostname = get_hostname()
            ip_address = get_ip_address()

            init_data = {
                "filepath": str(filepath.absolute()),
                "hostname": hostname,
                "ip_address": ip_address,
                "sha256": sha256,
                "file_size": file_size,
                "total_chunks": total_chunks,
            }

            response = await client.post(initiate_url, json=init_data, headers=headers)
            response.raise_for_status()
            upload_response = response.json()
            upload_id = upload_response["upload_id"]

            logger.info(
                f"Initiated chunked upload: {filepath.name} (upload_id={upload_id}, chunks={total_chunks})"
            )

            # Step 2: Upload chunks
            uploaded_parts = []
            with open(filepath, "rb") as f:
                for chunk_num in range(total_chunks):
                    chunk_data = f.read(chunk_size)

                    chunk_url = f"{server_url.rstrip('/')}/api/uploads/{upload_id}/chunk/{chunk_num}"
                    chunk_response = await client.put(
                        chunk_url,
                        content=chunk_data,
                        headers={**headers, "Content-Type": "application/octet-stream"},
                    )
                    chunk_response.raise_for_status()

                    chunk_result = chunk_response.json()
                    uploaded_parts.append(
                        {"chunk_num": chunk_num, "etag": chunk_result.get("etag", "")}
                    )

                    logger.debug(
                        f"Uploaded chunk {chunk_num + 1}/{total_chunks} for {filepath.name}"
                    )

            # Step 3: Complete upload
            complete_url = f"{server_url.rstrip('/')}/api/uploads/{upload_id}/complete"
            complete_data = {"parts": uploaded_parts}
            complete_response = await client.post(complete_url, json=complete_data, headers=headers)
            complete_response.raise_for_status()

            logger.info(f"Completed chunked upload: {filepath.name} ({sha256[:16]}...)")
            return True

    async def _process_deletion(self, deletion_entry: dict) -> bool:
        """Process a deletion notification from queue_pending_deletion.

        Args:
            deletion_entry: Entry from queue_pending_deletion table
                           {id, filepath, sha256, deleted_at, retry_count}

        Returns:
            True if successful, False otherwise
        """
        filepath = deletion_entry["filepath"]
        sha256 = deletion_entry.get("sha256")
        queue_id = deletion_entry["id"]
        retry_count = deletion_entry.get("retry_count", 0)

        try:
            # Get server configuration
            server_result = await db.get_default_server()
            if not server_result:
                logger.error("No server configured, cannot send deletion notification")
                await asyncio.sleep(30)
                return False

            server, encrypted_password = server_result
            password = decrypt_password(encrypted_password)

            # Get access token
            token = await self._get_access_token(server.url, server.username, password, server.id)
            if not token:
                await asyncio.sleep(30)
                return False

            # Send deletion notification
            headers = {"Authorization": f"Bearer {token}"}
            delete_url = f"{server.url.rstrip('/')}/api/files/{sha256}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(delete_url, headers=headers)

                if response.status_code == 200:
                    # Success - remove from queue
                    await db.remove_from_deletion_queue(queue_id)
                    logger.info(f"Deletion notified: {filepath}")

                    await activity_manager.emit(
                        EventType.FILE_DELETED,
                        filepath=filepath,
                        message=f"Deletion notified: {Path(filepath).name}",
                        details={"sha256": sha256[:16] + "..." if sha256 else "unknown"},
                    )

                    return True

                elif response.status_code == 404:
                    # File doesn't exist on server anyway - remove from queue
                    logger.info(f"File not found on server (deletion OK): {filepath}")
                    await db.remove_from_deletion_queue(queue_id)
                    return True

                elif response.status_code == 401:
                    # Unauthorized - invalidate credentials and retry
                    logger.warning(f"401 Unauthorized during deletion notification of {filepath}")
                    self._access_tokens.pop(server.url, None)

                    if retry_count < 3:
                        delay = 5.0 * (2.0 ** retry_count)
                        await db.retry_deletion_queue_entry(queue_id, delay_seconds=delay)
                    else:
                        # Max retries - just remove from queue
                        logger.error(f"Max retries exhausted for deletion notification: {filepath}")
                        await db.remove_from_deletion_queue(queue_id)

                    return False

                else:
                    # Other error - retry
                    logger.error(f"Deletion notification failed ({response.status_code}): {filepath}")

                    if retry_count < 3:
                        delay = 5.0 * (2.0 ** retry_count)
                        await db.retry_deletion_queue_entry(queue_id, delay_seconds=delay)
                    else:
                        # Max retries - just remove from queue
                        logger.error(f"Max retries exhausted for deletion notification: {filepath}")
                        await db.remove_from_deletion_queue(queue_id)

                    return False

        except Exception as e:
            logger.error(f"Error processing deletion notification for {filepath}: {e}")

            if retry_count < 3:
                delay = 5.0 * (2.0 ** retry_count)
                await db.retry_deletion_queue_entry(queue_id, delay_seconds=delay)
            else:
                # Max retries - just remove from queue
                logger.error(f"Max retries exhausted for deletion notification: {filepath}")
                await db.remove_from_deletion_queue(queue_id)

            return False

    def reset_daily_counters(self) -> None:
        """Reset daily counters (called at midnight)."""
        self._uploaded_today = 0
        self._failed_today = 0

    async def get_pending_counts(self) -> dict[str, int]:
        """Get count of pending uploads and deletions.

        Returns:
            Dictionary with queue counts
        """
        counts = await db.get_queue_counts()
        return {
            "pending_uploads": counts.get("queue_pending_upload", 0),
            "pending_deletions": counts.get("queue_pending_deletion", 0),
        }


# Global uploader instance
uploader_v3 = UploaderV3()
