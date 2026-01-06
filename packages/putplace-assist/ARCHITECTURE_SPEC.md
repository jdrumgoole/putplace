# PutPlace Assist - Three-Component Architecture Specification

## Overview

PutPlace Assist is refactored into three independent components connected by persistent queues:

1. **Scanner** - Discovers file changes, new files, and deletions
2. **Checksum Calculator** - Calculates SHA256 hashes for changed files
3. **Uploader** - Uploads file metadata and content to server (chunked uploads)

**Data Flow:**
```
Scanner → Queue 1 → Checksum Calculator → Queue 2 → Uploader
   ↓          ↓              ↓                           ↓
SQLite    Queue 3       SQLite (write)             SQLite (write)
(read)   (deletions)

Queue 3 (deletions) → Uploader (DELETE notification to server)
```

**Key Design Decisions:**
- ✅ Periodic scanning (60s default) + real-time events (inotify/FSEvents) after initial scan
- ✅ Moves/renames treated as delete + new file
- ✅ Deletions queued for server notification
- ✅ All queues use strict FIFO ordering
- ✅ All files uploaded with content (no metadata-only uploads)
- ✅ Failed files removed immediately, rediscovered on next scan
- ✅ All uploads chunked in configurable 2MB chunks

## Component 1: Scanner

### Responsibility
Monitors registered directories for file changes, new files, and deletions using:
- **Initial scan:** Full directory scan on startup and every 60 seconds
- **Real-time events:** Filesystem monitoring (inotify/FSEvents) after initial scan completes

### Algorithm
```
FOR EACH registered path:
  FOR EACH file in path (recursive):
    entry = SELECT filepath, mtime, sha256 FROM files WHERE filepath = file.path

    IF entry NOT EXISTS:
      // New file discovered
      INSERT INTO queue_pending_checksum (filepath, reason='new', priority=1)

    ELSE IF file.mtime > entry.mtime:
      // File modified since last scan
      INSERT INTO queue_pending_checksum (filepath, reason='modified', priority=2)

    ELSE:
      // File unchanged, skip
      CONTINUE
```

### Configuration
```toml
[scanner]
# Scan interval in seconds (periodic scanning)
# After initial scan, real-time events (inotify/FSEvents) are used if available
scan_interval = 60

# Use filesystem events for real-time change detection (after initial scan)
use_filesystem_events = true

# File stability period - wait for mtime to stop changing
stability_period_seconds = 5

# Exclude patterns (glob syntax)
exclude_patterns = [
  ".git/**",
  "**/__pycache__/**",
  "**/*.pyc",
  "**/node_modules/**",
  "**/.DS_Store"
]

# Skip files larger than this (bytes, 0 = no limit)
max_file_size = 0

# Minimum file age before scanning (seconds)
# Prevents scanning files still being written
min_file_age_seconds = 2
```

### File Stability Check
Before adding to queue, verify file is stable:
- Check mtime hasn't changed for `stability_period_seconds`
- Prevents checksumming files still being written

### SQLite Access
- **Read-only** access to `files` table
- Checks if file exists and compares mtime
- Does NOT write to database

### Error Handling
| Error | Action |
|-------|--------|
| Permission denied | Log warning, skip file, continue scan |
| Path not found | Log error, remove from registered paths |
| Symlink loop | Log warning, skip directory |
| I/O error | Log error, retry on next scan cycle |

### File Type Handling

**Regular Files:**
- Process normally

**Directories:**
- Skip (only scan contents)

**Symlinks:**
- Follow if within registered paths
- Do NOT follow external symlinks (prevent infinite loops)

**Special Files (sockets, pipes, devices):**
- Skip silently

### Deletion Detection
On each scan cycle:
```sql
-- Find files in DB that no longer exist on disk
SELECT filepath FROM files
WHERE filepath LIKE '{registered_path}%'
  AND filepath NOT IN (current_scan_results)
```

**Deletion Behavior:**
- Queue deletion event to be communicated to server
- Remove from local SQLite database immediately
- Server tracks deletion timestamp

