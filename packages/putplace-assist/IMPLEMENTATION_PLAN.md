# PutPlace Assist - Implementation Plan

## Dependencies

### New Dependencies Required

**pp_assist (daemon):**

```toml
[project]
dependencies = [
    # Existing dependencies (keep)
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.25.0",
    "python-dotenv>=1.0.0",

    # New dependencies for new architecture
    "watchdog>=3.0.0",        # Cross-platform filesystem events (inotify/FSEvents/ReadDirectoryChangesW)
    "aiosqlite>=0.19.0",      # Async SQLite wrapper for better concurrency
]
```

**Dependency Details:**

1. **watchdog (3.0.0+)**
   - Purpose: Real-time filesystem event monitoring
   - Platform support:
     - Linux: inotify
     - macOS: FSEvents
     - Windows: ReadDirectoryChangesW
   - Used by: Component 1 (Scanner)

2. **aiosqlite (0.19.0+)**
   - Purpose: Async SQLite operations
   - Allows concurrent database access from multiple async contexts
   - Alternative: Keep using sqlite3 with proper locking
   - Used by: All components

**Optional/Future Dependencies:**

```toml
# Optional: If SHA256 performance becomes an issue
"xxhash>=3.0.0",          # Faster hashing algorithm (alternative to SHA256)

# Optional: If we want process-based parallelism for Component 2
"multiprocess>=0.70.0",   # Better than multiprocessing for complex objects
```

### Dependencies to Remove

None - all existing dependencies are still useful.

---

## Server Changes Required (pp_server)

The server needs significant API additions to support the new architecture.

### 1. Chunked Upload Endpoints

**POST /api/uploads/initiate**

Initiate a multipart chunked upload.

```python
# Request
{
  "filepath": "/path/to/file.txt",
  "hostname": "client-machine",
  "sha256": "abc123...",
  "file_size": 104857600,  # 100 MB
  "chunk_size": 2097152,   # 2 MB
  "total_chunks": 50
}

# Response
{
  "upload_id": "uuid-1234-5678-90ab-cdef",
  "expires_at": "2026-01-05T14:00:00Z",  # 1 hour from now
  "chunk_urls": [
    "/api/uploads/uuid-1234.../chunk/0",
    "/api/uploads/uuid-1234.../chunk/1",
    # ... (or generated on demand)
  ]
}
```

**Implementation:**
- Generate unique upload_id (UUID)
- Store upload metadata in MongoDB:
  ```javascript
  {
    upload_id: "uuid-1234...",
    filepath: "/path/to/file.txt",
    hostname: "client-machine",
    sha256: "abc123...",
    file_size: 104857600,
    chunk_size: 2097152,
    total_chunks: 50,
    uploaded_chunks: [],
    status: "initiated",
    expires_at: "2026-01-05T14:00:00Z",
    created_at: "2026-01-05T13:00:00Z"
  }
  ```
- Create temporary storage location (filesystem or S3)
- Return upload_id for subsequent chunk uploads

---

**PUT /api/uploads/{upload_id}/chunk/{chunk_num}**

Upload a single chunk.

```python
# Request
PUT /api/uploads/uuid-1234-5678/chunk/0
Content-Type: application/octet-stream
Content-Length: 2097152
[binary chunk data]

# Response
{
  "chunk_num": 0,
  "etag": "chunk-hash-abc123",
  "received_bytes": 2097152,
  "uploaded_chunks": 1,
  "total_chunks": 50
}
```

**Implementation:**
- Validate upload_id exists and not expired
- Validate chunk_num is within range (0 to total_chunks-1)
- Write chunk to temporary storage:
  - Filesystem: `/tmp/uploads/{upload_id}/chunk_{chunk_num}`
  - S3: Use S3 multipart upload API directly
- Calculate chunk hash (etag) for integrity
- Update MongoDB with uploaded chunk info
- Return progress

---

**POST /api/uploads/{upload_id}/complete**

Finalize the upload after all chunks uploaded.

