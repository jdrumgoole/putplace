"""SQLite database operations for putplace-assist."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from .config import settings
from .models import (
    ActivityEvent,
    EventType,
    ExcludeResponse,
    FileLogEntry,
    FileLogSha256Entry,
    FileStats,
    PathResponse,
    ServerResponse,
)

logger = logging.getLogger(__name__)


def get_current_month_table() -> str:
    """Get the current month's filelog table name.

    Returns:
        Table name in format 'filelog_YYYYMM'
    """
    return f"filelog_{datetime.utcnow().strftime('%Y%m')}"


def get_month_table_for_date(dt: datetime) -> str:
    """Get the filelog table name for a specific date.

    Args:
        dt: The datetime to get the table name for

    Returns:
        Table name in format 'filelog_YYYYMM'
    """
    return f"filelog_{dt.strftime('%Y%m')}"


# SQL for creating base tables (non-monthly)
CREATE_BASE_TABLES_SQL = """
-- Registered paths to watch
CREATE TABLE IF NOT EXISTS registered_paths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    recursive INTEGER DEFAULT 1,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_scanned_at TEXT
);

-- Exclude patterns
CREATE TABLE IF NOT EXISTS exclude_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Server configuration
CREATE TABLE IF NOT EXISTS server_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    username TEXT,
    password_encrypted TEXT,
    is_default INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Permanent SHA256 table - processed file records
CREATE TABLE IF NOT EXISTS filelog_sha256 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL,
    ctime REAL NOT NULL,
    mtime REAL NOT NULL,
    atime REAL,
    file_size INTEGER NOT NULL,
    permissions INTEGER,
    uid INTEGER,
    gid INTEGER,
    sha256 TEXT NOT NULL,
    upload_status TEXT,
    source_table TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    processed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sha256_path ON filelog_sha256(filepath);
CREATE INDEX IF NOT EXISTS idx_sha256_hash ON filelog_sha256(sha256);
CREATE INDEX IF NOT EXISTS idx_sha256_upload ON filelog_sha256(upload_status);
CREATE INDEX IF NOT EXISTS idx_sha256_source ON filelog_sha256(source_table, source_id);

-- Activity log
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    filepath TEXT,
    path_id INTEGER REFERENCES registered_paths(id) ON DELETE SET NULL,
    message TEXT,
    details TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log(event_type);
CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_log(created_at DESC);