**Deletion Event:**
```python
# Queue deletion for server notification
INSERT INTO queue_pending_deletion (filepath, sha256, deleted_at)
SELECT filepath, sha256, CURRENT_TIMESTAMP
FROM files
WHERE filepath = ?;

# Remove from files table
DELETE FROM files WHERE filepath = ?;
```

### Move/Rename Detection
**Strategy: Treat as delete + new file**

- Move detected as: deletion of old path + discovery of new path
- No inode tracking (simplified approach)
- Server will see two events: DELETE old path, PUT new path
- Same SHA256 allows server to recognize it's the same file content

## Component 2: Checksum Calculator

### Responsibility
Calculates SHA256 checksums for files in Queue 1, updates SQLite, and queues uploads.

### Algorithm
```
WHILE TRUE:
  entry = DEQUEUE from queue_pending_checksum

  IF file NOT EXISTS on disk:
    // File deleted between scan and checksum
    MARK as 'deleted' in SQLite
    CONTINUE

  TRY:
    sha256 = CALCULATE_SHA256(entry.filepath)

    existing = SELECT sha256, upload_status FROM files WHERE filepath = entry.filepath

    IF existing.sha256 == sha256:
      // Checksum unchanged, no upload needed
      UPDATE files SET last_checked_at = NOW() WHERE filepath = entry.filepath
      LOG "File unchanged: {filepath}"
      CONTINUE

    ELSE:
      // New or changed checksum
      UPSERT files (filepath, sha256, mtime, file_size, last_checked_at, status='ready_for_upload')
      INSERT INTO queue_pending_upload (filepath, sha256, upload_content)
      LOG "File queued for upload: {filepath}"

  CATCH FileNotFoundError:
    MARK as 'deleted'

  CATCH PermissionError:
    MARK as 'checksum_error', retry_count++
    IF retry_count < 3:
      REQUEUE with exponential backoff

  CATCH IOError:
    MARK as 'checksum_error', retry_count++
    IF retry_count < 3:
      REQUEUE with exponential backoff
```

### Configuration
```toml
[checksum_calculator]
# Number of parallel checksum workers
parallel_workers = 4

# Chunk size for reading files (bytes)
chunk_size = 8192

# Hash algorithm (currently only SHA256)
algorithm = "sha256"

# Retry configuration
retry_attempts = 3
retry_delay_seconds = 5.0
retry_backoff_multiplier = 2.0  # exponential backoff
```

### SHA256 Calculation
```python
def calculate_sha256(filepath: str, chunk_size: int = 8192) -> str:
    """Calculate SHA256 hash of file."""
    hash_obj = hashlib.sha256()

    with open(filepath, 'rb') as f:
        while chunk := f.read(chunk_size):
            hash_obj.update(chunk)

    return hash_obj.hexdigest()
```

### SQLite Access
- **Read-write** access to `files` table
- INSERT new files
- UPDATE existing files (sha256, mtime, file_size, last_checked_at, status)
- **Write** to `queue_pending_upload` table

### Error Handling
| Error | Retry Strategy | Final Action |
|-------|---------------|-------------|
| File not found | No retry | Delete from queue and files table |
| Permission denied | 3 retries, 5s delay | Delete from queue and files table |
| I/O error | 3 retries, exponential backoff | Delete from queue and files table |
| File locked | 3 retries, 5s delay | Delete from queue and files table |

**Failure Strategy:**
- After all retries exhausted, remove file from database entirely
- Next scan cycle will rediscover the file and retry
- No persistent "failed" state maintained

### Retry Logic
```python
async def process_with_retry(filepath: str, max_retries: int = 3):
    delay = 5.0

    for attempt in range(max_retries):
        try:
            return await calculate_checksum(filepath)
        except (IOError, PermissionError) as e:
            if attempt == max_retries - 1:
                # Final failure - remove from database
                await db.delete_file(filepath)
                raise
            await asyncio.sleep(delay)
            delay *= 2.0  # exponential backoff
```

## Component 3: Uploader

### Responsibility
Uploads file metadata and content to server, and notifies server of file deletions.

### Algorithm