```python
# Request
{
  "parts": [
    {"chunk_num": 0, "etag": "chunk-hash-abc123"},
    {"chunk_num": 1, "etag": "chunk-hash-def456"},
    # ... all chunks
  ]
}

# Response
{
  "file_id": "file-uuid",
  "sha256": "abc123...",
  "file_size": 104857600,
  "status": "completed",
  "storage_location": "s3://bucket/files/abc123..."
}
```

**Implementation:**
- Validate all chunks uploaded (check against expected total_chunks)
- Validate chunk etags match
- Assemble chunks into final file:
  - Filesystem: Concatenate chunks, move to final location
  - S3: Complete S3 multipart upload
- Calculate final SHA256 and verify against provided hash
- Store file metadata in MongoDB (existing `file_metadata` collection)
- Clean up temporary chunk storage
- Return file metadata

---

**DELETE /api/uploads/{upload_id}**

Abort/cancel an in-progress upload.

```python
# Request
DELETE /api/uploads/uuid-1234-5678

# Response
{
  "upload_id": "uuid-1234-5678",
  "status": "aborted",
  "chunks_uploaded": 10,
  "chunks_deleted": 10
}
```

**Implementation:**
- Mark upload as aborted in MongoDB
- Delete all uploaded chunks from temporary storage
- Clean up metadata
- Return summary

---

**Background Cleanup Job:**

Add a periodic task (e.g., every hour) to clean up expired uploads:
- Find uploads with `expires_at < NOW()` and `status != 'completed'`
- Delete chunk files
- Remove from MongoDB

---

### 2. Deletion Notification Endpoint

**DELETE /api/files/{sha256}**

Notify server that a file has been deleted on the client.

```python
# Request
DELETE /api/files/abc123...
{
  "filepath": "/path/to/deleted/file.txt",
  "hostname": "client-machine",
  "deleted_at": "2026-01-05T12:00:00Z"
}

# Response (Success)
{
  "sha256": "abc123...",
  "filepath": "/path/to/deleted/file.txt",
  "hostname": "client-machine",
  "status": "deleted",
  "deleted_at": "2026-01-05T12:00:00Z"
}

# Response (Not Found)
404 Not Found
{
  "detail": "File not found on server"
}
```

**Implementation:**
- Query MongoDB for file with matching sha256 + hostname + filepath
- If found:
  - Mark as deleted (soft delete):
    ```javascript
    {
      ...existing_fields,
      deleted_at: "2026-01-05T12:00:00Z",
      status: "deleted"
    }
    ```
  - Or hard delete (remove from MongoDB)
  - Optionally: Keep file content in S3 (for backup/recovery)
- If not found: Return 404
- Return deletion confirmation

**Alternative Design:**

Could use a more RESTful endpoint:

```
POST /api/files/deletions
{
  "files": [
    {
      "sha256": "abc123...",
      "filepath": "/path/to/file1.txt",
      "hostname": "client-machine",
      "deleted_at": "2026-01-05T12:00:00Z"
    },
    {
      "sha256": "def456...",
      "filepath": "/path/to/file2.txt",
      "hostname": "client-machine",
      "deleted_at": "2026-01-05T12:00:00Z"
    }
  ]
}
```

This allows batch deletion notifications.

---

### 3. Existing Endpoint Changes

**POST /api/put_file (DEPRECATE)**

The existing `/put_file` endpoint becomes obsolete with chunked uploads. Options:

1. **Keep for backward compatibility** - Support both old and new APIs
2. **Deprecate with migration period** - Return 410 Gone with migration instructions
3. **Redirect to new API** - Auto-convert to chunked upload for small files

**Recommendation:** Keep for backward compatibility, but document as deprecated.

---

### 4. Database Schema Changes (MongoDB)

**New Collection: `upload_sessions`**

```javascript
{
  _id: ObjectId,
  upload_id: "uuid-1234-5678",  // Unique upload identifier
  filepath: "/path/to/file.txt",
  hostname: "client-machine",
  sha256: "abc123...",
  file_size: 104857600,
  chunk_size: 2097152,
  total_chunks: 50,
  uploaded_chunks: [
    {chunk_num: 0, etag: "...", uploaded_at: "..."},
    {chunk_num: 1, etag: "...", uploaded_at: "..."}
  ],
  status: "initiated",  // initiated, uploading, completed, aborted, expired
  storage_backend: "s3",  // or "filesystem"
  storage_location: "s3://bucket/temp/uuid-1234.../",
  expires_at: "2026-01-05T14:00:00Z",
  created_at: "2026-01-05T13:00:00Z",
  completed_at: null
}
```

