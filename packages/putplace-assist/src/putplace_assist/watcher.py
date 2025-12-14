"""File system watcher for putplace-assist.

Monitors registered paths for file changes using watchdog.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import settings
from .database import db
from .models import EventType
from .scanner import matches_exclude_pattern, get_file_metadata

logger = logging.getLogger(__name__)


class FileChangeHandler(FileSystemEventHandler):
    """Handler for file system events."""

    def __init__(
        self,
        path_id: int,
        base_path: Path,
        exclude_patterns: list[str],
        event_callback: Callable[[FileSystemEvent], None],
    ):
        """Initialize handler.

        Args:
            path_id: ID of the registered path
            base_path: Base path being watched
            exclude_patterns: Patterns to exclude
            event_callback: Callback for file events
        """
        super().__init__()
        self.path_id = path_id
        self.base_path = base_path
        self.exclude_patterns = exclude_patterns
        self.event_callback = event_callback

    def _should_process(self, event: FileSystemEvent) -> bool:
        """Check if event should be processed."""
        # Ignore directory events
        if event.is_directory:
            return False

        # Check exclude patterns
        path = Path(event.src_path)
        if matches_exclude_pattern(path, self.base_path, self.exclude_patterns):
            return False

        return True

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation."""
        if self._should_process(event):
            self.event_callback(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification."""
        if self._should_process(event):
            self.event_callback(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion."""
        if self._should_process(event):
            self.event_callback(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename."""
        if self._should_process(event):
            self.event_callback(event)


class FileWatcher:
    """Watches registered paths for file changes."""

    def __init__(self, debounce_seconds: Optional[float] = None):
        """Initialize watcher.

        Args:
            debounce_seconds: Debounce delay for file events
        """
        self.debounce_seconds = debounce_seconds or settings.watcher_debounce_seconds
        self._observer: Optional[Observer] = None
        self._handlers: dict[int, FileChangeHandler] = {}
        self._watches: dict[int, Any] = {}  # Store watch objects for unscheduling
        self._pending_events: dict[str, asyncio.Task] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._process_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the file watcher."""
        if self._running:
            logger.warning("Watcher already running")
            return

        logger.info("Starting file watcher...")
        self._running = True

        # Create observer
        self._observer = Observer()

        # Get all enabled paths
        paths = await db.get_all_paths(enabled_only=True)

        # Get all exclude patterns
        excludes = await db.get_all_excludes()
        exclude_patterns = [e.pattern for e in excludes]

        # Add watches for each path
        for path_response in paths:
            await self._add_watch(path_response.id, path_response.path, exclude_patterns)

        # Start observer
        self._observer.start()

        # Start event processing task
        self._process_task = asyncio.create_task(self._process_events())

        logger.info(f"File watcher started, watching {len(paths)} paths")

    async def stop(self) -> None:
        """Stop the file watcher."""
        if not self._running:
            return

        logger.info("Stopping file watcher...")
        self._running = False

        # Cancel pending debounce tasks
        for task in self._pending_events.values():
            task.cancel()
        self._pending_events.clear()

        # Stop observer
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        # Cancel event processing task
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
            self._process_task = None

        self._handlers.clear()
        self._watches.clear()
        logger.info("File watcher stopped")

    async def _add_watch(
        self, path_id: int, path_str: str, exclude_patterns: list[str]
    ) -> bool:
        """Add a watch for a path.

        Returns:
            True if watch was added successfully
        """
        path = Path(path_str)

        if not path.exists():
            logger.warning(f"Cannot watch non-existent path: {path}")
            return False

        if not path.is_dir():
            logger.warning(f"Cannot watch non-directory: {path}")
            return False

        # Create handler
        handler = FileChangeHandler(
            path_id=path_id,
            base_path=path,
            exclude_patterns=exclude_patterns,
            event_callback=lambda e: self._queue_event(path_id, e),
        )

        # Schedule watch
        try:
            watch = self._observer.schedule(handler, str(path), recursive=True)
            self._handlers[path_id] = handler
            self._watches[path_id] = watch
            logger.info(f"Added watch for path {path_id}: {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to add watch for {path}: {e}")
            return False

    def _queue_event(self, path_id: int, event: FileSystemEvent) -> None:
        """Queue an event for processing (called from watchdog thread)."""
        try:
            # Use asyncio.run_coroutine_threadsafe to add to queue from another thread
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(
                self._debounce_event(path_id, event), loop
            )
        except RuntimeError:
            # No event loop running
            pass

    async def _debounce_event(self, path_id: int, event: FileSystemEvent) -> None:
        """Debounce file events to avoid processing rapid changes."""
        key = event.src_path

        # Cancel existing debounce task for this file
        if key in self._pending_events:
            self._pending_events[key].cancel()

        # Create new debounce task
        async def delayed_process():
            await asyncio.sleep(self.debounce_seconds)
            if key in self._pending_events:
                del self._pending_events[key]
            await self._event_queue.put((path_id, event))

        self._pending_events[key] = asyncio.create_task(delayed_process())

    async def _process_events(self) -> None:
        """Process events from the queue."""
        while self._running:
            try:
                path_id, event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=1.0
                )
                await self._handle_event(path_id, event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing event: {e}")

    async def _handle_event(self, path_id: int, event: FileSystemEvent) -> None:
        """Handle a single file system event."""
        filepath = Path(event.src_path)
        event_type = event.event_type

        logger.debug(f"Processing event: {event_type} for {filepath}")

        try:
            if event_type == "deleted":
                await self._handle_deleted(path_id, filepath)
            elif event_type in ("created", "modified"):
                await self._handle_created_modified(path_id, filepath)
            elif event_type == "moved":
                # Handle as delete + create
                await self._handle_deleted(path_id, filepath)
                if hasattr(event, "dest_path"):
                    dest = Path(event.dest_path)
                    await self._handle_created_modified(path_id, dest)
        except Exception as e:
            logger.error(f"Error handling {event_type} for {filepath}: {e}")
            await db.log_activity(
                EventType.ERROR,
                path_id=path_id,
                message=f"Error handling {event_type}: {e}",
                details={"filepath": str(filepath)},
            )

    async def _handle_deleted(self, path_id: int, filepath: Path) -> None:
        """Handle file deletion."""
        # Find file in database
        files, _ = await db.get_files(path_prefix=str(filepath), limit=1)
        if not files:
            return

        file_info = files[0]

        # Log deletion
        await db.log_activity(
            EventType.FILE_DELETED,
            file_id=file_info.id,
            path_id=path_id,
            message=f"File deleted: {filepath.name}",
            details={"sha256": file_info.sha256},
        )

        # Delete from database
        await db.delete_file(file_info.id)
        logger.info(f"Deleted file from tracking: {filepath}")

    async def _handle_created_modified(self, path_id: int, filepath: Path) -> None:
        """Handle file creation or modification."""
        if not filepath.exists():
            return

        if not filepath.is_file():
            return

        # Scan the file
        scanned = await get_file_metadata(filepath)
        if scanned is None:
            logger.warning(f"Failed to scan file: {filepath}")
            return

        # Check if file exists in database
        existing_files, _ = await db.get_files(path_prefix=str(filepath), limit=1)
        is_new = len(existing_files) == 0
        is_changed = False

        if not is_new:
            existing = existing_files[0]
            is_changed = existing.sha256 != scanned.sha256

        # Store in database
        file_id = await db.upsert_file(
            filepath=str(scanned.filepath),
            sha256=scanned.sha256,
            file_size=scanned.file_size,
            registered_path_id=path_id,
            file_mode=scanned.file_mode,
            file_uid=scanned.file_uid,
            file_gid=scanned.file_gid,
            file_mtime=scanned.file_mtime,
            file_atime=scanned.file_atime,
            file_ctime=scanned.file_ctime,
        )

        # Log events
        if is_new:
            await db.log_activity(
                EventType.FILE_DISCOVERED,
                file_id=file_id,
                path_id=path_id,
                message=f"New file: {filepath.name}",
                details={"sha256": scanned.sha256, "size": scanned.file_size},
            )
            logger.info(f"New file discovered: {filepath}")
        elif is_changed:
            await db.log_activity(
                EventType.FILE_CHANGED,
                file_id=file_id,
                path_id=path_id,
                message=f"File changed: {filepath.name}",
                details={"sha256": scanned.sha256, "size": scanned.file_size},
            )
            logger.info(f"File changed: {filepath}")

    async def add_path(self, path_id: int, path_str: str) -> bool:
        """Add a new path to watch dynamically.

        Args:
            path_id: ID of the registered path
            path_str: Path to watch

        Returns:
            True if watch was added successfully
        """
        if not self._running or not self._observer:
            return False

        # Get current exclude patterns
        excludes = await db.get_all_excludes()
        exclude_patterns = [e.pattern for e in excludes]

        return await self._add_watch(path_id, path_str, exclude_patterns)

    async def remove_path(self, path_id: int) -> bool:
        """Remove a path from watching.

        Args:
            path_id: ID of the registered path

        Returns:
            True if watch was removed
        """
        if path_id not in self._handlers:
            return False

        # Unschedule using the watch object, not the handler
        if self._observer and path_id in self._watches:
            watch = self._watches[path_id]
            self._observer.unschedule(watch)
            del self._watches[path_id]

        del self._handlers[path_id]
        logger.info(f"Removed watch for path {path_id}")
        return True

    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running

    @property
    def watched_paths(self) -> list[int]:
        """Get list of watched path IDs."""
        return list(self._handlers.keys())


# Global watcher instance
watcher = FileWatcher()