**Upload Worker:**
```
WHILE TRUE:
  entry = DEQUEUE from queue_pending_upload

  IF NOT has_valid_access_token():
    TRY:
      access_token = AUTHENTICATE(server_url, username, password)
    CATCH AuthenticationError:
      LOG "Authentication failed, stopping uploads"
      WAIT for server reconfiguration
      CONTINUE

  TRY:
    // Always upload with content (chunked)
    UPLOAD_FILE_CHUNKED(entry.filepath, entry.sha256, access_token)

    UPDATE files SET status='completed', uploaded_at=NOW() WHERE filepath=entry.filepath
    LOG "Upload successful: {filepath}"

  CATCH 401 Unauthorized:
    // Invalid credentials - user deleted or password changed
    DELETE server credentials
    LOG "Server credentials invalidated"
    REQUEUE entry

  CATCH 409 Conflict:
    // File already exists on server
    UPDATE files SET status='completed', uploaded_at=NOW()
    LOG "File already on server: {filepath}"

  CATCH NetworkError:
    retry_count++
    IF retry_count < retry_attempts:
      REQUEUE with exponential backoff
    ELSE:
      DELETE from queue and files table

  CATCH TimeoutError:
    retry_count++
    IF retry_count < retry_attempts:
      REQUEUE with exponential backoff
    ELSE:
      DELETE from queue and files table
```

**Deletion Worker:**
```
WHILE TRUE:
  entry = DEQUEUE from queue_pending_deletion

  IF NOT has_valid_access_token():
    TRY:
      access_token = AUTHENTICATE(server_url, username, password)
    CATCH AuthenticationError:
      LOG "Authentication failed, stopping deletion notifications"
      WAIT for server reconfiguration
      CONTINUE

  TRY:
    SEND_DELETE_NOTIFICATION(entry.filepath, entry.sha256, entry.deleted_at, access_token)
    DELETE FROM queue_pending_deletion WHERE id=entry.id
    LOG "Deletion notified: {filepath}"

  CATCH 401 Unauthorized:
    DELETE server credentials
    LOG "Server credentials invalidated"
    REQUEUE entry

  CATCH 404 Not Found:
    // File doesn't exist on server anyway
    DELETE FROM queue_pending_deletion WHERE id=entry.id
    LOG "File not found on server: {filepath}"

  CATCH NetworkError:
    retry_count++
    IF retry_count < retry_attempts:
      REQUEUE with exponential backoff
    ELSE:
      DELETE FROM queue_pending_deletion WHERE id=entry.id
      LOG "Deletion notification failed after retries: {filepath}"
```

### Configuration
```toml
[uploader]
# Number of parallel upload workers
parallel_uploads = 4

# Timeout per file upload (seconds)
timeout_seconds = 600

# Retry configuration
retry_attempts = 3
retry_delay_seconds = 5.0

# Chunked upload configuration
chunk_size_mb = 2  # Upload files in 2MB chunks
enable_chunked_upload = true

# Always upload file content (metadata + content)
upload_content = true
```

### Chunked Upload Implementation

**All files uploaded in configurable chunks (default: 2MB)**

```python
async def upload_file_chunked(
    filepath: str,
    sha256: str,
    chunk_size_mb: int = 2
) -> None:
    """Upload file in chunks to handle large files."""
    chunk_size = chunk_size_mb * 1024 * 1024  # Convert MB to bytes
    file_size = os.path.getsize(filepath)
    total_chunks = (file_size + chunk_size - 1) // chunk_size  # Ceiling division

    # Initiate multipart upload
    upload_id = await initiate_upload(filepath, sha256, file_size)

    # Upload chunks
    uploaded_parts = []
    with open(filepath, 'rb') as f:
        for chunk_num in range(total_chunks):
            chunk_data = f.read(chunk_size)

            etag = await upload_chunk(
                upload_id=upload_id,
                chunk_num=chunk_num,
                data=chunk_data
            )

            uploaded_parts.append({
                'chunk_num': chunk_num,
                'etag': etag
            })

    # Complete multipart upload
    await complete_upload(upload_id, uploaded_parts)
```

