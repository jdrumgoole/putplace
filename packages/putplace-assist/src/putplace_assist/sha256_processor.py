"""Background SHA256 processor for putplace-assist.

Component 2 of the 3-component queue-based architecture.

This module provides a background task that:
1. Processes files from queue_pending_checksum (FIFO)
2. Calculates SHA256 checksums for each file
3. Updates files table with SHA256 and marks status='ready_for_upload'
4. Enqueues files to queue_pending_upload
5. Implements retry logic with exponential backoff (3 retries)
6. Removes files from database after all retries exhausted
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional

from .activity import activity_manager
from .config import settings
from .database import db
from .models import EventType

logger = logging.getLogger(__name__)


class Sha256Processor:
    """Background processor for calculating SHA256 checksums."""

    def __init__(self):
        """Initialize the processor."""
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._current_file: Optional[str] = None
        self._processed_today = 0
        self._failed_today = 0

    @property
    def is_running(self) -> bool:
        """Check if the processor is running."""
        return self._running

    @property
    def current_file(self) -> Optional[str]:
        """Get the file currently being processed."""
        return self._current_file

    @property
    def processed_today(self) -> int:
        """Get the count of files processed today."""
        return self._processed_today

    @property
    def failed_today(self) -> int:
        """Get the count of failed processing attempts today."""
        return self._failed_today

    async def start(self) -> None:
        """Start the background processor."""
        if self._running:
            logger.warning("SHA256 processor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("SHA256 processor started")

    async def stop(self) -> None:
        """Stop the background processor."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("SHA256 processor stopped")

    async def _process_loop(self) -> None:
        """Main processing loop - processes queue_pending_checksum (FIFO)."""
        while self._running:
            try:
                # Dequeue batch from queue_pending_checksum (FIFO)
                queue_entries = await db.dequeue_for_checksum(
                    limit=settings.sha256_batch_size
                )

                if queue_entries:
                    logger.debug(f"Processing batch of {len(queue_entries)} files from checksum queue")

                    for queue_entry in queue_entries:
                        if not self._running:
                            break

                        await self._process_queue_entry(queue_entry)

                else:
                    # No entries to process, wait before checking again
                    await asyncio.sleep(settings.sha256_batch_delay_seconds * 5)

                # Delay between batches
                await asyncio.sleep(settings.sha256_batch_delay_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in SHA256 processor loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    async def _process_queue_entry(self, queue_entry: dict) -> bool:
        """Process a single entry from queue_pending_checksum.

        Implements the Component 2 algorithm:
        1. Check if file exists
        2. Calculate SHA256 hash
        3. Check if checksum changed
        4. Update files table with SHA256 and status='ready_for_upload'
        5. Enqueue to queue_pending_upload
        6. Remove from queue_pending_checksum
        7. Implement retry logic with exponential backoff

        Args:
            queue_entry: Entry from queue_pending_checksum table
                        {id, filepath, reason, queued_at, retry_count}

        Returns:
            True if successful, False otherwise
        """
        filepath = queue_entry["filepath"]
        queue_id = queue_entry["id"]
        retry_count = queue_entry.get("retry_count", 0)

        self._current_file = filepath

        try:
            # Check if file still exists
            file_path = Path(filepath)
            if not file_path.exists():
                # File deleted between scan and checksum - remove from queue and files table
                logger.warning(f"File no longer exists, removing: {filepath}")
                await db.remove_from_checksum_queue(queue_id)
                await db.delete_file(filepath)
                self._failed_today += 1
                return False

            # Get file metadata from files table
            file_record = await db.get_file(filepath)
            if not file_record:
                # File not in files table (shouldn't happen, but handle gracefully)
                logger.error(f"File not found in files table: {filepath}")
                await db.remove_from_checksum_queue(queue_id)
                self._failed_today += 1
                return False

            # Calculate SHA256 hash
            sha256_hash = await self._calculate_sha256(file_path)

            # Check if checksum changed
            existing_sha256 = file_record.get("sha256")

            if existing_sha256 == sha256_hash:
                # Checksum unchanged, no upload needed
                logger.debug(f"File unchanged (same SHA256): {filepath}")
                await db.upsert_file(
                    filepath=filepath,
                    file_size=file_record["file_size"],
                    file_mtime=file_record["file_mtime"],
                    file_mode=file_record.get("file_mode"),
                    file_uid=file_record.get("file_uid"),
                    file_gid=file_record.get("file_gid"),
                    file_atime=file_record.get("file_atime"),
                    file_ctime=file_record.get("file_ctime"),
                    sha256=sha256_hash,
                    status="unchanged",  # Mark as unchanged since SHA256 matches
                )
                await db.remove_from_checksum_queue(queue_id)
                self._processed_today += 1
                return True

            # New or changed checksum - update files table and queue for upload
            await db.update_file_sha256(filepath, sha256_hash, status="ready_for_upload")

            # Enqueue to queue_pending_upload
            await db.enqueue_for_upload(filepath, sha256_hash)

            # Remove from queue_pending_checksum
            await db.remove_from_checksum_queue(queue_id)

            self._processed_today += 1

            # Log activity
            await activity_manager.emit(
                EventType.SHA256_COMPLETE,
                filepath=filepath,
                message=f"SHA256 calculated: {file_path.name}",
                details={
                    "sha256": sha256_hash[:16] + "...",
                    "reason": queue_entry.get("reason", "unknown"),
                },
            )

            logger.debug(f"Processed: {filepath} -> {sha256_hash[:16]}... (queued for upload)")
            return True

        except FileNotFoundError:
            # File not found - remove from queue and files table
            logger.warning(f"File not found during SHA256 calculation: {filepath}")
            await db.remove_from_checksum_queue(queue_id)
            await db.delete_file(filepath)
            self._failed_today += 1
            return False

        except PermissionError:
            # Permission denied - retry with exponential backoff
            logger.warning(f"Permission denied reading file: {filepath} (retry {retry_count}/3)")
            self._failed_today += 1

            await activity_manager.emit(
                EventType.SHA256_FAILED,
                filepath=filepath,
                message=f"Permission denied: {Path(filepath).name} (retry {retry_count}/3)",
            )

            if retry_count < 3:
                # Retry with exponential backoff
                delay = 5.0 * (2.0 ** retry_count)  # 5s, 10s, 20s
                await db.retry_checksum_queue_entry(queue_id, delay_seconds=delay)
                logger.debug(f"Retrying {filepath} in {delay}s")
            else:
                # Max retries exhausted - remove from queue and files table
                logger.error(f"Max retries exhausted for {filepath}, removing from database")
                await db.remove_from_checksum_queue(queue_id)
                await db.delete_file(filepath)

            return False

        except (IOError, OSError) as e:
            # I/O error - retry with exponential backoff
            logger.error(f"I/O error processing {filepath}: {e} (retry {retry_count}/3)")
            self._failed_today += 1

            await activity_manager.emit(
                EventType.SHA256_FAILED,
                filepath=filepath,
                message=f"I/O error: {Path(filepath).name} (retry {retry_count}/3)",
                details={"error": str(e)},
            )

            if retry_count < 3:
                # Retry with exponential backoff
                delay = 5.0 * (2.0 ** retry_count)  # 5s, 10s, 20s
                await db.retry_checksum_queue_entry(queue_id, delay_seconds=delay)
                logger.debug(f"Retrying {filepath} in {delay}s")
            else:
                # Max retries exhausted - remove from queue and files table
                logger.error(f"Max retries exhausted for {filepath}, removing from database")
                await db.remove_from_checksum_queue(queue_id)
                await db.delete_file(filepath)

            return False

        except Exception as e:
            # Unexpected error - retry with exponential backoff
            logger.error(f"Unexpected error processing {filepath}: {e} (retry {retry_count}/3)")
            self._failed_today += 1

            await activity_manager.emit(
                EventType.SHA256_FAILED,
                filepath=filepath,
                message=f"SHA256 failed: {Path(filepath).name} (retry {retry_count}/3)",
                details={"error": str(e)},
            )

            if retry_count < 3:
                # Retry with exponential backoff
                delay = 5.0 * (2.0 ** retry_count)  # 5s, 10s, 20s
                await db.retry_checksum_queue_entry(queue_id, delay_seconds=delay)
                logger.debug(f"Retrying {filepath} in {delay}s")
            else:
                # Max retries exhausted - remove from queue and files table
                logger.error(f"Max retries exhausted for {filepath}, removing from database")
                await db.remove_from_checksum_queue(queue_id)
                await db.delete_file(filepath)

            return False

        finally:
            self._current_file = None

    async def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash with rate limiting.

        Reads file in chunks with delays to avoid CPU saturation.

        Args:
            file_path: Path to the file

        Returns:
            Hexadecimal SHA256 hash string
        """
        sha256_hash = hashlib.sha256()
        chunk_size = settings.sha256_chunk_size
        chunk_delay_ms = settings.sha256_chunk_delay_ms

        # Run file reading in thread pool to avoid blocking
        loop = asyncio.get_event_loop()

        def read_file_chunks():
            """Generator that reads file in chunks."""
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        # Process chunks with rate limiting
        for chunk in await loop.run_in_executor(None, lambda: list(read_file_chunks())):
            sha256_hash.update(chunk)

            # Rate limit between chunks
            if chunk_delay_ms > 0:
                await asyncio.sleep(chunk_delay_ms / 1000.0)

        return sha256_hash.hexdigest()

    async def get_pending_count(self) -> int:
        """Get the count of entries waiting to be processed in queue_pending_checksum.

        Returns:
            Number of entries in checksum queue
        """
        counts = await db.get_queue_counts()
        return counts.get("queue_pending_checksum", 0)

    def reset_daily_counters(self) -> None:
        """Reset the daily counters (called at midnight)."""
        self._processed_today = 0
        self._failed_today = 0


# Global processor instance
sha256_processor = Sha256Processor()