**Index:**
- `upload_id` (unique)
- `expires_at` (for cleanup job)
- `status` (for queries)

**Updated Collection: `file_metadata`**

Add optional fields:
```javascript
{
  ...existing_fields,
  deleted_at: "2026-01-05T12:00:00Z",  // null if not deleted
  status: "active",  // active, deleted
}
```

**Index:**
- Add index on `status` for efficient queries

---

### 5. S3 Integration Changes

If using S3 storage backend, use S3's native multipart upload API:

```python
# In server code
import boto3

s3_client = boto3.client('s3')

# Initiate multipart upload
response = s3_client.create_multipart_upload(
    Bucket='putplace-files',
    Key=f'files/{sha256}'
)
upload_id = response['UploadId']

# Upload chunk (part)
response = s3_client.upload_part(
    Bucket='putplace-files',
    Key=f'files/{sha256}',
    PartNumber=chunk_num + 1,  # S3 parts are 1-indexed
    UploadId=upload_id,
    Body=chunk_data
)
etag = response['ETag']

# Complete multipart upload
s3_client.complete_multipart_upload(
    Bucket='putplace-files',
    Key=f'files/{sha256}',
    UploadId=upload_id,
    MultipartUpload={
        'Parts': [
            {'PartNumber': 1, 'ETag': etag1},
            {'PartNumber': 2, 'ETag': etag2},
            # ...
        ]
    }
)

# Abort multipart upload (cleanup)
s3_client.abort_multipart_upload(
    Bucket='putplace-files',
    Key=f'files/{sha256}',
    UploadId=upload_id
)
```

This maps directly to our chunked upload API.

---

## pp_client Changes

The current `pp_client` is a standalone CLI tool that:
- Scans directories
- Calculates SHA256
- Uploads directly to server

With the new `pp_assist` daemon architecture, `pp_client` has three possible futures:

### Option 1: Deprecate pp_client (RECOMMENDED)

**Rationale:**
- All functionality now in `pp_assist` daemon
- Daemon is more robust (persistent, retries, queues)
- Avoids code duplication

**Migration Path:**
1. Deprecate `pp_client` with clear message
2. Document how to use `pp_assist` instead:
   ```bash
   # Old way
   pp_client /path/to/scan --url http://server:8000

   # New way
   pp_assist start
   curl -X POST http://localhost:8765/paths -d '{"path": "/path/to/scan", "recursive": true}'
   ```

3. Remove `pp_client` in next major version

---

### Option 2: Rewrite as Daemon Client

Keep `pp_client` as a thin CLI wrapper around `pp_assist` daemon API:

```bash
# pp_client becomes a convenience wrapper
pp_client /path/to/scan

# Internally does:
# 1. Check if pp_assist daemon is running
# 2. POST to /paths to register path
# 3. POST to /scan/trigger to scan
# 4. Poll /stats to monitor progress
# 5. Display progress bar
```

**Pros:**
- Familiar command-line interface
- No breaking changes for users
- Simpler for one-time scans

**Cons:**
- Requires daemon to be running
- Adds another layer of complexity
- Still duplicates some logic

---

### Option 3: Keep for Direct Uploads

Keep `pp_client` for scenarios where daemon isn't needed:

**Use Cases:**
- One-time ad-hoc uploads
- CI/CD pipelines
- Scripting/automation
- Docker containers (ephemeral, don't need persistent daemon)

**Implementation:**
- Update to use new chunked upload API
- Add chunked upload support:
  ```python
  async def upload_file_chunked(filepath: str, server_url: str):
      # Calculate SHA256
      sha256 = calculate_sha256(filepath)
      file_size = os.path.getsize(filepath)

      # Initiate upload
      response = await client.post(f"{server_url}/api/uploads/initiate", json={
          "filepath": filepath,
          "sha256": sha256,
          "file_size": file_size,
          "chunk_size": 2 * 1024 * 1024,
          "total_chunks": (file_size + 2*1024*1024 - 1) // (2*1024*1024)
      })
      upload_id = response.json()["upload_id"]

      # Upload chunks
      with open(filepath, 'rb') as f:
          chunk_num = 0
          while chunk := f.read(2 * 1024 * 1024):
              await client.put(
                  f"{server_url}/api/uploads/{upload_id}/chunk/{chunk_num}",
                  content=chunk
              )
              chunk_num += 1

      # Complete upload
      await client.post(f"{server_url}/api/uploads/{upload_id}/complete")
  ```

**Recommendation:** Use Option 1 or Option 3. Option 2 adds unnecessary complexity.

---

## Electron Client Changes

The Electron GUI client currently communicates with `pp_assist` daemon via REST API.

### API Compatibility

**Good News:** Most of the current API remains unchanged.

**Existing endpoints that don't need changes:**
- `GET /status` - Daemon status
- `GET /servers` - List configured servers
- `POST /servers` - Add server
- `DELETE /servers/{id}` - Remove server
- `GET /paths` - List registered paths
- `POST /paths` - Register path
- `DELETE /paths/{id}` - Remove path
- `GET /config` - Get configuration
- `POST /config` - Update configuration

### New/Changed Endpoints

**GET /stats (Enhanced)**

Add new fields for queue statistics:

```typescript
interface Stats {
  files: {
    total: number;
    discovered: number;
    ready_for_upload: number;
    completed: number;
    unchanged: number;
    // Removed: failed, checksum_error (no longer tracked)
  };
  queues: {
    pending_checksum: {
      count: number;
      oldest_queued_at: string;
    };
    pending_upload: {
      count: number;
      oldest_queued_at: string;
    };
    pending_deletion: {
      count: number;
      oldest_deleted_at: string;
    };
  };
  components: {
    scanner: {
      status: 'running' | 'stopped';
      last_scan_at: string;
      next_scan_at: string;
      filesystem_events_active: boolean;
      registered_paths: number;
      files_scanned: number;
    };
    checksum_calculator: {
      status: 'running' | 'stopped';
      active_workers: number;
      total_processed: number;
      processing_rate: number;  // files/sec
    };
    uploader: {
      status: 'running' | 'stopped';
      active_workers: number;
      total_uploaded: number;
      upload_rate: number;  // files/sec
    };
  };
}
```

**Electron Client Changes:**
- Update `Stats` interface to match new structure
- Display new queue statistics in UI
- Show component status (scanner, checksum, uploader)
- Show filesystem events status (real-time monitoring active/inactive)

---

**GET /files (Enhanced - New Endpoint)**

Add endpoint to list files with their status:

```
GET /files?status=ready_for_upload&limit=100
```

```typescript
interface FileEntry {
  filepath: string;
  hostname: string;
  sha256: string | null;
  file_size: number;
  mtime: string;
  discovered_at: string;
  last_checked_at: string | null;
  status: 'discovered' | 'ready_for_upload' | 'completed' | 'unchanged';
  uploaded_at: string | null;
}

interface FileListResponse {
  files: FileEntry[];
  total: number;
  limit: number;
  offset: number;
}
```

**Electron Client Changes:**
- Add file list view (optional feature)
- Show pending uploads with status

---

**POST /scan/trigger (New Endpoint)**

Manually trigger a scan:

```
POST /scan/trigger
{
  "path": "/path/to/scan",  // optional, defaults to all registered paths
  "force": false  // if true, rescan all files regardless of mtime
}
```

**Electron Client Changes:**
- Add "Scan Now" button
- Trigger scan on demand

---

**WebSocket Support (Optional Future Enhancement)**

For real-time progress updates, consider adding WebSocket support:

```
ws://localhost:8765/ws/progress
```

**Events:**
```typescript
interface ProgressEvent {
  type: 'file_discovered' | 'checksum_calculated' | 'upload_started' | 'upload_progress' | 'upload_completed' | 'file_deleted';
  filepath: string;
  sha256?: string;
  progress?: number;  // 0-100 for chunked uploads
  timestamp: string;
}
```

**Electron Client Changes:**
- Connect to WebSocket on app start
- Update UI in real-time based on events
- No polling needed

---

### UI Changes Required

**1. Upload Progress Display**

Currently shows:
- File name
- Upload percentage
- Speed

With chunked uploads:
- Show chunk progress (e.g., "Chunk 25/50")
- Show overall progress (same as before)
- Handle longer uploads (large files)

---

**2. Queue Statistics**

Add new section to show:
- Pending checksum: X files
- Pending upload: X files
- Pending deletion: X files

---

**3. Component Status**

Add section showing:
- Scanner: Running ✓ (Filesystem events active)
- Checksum Calculator: Running ✓ (4 workers)
- Uploader: Running ✓ (4 workers)

---

**4. Configuration Window**

Add new settings:
- Scan interval (default: 60 seconds)
- Use filesystem events (default: true)
- Chunk size (default: 2 MB)
- Shutdown timeout (default: 10 seconds)

---

### Code Changes Needed

**renderer.ts:**

```typescript
// Update Stats interface
interface Stats {
  files: {
    total: number;
    discovered: number;
    ready_for_upload: number;
    completed: number;
    unchanged: number;
  };
  queues: {
    pending_checksum: { count: number; oldest_queued_at: string; };
    pending_upload: { count: number; oldest_queued_at: string; };
    pending_deletion: { count: number; oldest_deleted_at: string; };
  };
  components: {
    scanner: { status: string; filesystem_events_active: boolean; };
    checksum_calculator: { status: string; active_workers: number; };
    uploader: { status: string; active_workers: number; };
  };
}

// Update config interface
interface Config {
  scanner: {
    scan_interval: number;
    use_filesystem_events: boolean;
  };
  checksum_calculator: {
    parallel_workers: number;
  };
  uploader: {
    parallel_uploads: number;
    chunk_size_mb: number;
    timeout_seconds: number;
  };
  daemon: {
    shutdown_timeout: number;
  };
}
```

---

## Summary of Changes

### pp_assist (Daemon)
- ✅ Complete rewrite with 3-component architecture
- ✅ Add watchdog dependency
- ✅ Add aiosqlite dependency
- ✅ Implement SQLite queues
- ✅ Implement chunked upload client

### pp_server
- ✅ Add 4 new endpoints for chunked uploads
- ✅ Add 1 new endpoint for deletion notifications
- ✅ Add MongoDB collection for upload sessions
- ✅ Add background cleanup job for expired uploads
- ✅ Update S3 integration to use multipart uploads

### pp_client
- ⚠️ **Decision needed:** Deprecate, rewrite, or keep with chunked upload support?
- **Recommendation:** Deprecate in favor of pp_assist daemon

### Electron Client
- ✅ Update Stats interface (add queues and components)
- ✅ Add new UI sections (queues, component status)
- ✅ Update Config interface (add new settings)
- ✅ Add "Scan Now" button
- ✅ Handle chunked upload progress display
- ⚠️ Optional: Add WebSocket support for real-time updates

---

## Implementation Order

**Phase 1: Server Changes** (1-2 weeks)
1. Implement chunked upload endpoints
2. Implement deletion notification endpoint
3. Add MongoDB schema changes
4. Add S3 multipart upload integration
5. Add cleanup job for expired uploads
6. Test with curl/Postman

**Phase 2: pp_assist Daemon** (2-3 weeks)
1. Implement Component 1 (Scanner)
2. Implement Component 2 (Checksum Calculator)
3. Implement Component 3 (Uploader with chunked upload)
4. Implement SQLite queue system
5. Add configuration management
6. Test end-to-end

**Phase 3: Electron Client** (1 week)
1. Update Stats interface
2. Update Config interface
3. Add new UI sections
4. Test with new daemon
5. Update documentation

**Phase 4: pp_client** (Decision + 1 week if keeping)
1. Decide on deprecation vs. rewrite
2. If keeping: Add chunked upload support
3. Update documentation
4. Add deprecation warnings

**Total Estimated Time:** 4-6 weeks for full implementation