**Server API Changes Required:**
- `POST /uploads/initiate` - Start multipart upload, returns upload_id
- `PUT /uploads/{upload_id}/chunk/{chunk_num}` - Upload single chunk
- `POST /uploads/{upload_id}/complete` - Finalize upload
- `DELETE /uploads/{upload_id}` - Cancel/abort upload

### SQLite Access
- **Write** access to `files` table
- UPDATE upload_status, uploaded_at, retry_count

### Error Handling
| Error | Retry Strategy | Final Action |
|-------|---------------|-------------|
| 401 Unauthorized | No retry, invalidate creds | Delete from queue/files, requeue after auth |
| 403 Forbidden | 3 retries | Delete from queue and files table |
| 404 Not Found | No retry | Delete from queue and files table |
| 409 Conflict | No retry | Mark as completed (file already exists) |
| 413 Payload Too Large | No retry | Delete from queue and files table |
| 500 Server Error | 3 retries, exponential backoff | Delete from queue and files table |
| Network timeout | 3 retries, exponential backoff | Delete from queue and files table |
| Connection refused | 3 retries, exponential backoff | Delete from queue and files table |
| Chunk upload failure | Retry chunk 3×, then abort entire upload | Delete from queue and files table |

**Failure Strategy:**
- After all retries exhausted, remove file from database entirely
- Next scan cycle will rediscover the file and retry
- No persistent "upload_failed" state maintained

## Queue Implementation

### Persistent Queues (SQLite Tables)

**Queue 1: Pending Checksum**
```sql
CREATE TABLE queue_pending_checksum (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL,  -- 'new' or 'modified'
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP NULL,

    INDEX idx_queued (queued_at ASC)
);
```

**Queue 2: Pending Upload**
```sql
CREATE TABLE queue_pending_upload (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP NULL,

    INDEX idx_queued (queued_at ASC)
);
```

**Queue 3: Pending Deletion**
```sql
CREATE TABLE queue_pending_deletion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL UNIQUE,
    sha256 TEXT,
    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP NULL,

    INDEX idx_deleted (deleted_at ASC)
);
```

### Queue Operations

**Enqueue:**
```sql
INSERT OR IGNORE INTO queue_pending_checksum (filepath, reason, priority)
VALUES (?, ?, ?);
```

**Dequeue (FIFO for all queues):**
```sql
-- Queue 1: Pending Checksum (FIFO)
SELECT * FROM queue_pending_checksum
WHERE next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP
ORDER BY queued_at ASC
LIMIT 1;

-- Queue 2: Pending Upload (FIFO)
SELECT * FROM queue_pending_upload
WHERE next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP
ORDER BY queued_at ASC
LIMIT 1;

-- Queue 3: Pending Deletion (FIFO)
SELECT * FROM queue_pending_deletion
WHERE next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP
ORDER BY deleted_at ASC
LIMIT 1;
```

**Complete (Remove from Queue):**
```sql
DELETE FROM queue_pending_checksum WHERE id = ?;
DELETE FROM queue_pending_upload WHERE id = ?;
```

**Requeue with Backoff:**
```sql
UPDATE queue_pending_checksum
SET retry_count = retry_count + 1,
    next_retry_at = datetime('now', '+' || (retry_count * 5) || ' seconds')
WHERE id = ?;
```

### Queue Limits

**Backpressure Handling:**
- Queue 1 max size: 100,000 entries
- Queue 2 max size: 10,000 entries

**If Queue Full:**
- Scanner (Component 1): Sleep and retry, log warning
- Checksum Calculator (Component 2): Wait for Queue 2 to drain

## SQLite Schema

### Core Tables

**Files Table:**
```sql
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL UNIQUE,
    hostname TEXT NOT NULL,
    sha256 TEXT,
    file_size INTEGER,
    mtime TIMESTAMP,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMP,
    status TEXT DEFAULT 'discovered',  -- discovered, ready_for_upload, completed
    uploaded_at TIMESTAMP,

    INDEX idx_filepath (filepath),
    INDEX idx_sha256 (sha256),
    INDEX idx_status (status)
);
```