-- Queue 1: Pending Checksum (Scanner -> Checksum Calculator)
CREATE TABLE IF NOT EXISTS queue_pending_checksum (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL,  -- 'new' or 'modified'
    queued_at TEXT DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_checksum_queued ON queue_pending_checksum(queued_at ASC);
CREATE INDEX IF NOT EXISTS idx_checksum_retry ON queue_pending_checksum(next_retry_at);

-- Queue 2: Pending Upload (Checksum Calculator -> Uploader)
CREATE TABLE IF NOT EXISTS queue_pending_upload (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    queued_at TEXT DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_upload_queued ON queue_pending_upload(queued_at ASC);
CREATE INDEX IF NOT EXISTS idx_upload_retry ON queue_pending_upload(next_retry_at);

-- Queue 3: Pending Deletion (Scanner -> Uploader)
CREATE TABLE IF NOT EXISTS queue_pending_deletion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL UNIQUE,
    sha256 TEXT,
    deleted_at TEXT DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_deletion_deleted ON queue_pending_deletion(deleted_at ASC);
CREATE INDEX IF NOT EXISTS idx_deletion_retry ON queue_pending_deletion(next_retry_at);

-- Files table for tracking file state
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT UNIQUE NOT NULL,
    file_size INTEGER NOT NULL,
    file_mode INTEGER,
    file_uid INTEGER,
    file_gid INTEGER,
    file_mtime REAL NOT NULL,
    file_atime REAL,
    file_ctime REAL,
    sha256 TEXT,
    status TEXT DEFAULT 'discovered',  -- 'discovered', 'ready_for_upload', 'completed', 'unchanged'
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TEXT,
    uploaded_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_path ON files(filepath);
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(file_mtime);
"""


def get_create_filelog_table_sql(table_name: str) -> str:
    """Get SQL to create a monthly filelog table.

    Args:
        table_name: Name of the table (e.g., 'filelog_202412')

    Returns:
        SQL statement to create the table
    """
    return f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filepath TEXT NOT NULL,
        ctime REAL NOT NULL,
        mtime REAL NOT NULL,
        atime REAL,
        file_size INTEGER NOT NULL,
        permissions INTEGER,
        uid INTEGER,
        gid INTEGER,
        logged_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_{table_name}_path ON {table_name}(filepath);
    CREATE INDEX IF NOT EXISTS idx_{table_name}_mtime ON {table_name}(mtime);
    CREATE INDEX IF NOT EXISTS idx_{table_name}_size ON {table_name}(file_size);
    """


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database manager.

        Args:
            db_path: Path to database file. Uses settings if not provided.
        """
        self.db_path = db_path or settings.db_path_resolved
        self._connection: Optional[aiosqlite.Connection] = None
        self._current_month_table: Optional[str] = None

    async def connect(self) -> None:
        """Connect to the database and create tables if needed."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        # Enable foreign keys
        await self._connection.execute("PRAGMA foreign_keys = ON")

        # Create base tables
        await self._connection.executescript(CREATE_BASE_TABLES_SQL)
        await self._connection.commit()

        # Ensure current month table exists
        await self._ensure_month_table()

        logger.info(f"Connected to database: {self.db_path}")

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the database connection."""
        if not self._connection:
            raise RuntimeError("Database not connected")
        return self._connection

    async def _ensure_month_table(self) -> str:
        """Ensure the current month's filelog table exists.

        Returns:
            The current month's table name
        """
        table_name = get_current_month_table()

        if self._current_month_table != table_name:
            # Create new month table
            await self._connection.executescript(get_create_filelog_table_sql(table_name))
            await self._connection.commit()
            self._current_month_table = table_name
            logger.info(f"Created/verified month table: {table_name}")

        return table_name

    # ===== Registered Paths =====

    async def add_path(self, path: str, recursive: bool = True) -> int:
        """Add a path to watch.

        Returns:
            The ID of the inserted path.
        """
        cursor = await self.connection.execute(
            "INSERT INTO registered_paths (path, recursive) VALUES (?, ?)",
            (path, int(recursive)),
        )
        await self.connection.commit()
        return cursor.lastrowid

    async def get_path(self, path_id: int) -> Optional[PathResponse]:
        """Get a path by ID."""
        cursor = await self.connection.execute(
            "SELECT * FROM registered_paths WHERE id = ?",
            (path_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_path(row)

    async def get_path_by_path(self, path: str) -> Optional[PathResponse]:
        """Get a path by its path string."""
        cursor = await self.connection.execute(
            "SELECT * FROM registered_paths WHERE path = ?",
            (path,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_path(row)

    async def get_all_paths(self, enabled_only: bool = False) -> list[PathResponse]:
        """Get all registered paths."""
        query = "SELECT * FROM registered_paths"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY path"

        cursor = await self.connection.execute(query)
        rows = await cursor.fetchall()
        return [self._row_to_path(row) for row in rows]

    async def delete_path(self, path_id: int) -> bool:
        """Delete a path."""
        cursor = await self.connection.execute(
            "DELETE FROM registered_paths WHERE id = ?",
            (path_id,),
        )
        await self.connection.commit()
        return cursor.rowcount > 0

    async def update_path_scanned(self, path_id: int) -> None:
        """Update the last_scanned_at timestamp."""
        await self.connection.execute(
            "UPDATE registered_paths SET last_scanned_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), path_id),
        )
        await self.connection.commit()

    async def get_path_file_count(self, path_id: int) -> int:
        """Get the number of files logged for a path.

        This counts entries in filelog_sha256 that start with the path.
        """
        path = await self.get_path(path_id)
        if not path:
            return 0

        cursor = await self.connection.execute(
            "SELECT COUNT(DISTINCT filepath) FROM filelog_sha256 WHERE filepath LIKE ?",
            (f"{path.path}%",),
        )
        result = await cursor.fetchone()
        return result[0] if result else 0

    def _row_to_path(self, row: aiosqlite.Row) -> PathResponse:
        """Convert a database row to PathResponse."""
        return PathResponse(
            id=row["id"],
            path=row["path"],
            recursive=bool(row["recursive"]),
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_scanned_at=(
                datetime.fromisoformat(row["last_scanned_at"])
                if row["last_scanned_at"]
                else None
            ),
            file_count=0,  # Will be populated separately if needed
        )

    # ===== Exclude Patterns =====

    async def add_exclude(self, pattern: str) -> int:
        """Add an exclude pattern."""
        cursor = await self.connection.execute(
            "INSERT INTO exclude_patterns (pattern) VALUES (?)",
            (pattern,),
        )
        await self.connection.commit()
        return cursor.lastrowid

    async def get_all_excludes(self) -> list[ExcludeResponse]:
        """Get all exclude patterns."""
        cursor = await self.connection.execute(
            "SELECT * FROM exclude_patterns ORDER BY pattern"
        )
        rows = await cursor.fetchall()
        return [
            ExcludeResponse(
                id=row["id"],
                pattern=row["pattern"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    async def delete_exclude(self, pattern_id: int) -> bool:
        """Delete an exclude pattern."""
        cursor = await self.connection.execute(
            "DELETE FROM exclude_patterns WHERE id = ?",
            (pattern_id,),
        )
        await self.connection.commit()
        return cursor.rowcount > 0

    # ===== File Logging (Monthly Tables) =====

    async def log_file(
        self,
        filepath: str,
        ctime: float,
        mtime: float,
        atime: float,
        file_size: int,
        permissions: Optional[int] = None,
        uid: Optional[int] = None,
        gid: Optional[int] = None,
    ) -> Optional[int]:
        """Log a file entry to the current month's table.

        Only logs if the file is new or has changed (ctime or mtime different).

        Args:
            filepath: Full path to the file
            ctime: File creation/change time
            mtime: File modification time
            atime: File access time
            file_size: File size in bytes
            permissions: File permissions (mode)
            uid: Owner user ID
            gid: Owner group ID

        Returns:
            The ID of the inserted row, or None if skipped (no changes)
        """
        table_name = await self._ensure_month_table()

        # Check for existing entry with same ctime and mtime
        cursor = await self.connection.execute(
            f"""
            SELECT id, ctime, mtime FROM {table_name}
            WHERE filepath = ?
            ORDER BY logged_at DESC
            LIMIT 1
            """,
            (filepath,),
        )
        row = await cursor.fetchone()

        if row:
            # Check if ctime or mtime changed
            if row["ctime"] == ctime and row["mtime"] == mtime:
                # No changes, skip
                return None

        # Insert new entry
        cursor = await self.connection.execute(
            f"""
            INSERT INTO {table_name} (
                filepath, ctime, mtime, atime, file_size,
                permissions, uid, gid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (filepath, ctime, mtime, atime, file_size, permissions, uid, gid),
        )
        await self.connection.commit()
        return cursor.lastrowid

    async def get_filelog_entry(self, table_name: str, entry_id: int) -> Optional[FileLogEntry]:
        """Get a specific filelog entry.

        Args:
            table_name: The monthly table name
            entry_id: The entry ID

        Returns:
            FileLogEntry or None
        """
        cursor = await self.connection.execute(
            f"SELECT * FROM {table_name} WHERE id = ?",
            (entry_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        return FileLogEntry(
            id=row["id"],
            filepath=row["filepath"],
            ctime=row["ctime"],
            mtime=row["mtime"],
            atime=row["atime"],
            file_size=row["file_size"],
            permissions=row["permissions"],
            uid=row["uid"],
            gid=row["gid"],
            logged_at=datetime.fromisoformat(row["logged_at"]),
            source_table=table_name,
        )

    async def get_unprocessed_entries(self, limit: int = 100) -> list[FileLogEntry]:
        """Get filelog entries that haven't been processed to filelog_sha256.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of unprocessed FileLogEntry objects
        """
        entries = []

        # Get all filelog tables
        cursor = await self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'filelog_2%'"
        )
        tables = [row["name"] for row in await cursor.fetchall()]

        for table_name in sorted(tables):
            if len(entries) >= limit:
                break

            # Get entries not in filelog_sha256
            remaining = limit - len(entries)
            cursor = await self.connection.execute(
                f"""
                SELECT f.* FROM {table_name} f
                LEFT JOIN filelog_sha256 s
                    ON s.source_table = ? AND s.source_id = f.id
                WHERE s.id IS NULL
                LIMIT ?
                """,
                (table_name, remaining),
            )
            rows = await cursor.fetchall()

            for row in rows:
                entries.append(FileLogEntry(
                    id=row["id"],
                    filepath=row["filepath"],
                    ctime=row["ctime"],
                    mtime=row["mtime"],
                    atime=row["atime"],
                    file_size=row["file_size"],
                    permissions=row["permissions"],
                    uid=row["uid"],
                    gid=row["gid"],
                    logged_at=datetime.fromisoformat(row["logged_at"]),
                    source_table=table_name,
                ))

        return entries

    # ===== SHA256 Table =====

    async def add_sha256_entry(
        self,
        filepath: str,
        ctime: float,
        mtime: float,
        atime: float,
        file_size: int,
        sha256: str,
        source_table: str,
        source_id: int,
        permissions: Optional[int] = None,
        uid: Optional[int] = None,
        gid: Optional[int] = None,
    ) -> int:
        """Add a processed entry to the filelog_sha256 table.

        Args:
            filepath: Full path to the file
            ctime: File creation/change time
            mtime: File modification time
            atime: File access time
            file_size: File size in bytes
            sha256: SHA256 checksum of the file
            source_table: The source monthly table name
            source_id: The ID in the source table
            permissions: File permissions (mode)
            uid: Owner user ID
            gid: Owner group ID

        Returns:
            The ID of the inserted row
        """
        cursor = await self.connection.execute(
            """
            INSERT INTO filelog_sha256 (
                filepath, ctime, mtime, atime, file_size,
                permissions, uid, gid, sha256, source_table, source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filepath, ctime, mtime, atime, file_size,
                permissions, uid, gid, sha256, source_table, source_id
            ),
        )
        await self.connection.commit()
        return cursor.lastrowid

    async def get_sha256_entries(
        self,
        filepath_prefix: Optional[str] = None,
        upload_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[FileLogSha256Entry], int]:
        """Get entries from filelog_sha256.

        Args:
            filepath_prefix: Filter by filepath prefix
            upload_status: Filter by upload status (None, 'meta', 'full')
            limit: Maximum number of entries
            offset: Number of entries to skip

        Returns:
            Tuple of (entries, total_count)
        """
        query = "SELECT * FROM filelog_sha256 WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM filelog_sha256 WHERE 1=1"
        params = []

        if filepath_prefix:
            query += " AND filepath LIKE ?"
            count_query += " AND filepath LIKE ?"
            params.append(f"{filepath_prefix}%")

        if upload_status is not None:
            if upload_status == "":
                query += " AND upload_status IS NULL"
                count_query += " AND upload_status IS NULL"
            else:
                query += " AND upload_status = ?"
                count_query += " AND upload_status = ?"
                params.append(upload_status)

        # Get count
        cursor = await self.connection.execute(count_query, params)
        total = (await cursor.fetchone())[0]

        # Get entries
        query += " ORDER BY processed_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await self.connection.execute(query, params)
        rows = await cursor.fetchall()

        entries = [
            FileLogSha256Entry(
                id=row["id"],
                filepath=row["filepath"],
                ctime=row["ctime"],
                mtime=row["mtime"],
                atime=row["atime"],
                file_size=row["file_size"],
                permissions=row["permissions"],
                uid=row["uid"],
                gid=row["gid"],
                sha256=row["sha256"],
                upload_status=row["upload_status"],
                source_table=row["source_table"],
                source_id=row["source_id"],
                processed_at=datetime.fromisoformat(row["processed_at"]),
            )
            for row in rows
        ]

        return entries, total

    async def get_pending_uploads(self, limit: int = 100) -> list[FileLogSha256Entry]:
        """Get entries that haven't been uploaded yet.

        Args:
            limit: Maximum number of entries

        Returns:
            List of entries with upload_status IS NULL
        """
        entries, _ = await self.get_sha256_entries(upload_status="", limit=limit)
        return entries

    async def update_upload_status(
        self,
        entry_id: int,
        status: str,
    ) -> bool:
        """Update the upload status of an entry.

        Args:
            entry_id: The filelog_sha256 entry ID
            status: The new status ('meta' or 'full')

        Returns:
            True if updated, False if not found
        """
        cursor = await self.connection.execute(
            "UPDATE filelog_sha256 SET upload_status = ? WHERE id = ?",
            (status, entry_id),
        )
        await self.connection.commit()
        return cursor.rowcount > 0

    async def get_sha256_by_hash(self, sha256: str) -> Optional[FileLogSha256Entry]:
        """Get an entry by its SHA256 hash.

        Args:
            sha256: The SHA256 hash

        Returns:
            The entry or None
        """
        cursor = await self.connection.execute(
            "SELECT * FROM filelog_sha256 WHERE sha256 = ? LIMIT 1",
            (sha256,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        return FileLogSha256Entry(
            id=row["id"],
            filepath=row["filepath"],
            ctime=row["ctime"],
            mtime=row["mtime"],
            atime=row["atime"],
            file_size=row["file_size"],
            permissions=row["permissions"],
            uid=row["uid"],
            gid=row["gid"],
            sha256=row["sha256"],
            upload_status=row["upload_status"],
            source_table=row["source_table"],
            source_id=row["source_id"],
            processed_at=datetime.fromisoformat(row["processed_at"]),
        )

    async def get_sha256_by_id(self, entry_id: int) -> Optional[FileLogSha256Entry]:
        """Get an entry by its ID.

        Args:
            entry_id: The filelog_sha256 entry ID

        Returns:
            The entry or None
        """
        cursor = await self.connection.execute(
            "SELECT * FROM filelog_sha256 WHERE id = ? LIMIT 1",
            (entry_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        return FileLogSha256Entry(
            id=row["id"],
            filepath=row["filepath"],
            ctime=row["ctime"],
            mtime=row["mtime"],
            atime=row["atime"],
            file_size=row["file_size"],
            permissions=row["permissions"],
            uid=row["uid"],
            gid=row["gid"],
            sha256=row["sha256"],
            upload_status=row["upload_status"],
            source_table=row["source_table"],
            source_id=row["source_id"],
            processed_at=datetime.fromisoformat(row["processed_at"]),
        )

    async def delete_sha256_entry(self, entry_id: int) -> bool:
        """Delete an entry from filelog_sha256.

        Args:
            entry_id: The filelog_sha256 entry ID

        Returns:
            True if deleted, False if not found
        """
        cursor = await self.connection.execute(
            "DELETE FROM filelog_sha256 WHERE id = ?",
            (entry_id,),
        )
        await self.connection.commit()
        return cursor.rowcount > 0

    # ===== Monthly Table Management =====

    async def get_filelog_tables(self) -> list[str]:
        """Get all monthly filelog tables.

        Returns:
            List of table names sorted chronologically
        """
        cursor = await self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'filelog_2%'"
        )
        tables = [row["name"] for row in await cursor.fetchall()]
        return sorted(tables)

    async def is_table_fully_processed(self, table_name: str) -> bool:
        """Check if all entries in a monthly table have been processed.

        Args:
            table_name: The monthly table name

        Returns:
            True if all entries are in filelog_sha256
        """
        cursor = await self.connection.execute(
            f"""
            SELECT COUNT(*) FROM {table_name} f
            LEFT JOIN filelog_sha256 s
                ON s.source_table = ? AND s.source_id = f.id
            WHERE s.id IS NULL
            """,
            (table_name,),
        )
        unprocessed = (await cursor.fetchone())[0]
        return unprocessed == 0

    async def cleanup_old_tables(self) -> list[str]:
        """Delete old monthly tables that are fully processed.

        Only deletes tables from previous months (not current).

        Returns:
            List of deleted table names
        """
        current_table = get_current_month_table()
        tables = await self.get_filelog_tables()
        deleted = []

        for table_name in tables:
            # Don't delete current month
            if table_name >= current_table:
                continue

            # Check if fully processed
            if await self.is_table_fully_processed(table_name):
                await self.connection.execute(f"DROP TABLE {table_name}")
                await self.connection.commit()
                deleted.append(table_name)
                logger.info(f"Deleted fully processed table: {table_name}")

        return deleted

    # ===== Server Configuration =====

    async def add_server(
        self,
        name: str,
        url: str,
        username: str,
        password_encrypted: str,
        is_default: bool = False,
    ) -> int:
        """Add a server configuration."""
        if is_default:
            await self.connection.execute(
                "UPDATE server_config SET is_default = 0"
            )

        cursor = await self.connection.execute(
            """
            INSERT INTO server_config (name, url, username, password_encrypted, is_default)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, url, username, password_encrypted, int(is_default)),
        )
        await self.connection.commit()
        return cursor.lastrowid

    async def get_server(self, server_id: int) -> Optional[ServerResponse]:
        """Get a server by ID."""
        cursor = await self.connection.execute(
            "SELECT * FROM server_config WHERE id = ?",
            (server_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_server(row)

    async def get_default_server(self) -> Optional[tuple[ServerResponse, str]]:
        """Get the default server with encrypted password."""
        cursor = await self.connection.execute(
            "SELECT * FROM server_config WHERE is_default = 1"
        )
        row = await cursor.fetchone()
        if not row:
            cursor = await self.connection.execute(
                "SELECT * FROM server_config LIMIT 1"
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_server(row), row["password_encrypted"]

    async def get_all_servers(self) -> list[ServerResponse]:
        """Get all configured servers."""
        cursor = await self.connection.execute(
            "SELECT * FROM server_config ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [self._row_to_server(row) for row in rows]

    async def delete_server(self, server_id: int) -> bool:
        """Delete a server configuration."""
        cursor = await self.connection.execute(
            "DELETE FROM server_config WHERE id = ?",
            (server_id,),
        )
        await self.connection.commit()
        return cursor.rowcount > 0

    async def set_default_server(self, server_id: int) -> bool:
        """Set a server as the default."""
        await self.connection.execute("UPDATE server_config SET is_default = 0")
        cursor = await self.connection.execute(
            "UPDATE server_config SET is_default = 1 WHERE id = ?",
            (server_id,),
        )
        await self.connection.commit()
        return cursor.rowcount > 0

    def _row_to_server(self, row: aiosqlite.Row) -> ServerResponse:
        """Convert a database row to ServerResponse."""
        return ServerResponse(
            id=row["id"],
            name=row["name"],
            url=row["url"],
            username=row["username"],
            is_default=bool(row["is_default"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ===== Activity Log =====

    async def log_activity(
        self,
        event_type: EventType,
        filepath: Optional[str] = None,
        path_id: Optional[int] = None,
        message: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> int:
        """Log an activity event."""
        import json
        cursor = await self.connection.execute(
            """
            INSERT INTO activity_log (event_type, filepath, path_id, message, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_type.value,
                filepath,
                path_id,
                message,
                json.dumps(details) if details else None,
            ),
        )
        await self.connection.commit()
        return cursor.lastrowid

    async def get_activity(
        self,
        limit: int = 100,
        since_id: Optional[int] = None,
        event_type: Optional[EventType] = None,
    ) -> tuple[list[ActivityEvent], bool]:
        """Get activity events."""
        import json
        query = "SELECT * FROM activity_log WHERE 1=1"
        params = []

        if since_id:
            query += " AND id > ?"
            params.append(since_id)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit + 1)

        cursor = await self.connection.execute(query, params)
        rows = await cursor.fetchall()

        has_more = len(rows) > limit
        events = [
            ActivityEvent(
                id=row["id"],
                event_type=EventType(row["event_type"]),
                filepath=row["filepath"],
                path_id=row["path_id"],
                message=row["message"],
                details=json.loads(row["details"]) if row["details"] else None,
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows[:limit]
        ]

        return events, has_more

    # ===== Statistics =====

    async def get_file_stats(self) -> FileStats:
        """Get file statistics from the new files table (3-component architecture)."""
        # Count paths
        cursor = await self.connection.execute(
            "SELECT COUNT(*) FROM registered_paths WHERE enabled = 1"
        )
        paths_watched = (await cursor.fetchone())[0]

        # Count files in the files table
        cursor = await self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM files"
        )
        row = await cursor.fetchone()
        total_files = row[0]
        total_size = row[1]

        # Count pending SHA256 (files in checksum queue)
        cursor = await self.connection.execute(
            "SELECT COUNT(*) FROM queue_pending_checksum"
        )
        pending_sha256 = (await cursor.fetchone())[0]

        # Count pending uploads (files in upload queue)
        cursor = await self.connection.execute(
            "SELECT COUNT(*) FROM queue_pending_upload"
        )
        pending_uploads = (await cursor.fetchone())[0]

        # Count completed uploads by status (from files table)
        # Note: In the new architecture, we don't track 'meta' vs 'full' separately
        # All uploads are full. We'll return 0 for meta_uploads and count
        # files with status='completed' as full_uploads
        cursor = await self.connection.execute(
            """
            SELECT COUNT(*) FROM files
            WHERE status = 'completed'
            """
        )
        full_uploads = (await cursor.fetchone())[0]

        return FileStats(
            total_files=total_files,
            total_size=total_size,
            pending_sha256=pending_sha256,
            pending_uploads=pending_uploads,
            meta_uploads=0,  # Not tracked in new architecture
            full_uploads=full_uploads,
            paths_watched=paths_watched,
        )

    # ===== Queue Operations (3-Component Architecture) =====

    async def enqueue_for_checksum(self, filepath: str, reason: str = "new") -> None:
        """Add file to checksum queue.

        Args:
            filepath: Path to file
            reason: Reason for queuing ('new' or 'modified')
        """
        await self.connection.execute(
            """
            INSERT OR IGNORE INTO queue_pending_checksum (filepath, reason)
            VALUES (?, ?)
            """,
            (filepath, reason),
        )
        await self.connection.commit()

    async def dequeue_for_checksum(self, limit: int = 1) -> list[dict]:
        """Get next files from checksum queue (FIFO).

        Args:
            limit: Maximum number of items to dequeue

        Returns:
            List of queue entries
        """
        cursor = await self.connection.execute(
            """
            SELECT id, filepath, reason, queued_at, retry_count
            FROM queue_pending_checksum
            WHERE next_retry_at IS NULL OR next_retry_at <= datetime('now')
            ORDER BY queued_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def remove_from_checksum_queue(self, filepath: str) -> None:
        """Remove file from checksum queue.

        Args:
            filepath: Path to file
        """
        await self.connection.execute(
            "DELETE FROM queue_pending_checksum WHERE filepath = ?", (filepath,)
        )
        await self.connection.commit()

    async def enqueue_for_upload(self, filepath: str, sha256: str) -> None:
        """Add file to upload queue.

        Args:
            filepath: Path to file
            sha256: SHA256 hash of file
        """
        await self.connection.execute(
            """
            INSERT OR IGNORE INTO queue_pending_upload (filepath, sha256)
            VALUES (?, ?)
            """,
            (filepath, sha256),
        )
        await self.connection.commit()

    async def dequeue_for_upload(self, limit: int = 1) -> list[dict]:
        """Get next files from upload queue (FIFO).

        Args:
            limit: Maximum number of items to dequeue

        Returns:
            List of queue entries
        """
        cursor = await self.connection.execute(
            """
            SELECT id, filepath, sha256, queued_at, retry_count
            FROM queue_pending_upload
            WHERE next_retry_at IS NULL OR next_retry_at <= datetime('now')
            ORDER BY queued_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def remove_from_upload_queue(self, filepath: str) -> None:
        """Remove file from upload queue.

        Args:
            filepath: Path to file
        """
        await self.connection.execute(
            "DELETE FROM queue_pending_upload WHERE filepath = ?", (filepath,)
        )
        await self.connection.commit()

    async def enqueue_for_deletion(self, filepath: str, sha256: Optional[str] = None) -> None:
        """Add file to deletion queue.

        Args:
            filepath: Path to file
            sha256: SHA256 hash of file (if known)
        """
        await self.connection.execute(
            """
            INSERT OR IGNORE INTO queue_pending_deletion (filepath, sha256)
            VALUES (?, ?)
            """,
            (filepath, sha256),
        )
        await self.connection.commit()

    async def dequeue_for_deletion(self, limit: int = 1) -> list[dict]:
        """Get next files from deletion queue (FIFO).

        Args:
            limit: Maximum number of items to dequeue

        Returns:
            List of queue entries
        """
        cursor = await self.connection.execute(
            """
            SELECT id, filepath, sha256, deleted_at, retry_count
            FROM queue_pending_deletion
            WHERE next_retry_at IS NULL OR next_retry_at <= datetime('now')
            ORDER BY deleted_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def remove_from_deletion_queue(self, filepath: str) -> None:
        """Remove file from deletion queue.

        Args:
            filepath: Path to file
        """
        await self.connection.execute(
            "DELETE FROM queue_pending_deletion WHERE filepath = ?", (filepath,)
        )
        await self.connection.commit()

    async def retry_queue_item(self, table_name: str, filepath: str, delay_seconds: int = 60) -> None:
        """Mark queue item for retry after delay.

        Args:
            table_name: Name of queue table
            filepath: Path to file
            delay_seconds: Seconds to wait before retry
        """
        await self.connection.execute(
            f"""
            UPDATE {table_name}
            SET retry_count = retry_count + 1,
                next_retry_at = datetime('now', '+{delay_seconds} seconds')
            WHERE filepath = ?
            """,
            (filepath,),
        )
        await self.connection.commit()

    # ===== Files Table Operations =====

    async def upsert_file(
        self,
        filepath: str,
        file_size: int,
        file_mtime: float,
        file_mode: Optional[int] = None,
        file_uid: Optional[int] = None,
        file_gid: Optional[int] = None,
        file_atime: Optional[float] = None,
        file_ctime: Optional[float] = None,
        sha256: Optional[str] = None,
        status: str = "discovered",
    ) -> None:
        """Insert or update file in files table.

        Args:
            filepath: Path to file
            file_size: Size in bytes
            file_mtime: Modification time
            file_mode: File mode/permissions
            file_uid: User ID
            file_gid: Group ID
            file_atime: Access time
            file_ctime: Creation time
            sha256: SHA256 hash (if calculated)
            status: File status
        """
        await self.connection.execute(
            """
            INSERT INTO files (
                filepath, file_size, file_mtime, file_mode, file_uid, file_gid,
                file_atime, file_ctime, sha256, status, last_checked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(filepath) DO UPDATE SET
                file_size = excluded.file_size,
                file_mtime = excluded.file_mtime,
                file_mode = excluded.file_mode,
                file_uid = excluded.file_uid,
                file_gid = excluded.file_gid,
                file_atime = excluded.file_atime,
                file_ctime = excluded.file_ctime,
                sha256 = COALESCE(excluded.sha256, files.sha256),
                status = excluded.status,
                last_checked_at = datetime('now')
            """,
            (filepath, file_size, file_mtime, file_mode, file_uid, file_gid,
             file_atime, file_ctime, sha256, status),
        )
        await self.connection.commit()

    async def get_file(self, filepath: str) -> Optional[dict]:
        """Get file from files table.

        Args:
            filepath: Path to file

        Returns:
            File record or None
        """
        cursor = await self.connection.execute(
            "SELECT * FROM files WHERE filepath = ?", (filepath,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_file_sha256(self, filepath: str, sha256: str) -> None:
        """Update file SHA256 and mark as ready for upload.

        Args:
            filepath: Path to file
            sha256: SHA256 hash
        """
        await self.connection.execute(
            """
            UPDATE files
            SET sha256 = ?, status = 'ready_for_upload', last_checked_at = datetime('now')
            WHERE filepath = ?
            """,
            (sha256, filepath),
        )
        await self.connection.commit()

    async def mark_file_uploaded(self, filepath: str) -> None:
        """Mark file as uploaded.

        Args:
            filepath: Path to file
        """
        await self.connection.execute(
            """
            UPDATE files
            SET status = 'completed', uploaded_at = datetime('now')
            WHERE filepath = ?
            """,
            (filepath,),
        )
        await self.connection.commit()

    async def delete_file(self, filepath: str) -> None:
        """Delete file from files table.

        Args:
            filepath: Path to file
        """
        await self.connection.execute(
            "DELETE FROM files WHERE filepath = ?", (filepath,)
        )
        await self.connection.commit()

    async def get_queue_counts(self) -> dict:
        """Get count of items in each queue.

        Returns:
            Dictionary with queue counts
        """
        counts = {}

        # Checksum queue
        cursor = await self.connection.execute(
            "SELECT COUNT(*) FROM queue_pending_checksum"
        )
        counts["pending_checksum"] = (await cursor.fetchone())[0]

        # Upload queue
        cursor = await self.connection.execute(
            "SELECT COUNT(*) FROM queue_pending_upload"
        )
        counts["pending_upload"] = (await cursor.fetchone())[0]

        # Deletion queue
        cursor = await self.connection.execute(
            "SELECT COUNT(*) FROM queue_pending_deletion"
        )
        counts["pending_deletion"] = (await cursor.fetchone())[0]

        return counts


# Global database instance
db = Database()
