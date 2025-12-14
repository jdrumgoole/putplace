"""File scanner for putplace-assist.

Scans directories for files and logs metadata to monthly filelog tables.
SHA256 calculation is done separately by the background processor.
"""

import asyncio
import fnmatch
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .activity import activity_manager
from .database import db
from .models import EventType

logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Metadata collected from a file."""

    filepath: Path
    file_size: int
    file_mode: int
    file_uid: int
    file_gid: int
    file_mtime: float
    file_atime: float
    file_ctime: float


@dataclass
class ScanProgress:
    """Progress information for a scan."""

    path_id: int
    path: str
    total_files: int
    scanned_files: int
    logged_files: int  # Files that were actually logged (new or changed)
    skipped_files: int  # Files skipped (unchanged)
    error_count: int
    current_file: Optional[str] = None


@dataclass
class ScanResult:
    """Result of a directory scan."""

    path_id: int
    path: str
    total_files: int
    logged_files: int
    skipped_files: int
    error_count: int
    errors: list[tuple[str, str]]  # List of (filepath, error_message)


def get_file_stats(filepath: Path) -> Optional[dict]:
    """Get file stat information.

    Args:
        filepath: Path to the file

    Returns:
        Dictionary with stat information or None if stat fails
    """
    try:
        stat_info = os.stat(filepath)
        return {
            "file_size": stat_info.st_size,
            "file_mode": stat_info.st_mode,
            "file_uid": stat_info.st_uid,
            "file_gid": stat_info.st_gid,
            "file_mtime": stat_info.st_mtime,
            "file_atime": stat_info.st_atime,
            "file_ctime": stat_info.st_ctime,
        }
    except (IOError, OSError) as e:
        logger.warning(f"Cannot stat {filepath}: {e}")
        return None


def matches_exclude_pattern(path: Path, base_path: Path, patterns: list[str]) -> bool:
    """Check if a path matches any exclude pattern.

    Args:
        path: Path to check
        base_path: Base path for relative matching
        patterns: List of exclude patterns

    Returns:
        True if path matches any pattern
    """
    if not patterns:
        return False

    try:
        relative_path = path.relative_to(base_path)
    except ValueError:
        # Path is not relative to base_path
        return False

    relative_str = str(relative_path)
    path_parts = relative_path.parts

    for pattern in patterns:
        # Check if pattern matches the full relative path
        if relative_str == pattern:
            return True

        # Check if pattern matches any part of the path
        if pattern in path_parts:
            return True

        # Check for wildcard patterns
        if "*" in pattern:
            if fnmatch.fnmatch(relative_str, pattern):
                return True

            # Check each part for pattern match
            for part in path_parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

    return False


def collect_files(
    directory: Path, recursive: bool, exclude_patterns: list[str]
) -> list[Path]:
    """Collect all files in a directory.

    Args:
        directory: Directory to scan
        recursive: Whether to scan recursively
        exclude_patterns: Patterns to exclude

    Returns:
        List of file paths
    """
    files = []

    if recursive:
        iterator = directory.rglob("*")
    else:
        iterator = directory.glob("*")

    for filepath in iterator:
        if not filepath.is_file():
            continue

        if matches_exclude_pattern(filepath, directory, exclude_patterns):
            logger.debug(f"Excluded: {filepath}")
            continue

        files.append(filepath)

    return files


async def get_file_metadata(filepath: Path) -> Optional[FileMetadata]:
    """Get metadata for a single file.

    Args:
        filepath: Path to the file

    Returns:
        FileMetadata or None if file cannot be read
    """
    stats = await asyncio.to_thread(get_file_stats, filepath)
    if stats is None:
        return None

    return FileMetadata(
        filepath=filepath,
        file_size=stats["file_size"],
        file_mode=stats["file_mode"],
        file_uid=stats["file_uid"],
        file_gid=stats["file_gid"],
        file_mtime=stats["file_mtime"],
        file_atime=stats["file_atime"],
        file_ctime=stats["file_ctime"],
    )


async def scan_directory(
    path_id: int,
    directory: Path,
    recursive: bool = True,
    exclude_patterns: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[ScanProgress], None]] = None,
    concurrency: int = 8,
) -> ScanResult:
    """Scan a directory and log file metadata to the monthly filelog table.

    This does NOT calculate SHA256 checksums - that is done by the
    background SHA256 processor.

    Args:
        path_id: ID of the registered path
        directory: Directory to scan
        recursive: Whether to scan recursively
        exclude_patterns: Patterns to exclude
        progress_callback: Optional callback for progress updates
        concurrency: Number of concurrent file operations

    Returns:
        ScanResult with scan statistics
    """
    exclude_patterns = exclude_patterns or []
    errors: list[tuple[str, str]] = []
    logged_files = 0
    skipped_files = 0
    scanned_files = 0

    # Log scan start
    await activity_manager.emit(
        EventType.SCAN_STARTED,
        path_id=path_id,
        message=f"Started scanning {directory}",
        details={"recursive": recursive, "exclude_patterns": exclude_patterns},
    )

    # Collect files (this is I/O bound but not async, run in thread)
    logger.info(f"Collecting files from {directory}...")
    files = await asyncio.to_thread(collect_files, directory, recursive, exclude_patterns)
    total_files = len(files)

    logger.info(f"Found {total_files} files to scan")

    # Create progress tracker
    progress = ScanProgress(
        path_id=path_id,
        path=str(directory),
        total_files=total_files,
        scanned_files=0,
        logged_files=0,
        skipped_files=0,
        error_count=0,
    )

    if progress_callback:
        progress_callback(progress)

    # Process files with limited concurrency using semaphore
    semaphore = asyncio.Semaphore(concurrency)

    async def process_file(filepath: Path) -> tuple[str, bool, Optional[str]]:
        """Process a single file. Returns (filepath, was_logged, error_message)."""
        async with semaphore:
            try:
                metadata = await get_file_metadata(filepath)
                if metadata is None:
                    return str(filepath), False, "Could not read file stats"

                # Log to monthly filelog table
                # This will return None if the file hasn't changed (same ctime/mtime)
                log_id = await db.log_file(
                    filepath=str(metadata.filepath),
                    ctime=metadata.file_ctime,
                    mtime=metadata.file_mtime,
                    atime=metadata.file_atime,
                    file_size=metadata.file_size,
                    permissions=metadata.file_mode,
                    uid=metadata.file_uid,
                    gid=metadata.file_gid,
                )

                was_logged = log_id is not None

                if was_logged:
                    # Emit activity for new/changed file
                    await activity_manager.emit(
                        EventType.FILE_DISCOVERED,
                        filepath=str(filepath),
                        path_id=path_id,
                        message=f"File logged: {filepath.name}",
                        details={"size": metadata.file_size, "mtime": metadata.file_mtime},
                    )

                return str(filepath), was_logged, None

            except Exception as e:
                logger.error(f"Error processing {filepath}: {e}")
                return str(filepath), False, str(e)

    # Process all files concurrently
    tasks = [process_file(f) for f in files]

    for coro in asyncio.as_completed(tasks):
        filepath, was_logged, error = await coro
        scanned_files += 1

        if error:
            errors.append((filepath, error))
            progress.error_count += 1
        elif was_logged:
            logged_files += 1
            progress.logged_files += 1
        else:
            skipped_files += 1
            progress.skipped_files += 1

        progress.scanned_files = scanned_files
        progress.current_file = filepath

        if progress_callback:
            progress_callback(progress)

    # Update path last_scanned_at
    await db.update_path_scanned(path_id)

    # Log scan complete
    await activity_manager.emit(
        EventType.SCAN_COMPLETE,
        path_id=path_id,
        message=f"Completed scanning {directory}",
        details={
            "total_files": total_files,
            "logged_files": logged_files,
            "skipped_files": skipped_files,
            "errors": len(errors),
        },
    )

    return ScanResult(
        path_id=path_id,
        path=str(directory),
        total_files=total_files,
        logged_files=logged_files,
        skipped_files=skipped_files,
        error_count=len(errors),
        errors=errors,
    )


async def scan_all_paths(
    progress_callback: Optional[Callable[[ScanProgress], None]] = None,
    concurrency: int = 8,
) -> list[ScanResult]:
    """Scan all registered and enabled paths.

    Args:
        progress_callback: Optional callback for progress updates
        concurrency: Number of concurrent file operations per path

    Returns:
        List of ScanResult for each path
    """
    # Get all enabled paths
    paths = await db.get_all_paths(enabled_only=True)

    # Get all exclude patterns
    excludes = await db.get_all_excludes()
    exclude_patterns = [e.pattern for e in excludes]

    results = []

    for path_response in paths:
        path = Path(path_response.path)

        if not path.exists():
            logger.warning(f"Path does not exist: {path}")
            await activity_manager.emit(
                EventType.ERROR,
                path_id=path_response.id,
                message=f"Path does not exist: {path}",
            )
            continue

        if not path.is_dir():
            logger.warning(f"Path is not a directory: {path}")
            await activity_manager.emit(
                EventType.ERROR,
                path_id=path_response.id,
                message=f"Path is not a directory: {path}",
            )
            continue

        result = await scan_directory(
            path_id=path_response.id,
            directory=path,
            recursive=path_response.recursive,
            exclude_patterns=exclude_patterns,
            progress_callback=progress_callback,
            concurrency=concurrency,
        )

        results.append(result)

    return results