**Path Registry Table:**
```sql
CREATE TABLE path_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    recursive BOOLEAN DEFAULT TRUE,
    enabled BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scan_at TIMESTAMP,
    filesystem_watch_active BOOLEAN DEFAULT FALSE,

    INDEX idx_enabled (enabled)
);
```

### State Machine

**File States:**
```
discovered → ready_for_upload → completed
    ↓
unchanged
```

**Status Values:**
- `discovered` - Found by scanner, not yet checksummed
- `ready_for_upload` - Checksum calculated, queued for upload
- `unchanged` - Checksum matches previous, no upload needed
- `completed` - Successfully uploaded

**Failed States:**
- Files that fail checksum or upload are **removed from database entirely**
- Next scan cycle will rediscover them and retry
- No persistent "error" or "failed" states

**Deleted Files:**
- Removed from `files` table immediately
- Added to `queue_pending_deletion` for server notification

## Component Coordination

### Process Architecture

**Single Daemon Process with Multiple Threads:**

The three components run as threads within a single `pp_assist` daemon process:

```
pp_assist (main process)
├── Main Thread (async event loop)
│   └── Component 1: Scanner (async task)
├── Thread Pool: Checksum Calculator (N threads)
│   └── Component 2 workers (default: 4 threads)
└── Thread Pool: Uploader (M threads)
    ├── Component 3a: Upload workers (default: 4 threads)
    └── Component 3b: Deletion workers (default: 2 threads)
```

**Rationale:**
- **Single process:** Simpler deployment, shared SQLite database connection
- **Async main thread:** Efficient for I/O-bound Scanner and daemon coordination
- **Thread pools:** Python's `ThreadPoolExecutor` for parallel workers
- **Shared memory:** Direct access to queues via SQLite (no IPC needed)
- **Free-threading:** Python 3.13+ eliminates GIL contention, making threads efficient for CPU-bound work (SHA256 calculation)

### Daemon Startup Sequence
```
1. Initialize SQLite database
2. Start async event loop in main thread
3. Start Component 1 (Scanner) as async task
4. Create ThreadPoolExecutor for Component 2 (N workers)
5. Create ThreadPoolExecutor for Component 3a (M upload workers)
6. Create ThreadPoolExecutor for Component 3b (2 deletion workers)
7. Resume processing queued items from previous session
```

### Resume Incomplete Work
On startup, reprocess files stuck in intermediate states:

```sql
-- Requeue files stuck in checksum calculation
INSERT OR IGNORE INTO queue_pending_checksum (filepath, reason)
SELECT filepath, 'retry' FROM files
WHERE status = 'discovered'
  AND filepath NOT IN (SELECT filepath FROM queue_pending_checksum);

-- Requeue files stuck in upload
INSERT OR IGNORE INTO queue_pending_upload (filepath, sha256)
SELECT filepath, sha256
FROM files
WHERE status = 'ready_for_upload'
  AND filepath NOT IN (SELECT filepath FROM queue_pending_upload);
```

### Graceful Shutdown
```
1. Stop Component 1 (Scanner) - no new files queued
2. Signal Component 2 & 3 to finish current work
3. Wait up to shutdown_timeout seconds for in-progress operations
4. If workers don't finish by timeout, force terminate
5. Persist queue state (already in SQLite)
6. Exit
```

**Configuration:**
```toml
[daemon]
# Graceful shutdown timeout (seconds)
shutdown_timeout = 10
```

**Timeout Behavior:**
- If workers don't finish by shutdown_timeout, force terminate threads/processes
- Queue state persists in SQLite (survives force termination)
- In-progress operations resume on next startup
- Partial checksums or uploads are retried from beginning

## API Changes

### Stats Endpoint

