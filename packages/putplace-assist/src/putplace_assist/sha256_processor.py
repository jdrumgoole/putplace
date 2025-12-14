"""Background SHA256 processor for putplace-assist.

This module provides a background task that:
1. Reads unprocessed entries from monthly filelog tables
2. Calculates SHA256 checksums with rate limiting
3. Stores results in the filelog_sha256 table
4. Cleans up old monthly tables once fully processed
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional

from .activity import activity_manager
from .config import settings
from .database import db
from .models import EventType, FileLogEntry

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
        """Main processing loop."""
        while self._running:
            try:
                # Get batch of unprocessed entries
                entries = await db.get_unprocessed_entries(
                    limit=settings.sha256_batch_size
                )

                if entries:
                    logger.debug(f"Processing batch of {len(entries)} files")

                    for entry in entries:
                        if not self._running:
                            break

                        await self._process_entry(entry)

                    # Clean up old tables periodically
                    await self._cleanup_old_tables()

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

    async def _process_entry(self, entry: FileLogEntry) -> bool:
        """Process a single filelog entry.

        Args:
            entry: The filelog entry to process

        Returns:
            True if successful, False otherwise
        """
        self._current_file = entry.filepath

        try:
            # Check if file still exists
            file_path = Path(entry.filepath)
            if not file_path.exists():
                logger.warning(f"File no longer exists, skipping: {entry.filepath}")
                self._failed_today += 1
                # We don't add to sha256 table - entry remains unprocessed
                # but will be cleaned up when monthly table is deleted
                return False

            # Calculate SHA256 with rate limiting
            sha256_hash = await self._calculate_sha256(file_path)

            # Add to filelog_sha256
            await db.add_sha256_entry(
                filepath=entry.filepath,
                ctime=entry.ctime,
                mtime=entry.mtime,
                atime=entry.atime,
                file_size=entry.file_size,
                sha256=sha256_hash,
                source_table=entry.source_table,
                source_id=entry.id,
                permissions=entry.permissions,
                uid=entry.uid,
                gid=entry.gid,
            )

            self._processed_today += 1

            # Log activity
            await activity_manager.emit(
                EventType.SHA256_COMPLETE,
                filepath=entry.filepath,
                message=f"SHA256 calculated: {file_path.name}",
                details={"sha256": sha256_hash[:16] + "..."},
            )

            logger.debug(f"Processed: {entry.filepath} -> {sha256_hash[:16]}...")
            return True

        except FileNotFoundError:
            logger.warning(f"File not found during SHA256 calculation: {entry.filepath}")
            self._failed_today += 1
            return False

        except PermissionError:
            logger.warning(f"Permission denied reading file: {entry.filepath}")
            self._failed_today += 1

            await activity_manager.emit(
                EventType.SHA256_FAILED,
                filepath=entry.filepath,
                message=f"Permission denied: {Path(entry.filepath).name}",
            )
            return False

        except Exception as e:
            logger.error(f"Error processing {entry.filepath}: {e}")
            self._failed_today += 1

            await activity_manager.emit(
                EventType.SHA256_FAILED,
                filepath=entry.filepath,
                message=f"SHA256 failed: {Path(entry.filepath).name}",
                details={"error": str(e)},
            )
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

    async def _cleanup_old_tables(self) -> None:
        """Clean up old monthly tables that are fully processed."""
        try:
            deleted = await db.cleanup_old_tables()

            for table_name in deleted:
                await activity_manager.emit(
                    EventType.TABLE_CLEANUP,
                    message=f"Deleted old table: {table_name}",
                    details={"table_name": table_name},
                )

        except Exception as e:
            logger.error(f"Error cleaning up old tables: {e}")

    async def get_pending_count(self) -> int:
        """Get the count of entries waiting to be processed.

        Returns:
            Number of unprocessed entries
        """
        entries = await db.get_unprocessed_entries(limit=10000)
        return len(entries)

    def reset_daily_counters(self) -> None:
        """Reset the daily counters (called at midnight)."""
        self._processed_today = 0
        self._failed_today = 0


# Global processor instance
sha256_processor = Sha256Processor()