**GET /stats**
```json
{
  "files": {
    "total": 1500,
    "discovered": 50,
    "ready_for_upload": 10,
    "completed": 1400,
    "unchanged": 5
  },
  "queues": {
    "pending_checksum": {
      "count": 50,
      "oldest_queued_at": "2026-01-05T12:00:00Z"
    },
    "pending_upload": {
      "count": 10,
      "oldest_queued_at": "2026-01-05T12:30:00Z"
    },
    "pending_deletion": {
      "count": 3,
      "oldest_deleted_at": "2026-01-05T11:45:00Z"
    }
  },
  "components": {
    "scanner": {
      "status": "running",
      "last_scan_at": "2026-01-05T12:35:00Z",
      "next_scan_at": "2026-01-05T12:36:00Z",
      "filesystem_events_active": true,
      "registered_paths": 3,
      "files_scanned": 1500
    },
    "checksum_calculator": {
      "status": "running",
      "active_workers": 4,
      "total_processed": 1450,
      "processing_rate": 12.5  // files per second
    },
    "uploader": {
      "status": "running",
      "active_workers": 4,
      "total_uploaded": 1400,
      "upload_rate": 8.3  // files per second
    }
  }
}
```

### New Endpoints

**DELETE /files/{sha256}**
Notify server of file deletion:
```
Request:
DELETE /files/{sha256}
{
  "filepath": "/path/to/deleted/file.txt",
  "hostname": "client-machine",
  "deleted_at": "2026-01-05T12:00:00Z"
}

Response:
200 OK - Deletion recorded
404 Not Found - File not found on server
```

**POST /uploads/initiate**
Initiate chunked upload:
```
Request:
POST /uploads/initiate
{
  "filepath": "/path/to/file.txt",
  "sha256": "abc123...",
  "file_size": 10485760,
  "chunk_size": 2097152,
  "total_chunks": 5
}

Response:
{
  "upload_id": "uuid-1234-5678",
  "expires_at": "2026-01-05T13:00:00Z"
}
```

**PUT /uploads/{upload_id}/chunk/{chunk_num}**
Upload single chunk:
```
Request:
PUT /uploads/{upload_id}/chunk/0
Content-Type: application/octet-stream
[binary chunk data]

Response:
{
  "etag": "chunk-hash-abc123"
}
```

**POST /uploads/{upload_id}/complete**
Finalize chunked upload:
```
Request:
POST /uploads/{upload_id}/complete
{
  "parts": [
    {"chunk_num": 0, "etag": "chunk-hash-abc123"},
    {"chunk_num": 1, "etag": "chunk-hash-def456"}
  ]
}

Response:
200 OK - Upload completed
{
  "file_id": "file-uuid",
  "sha256": "abc123..."
}
```

**DELETE /uploads/{upload_id}**
Abort chunked upload:
```
DELETE /uploads/{upload_id}

Response:
204 No Content - Upload aborted
```

**POST /scan/trigger**
Manually trigger a scan cycle:
```json
{
  "path": "/path/to/scan",  // optional, defaults to all registered paths
  "force": false  // if true, rescan all files regardless of mtime
}
```

## Monitoring & Observability

### Metrics to Track

**Per Component:**
- Throughput (files/second)
- Active workers
- Error rate
- Average processing time

**Per Queue:**
- Current depth
- Oldest item age
- Enqueue/dequeue rate

**Overall:**
- Total files discovered
- Total files uploaded
- Total bytes uploaded
- Uptime
- Scan cycles completed

### Logging

**Log Levels:**
- DEBUG: Queue operations, file scanning details
- INFO: File state changes (discovered, checksummed, uploaded)
- WARNING: Retries, temporary errors
- ERROR: Permanent failures (checksum_error, upload_failed)

**Structured Logging:**
```json
{
  "timestamp": "2026-01-05T12:00:00Z",
  "level": "INFO",
  "component": "checksum_calculator",
  "event": "file_checksummed",
  "filepath": "/path/to/file.txt",
  "sha256": "abc123...",
  "duration_ms": 125
}
```

## Migration Plan

### Phase 1: Database Schema Updates
1. Add queue tables (queue_pending_checksum, queue_pending_upload)
2. Add inode/device columns to files table
3. Update status field to new state machine

### Phase 2: Component Implementation
1. Refactor existing code into three components
2. Implement queue-based communication
3. Add retry logic and error handling

### Phase 3: Testing
1. Unit tests per component
2. Integration tests with queues
3. E2E tests with full pipeline
4. Performance testing (throughput, latency)

### Phase 4: Deployment
1. Deploy with feature flag (enable new architecture)
2. Run both architectures in parallel for validation
3. Migrate existing database to new schema
4. Switch to new architecture
5. Remove old code

## Performance Considerations

### Bottlenecks

**Component 1 (Scanner):**
- Filesystem I/O for stat() calls
- SQLite queries for existence checks

**Optimization:**
- Batch stat() calls
- Cache SQLite results in memory
- Use inotify/fsevents for change detection (future enhancement)

**Component 2 (Checksum Calculator):**
- CPU-bound (SHA256 calculation)
- Disk I/O for reading files

**Optimization:**
- Parallel workers (default: 4)
- Adjust chunk_size based on file size
- Consider hardware acceleration (SHA-NI instructions)

**Component 3 (Uploader):**
- Network I/O
- Server processing time

**Optimization:**
- Parallel uploads (default: 4)
- HTTP/2 connection reuse
- Compress file content (gzip)

### Expected Throughput

**Assumptions:**
- Average file size: 1 MB
- SHA256 speed: ~500 MB/s per core
- Network upload speed: 100 Mbps (12.5 MB/s)

**Calculated Throughput:**
- Scanner: ~10,000 files/sec (limited by stat() calls)
- Checksum Calculator: ~2,000 files/sec (4 workers × 500 files/sec)
- Uploader: ~50 files/sec (4 workers × 12.5 files/sec)

**Bottleneck:** Uploader (network-bound)

## Security Considerations

### File Access
- Scanner runs with daemon user permissions
- Checksum calculator can only read files, not modify
- Uploader has no direct filesystem access (reads from queue)

### Credential Storage
- Access tokens cached in memory only (not persisted)
- Server credentials stored encrypted in SQLite
- Automatic invalidation on 401 responses

### Path Traversal Protection
- Registered paths validated on registration
- Scanner cannot escape registered paths
- Symlinks followed only within registered paths

## Future Enhancements

### Real-time Change Detection (Implemented)
After initial scan completes, use filesystem event monitoring:
- Linux: inotify
- macOS: FSEvents
- Windows: ReadDirectoryChangesW

Periodic scans still run every 60 seconds as fallback for missed events.

### Content-Based Deduplication
Before upload, check if server already has file with same SHA256:
```
GET /files/{sha256}/exists
→ If exists, skip upload, mark as completed
```

### Bandwidth Throttling
Limit upload rate to prevent network saturation:
```toml
[uploader]
max_bandwidth_mbps = 50  # 0 = unlimited
```

### Compression
Compress file content before upload:
```toml
[uploader]
compress_content = true
compression_algorithm = "gzip"  # or "zstd", "lz4"
```

### Delta Sync
For modified files, upload only changed blocks (rsync-style):
- Calculate block checksums
- Server compares with existing blocks
- Upload only differing blocks

## Architecture Decisions (Finalized)

1. ✅ **Scan Frequency:** Periodic (60s default, configurable) + real-time events after initial scan
2. ✅ **Move Detection:** Treat as delete + new file (no inode tracking)
3. ✅ **Deletion Notification:** Queue deletion events for server notification
4. ✅ **Queue Priority:** Strict FIFO for all queues
5. ✅ **Queue Persistence:** SQLite-backed (survives daemon restarts)
6. ✅ **Upload Content:** Always true (all files uploaded with content)
7. ✅ **Error Retention:** Failed files removed immediately, rediscovered on next scan
8. ✅ **Large File Handling:** Chunked uploads in configurable 2MB chunks

## Summary

This architecture provides:
- ✅ Clear separation of concerns (scan, checksum, upload)
- ✅ Persistent queues (survives daemon restarts)
- ✅ Comprehensive error handling with retries
- ✅ File move/rename detection (inode tracking)
- ✅ Deletion detection and tracking
- ✅ Graceful shutdown and resume
- ✅ Per-path upload content configuration
- ✅ Automatic credential invalidation
- ✅ Queue monitoring and observability
- ✅ Scalable (parallel workers per component)
