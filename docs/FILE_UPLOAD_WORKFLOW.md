# File Upload Workflow - Content Deduplication

## Overview

PutPlace uses a two-phase approach for file uploads with automatic deduplication based on SHA256 hashes:

1. **Phase 1: Metadata Registration** - Client sends file metadata (including SHA256)
2. **Phase 2: Conditional Upload** - Server indicates if file content upload is needed

This approach prevents unnecessary file transfers when the server already has the file content.

## How It Works

### Client Workflow

```
1. Client scans file and calculates SHA256 hash
2. Client sends metadata to POST /put_file
3. Server responds with upload_required flag:
   - upload_required: true  → File is unique, upload needed
   - upload_required: false → File already exists, skip upload
4. If upload_required: Client uploads to POST /upload_file/{sha256}
5. Server verifies SHA256 matches and marks file as uploaded
```

### Server Logic

**POST /put_file** (Metadata Registration):
```python
# Check if we already have this file content
has_content = await db.has_file_content(sha256)

if has_content:
    return {upload_required: false}  # Deduplication!
else:
    return {upload_required: true, upload_url: "/upload_file/{sha256}"}
```

**POST /upload_file/{sha256}** (File Upload):
```python
# Verify uploaded content matches claimed SHA256
calculated_hash = hashlib.sha256(content).hexdigest()
if calculated_hash != sha256:
    raise HTTPException("Hash mismatch")

# Mark file as uploaded in database
await db.mark_file_uploaded(sha256, hostname, filepath)
```

## API Examples

### Example 1: First Upload (Unique File)

**Step 1: Register Metadata**
```bash
curl -X POST http://localhost:8000/put_file \
  -H "Content-Type: application/json" \
  -d '{
    "filepath": "/var/log/app.log",
    "hostname": "server01",
    "ip_address": "192.168.1.100",
    "sha256": "abc123...",
    "file_size": 2048,
    "file_mode": 33188,
    "file_uid": 1000,
    "file_gid": 1000,
    "file_mtime": 1609459200.0,
    "file_atime": 1609459200.0,
    "file_ctime": 1609459200.0
  }'
```

**Response:**
```json
{
  "filepath": "/var/log/app.log",
  "hostname": "server01",
  "sha256": "abc123...",
  "upload_required": true,
  "upload_url": "/upload_file/abc123...",
  "has_file_content": false,
  "id": "65f1234..."
}
```

**Step 2: Upload File Content** (because upload_required=true)
```bash
curl -X POST "http://localhost:8000/upload_file/abc123...?hostname=server01&filepath=/var/log/app.log" \
  -F "file=@/var/log/app.log"
```

**Response:**
```json
{
  "message": "File uploaded successfully",
  "sha256": "abc123...",
  "size": 2048,
  "hostname": "server01",
  "filepath": "/var/log/app.log"
}
```

### Example 2: Duplicate File (Already Exists)

**Step 1: Register Metadata**
```bash
curl -X POST http://localhost:8000/put_file \
  -H "Content-Type: application/json" \
  -d '{
    "filepath": "/home/user/copy_of_app.log",
    "hostname": "server02",
    "sha256": "abc123...",
    ...
  }'
```

**Response:**
```json
{
  "filepath": "/home/user/copy_of_app.log",
  "hostname": "server02",
  "sha256": "abc123...",
  "upload_required": false,
  "upload_url": null,
  "has_file_content": false,
  "id": "65f5678..."
}
```

**Step 2: Skip Upload** (because upload_required=false)
Client detects `upload_required: false` and skips the upload entirely!

## Database Schema

### FileMetadata Document

```javascript
{
  // Core metadata
  "filepath": "/var/log/app.log",
  "hostname": "server01",
  "ip_address": "192.168.1.100",
  "sha256": "abc123...",

  // File stats
  "file_size": 2048,
  "file_mode": 33188,
  "file_uid": 1000,
  "file_gid": 1000,
  "file_mtime": 1609459200.0,
  "file_atime": 1609459200.0,
  "file_ctime": 1609459200.0,

  // Content tracking (NEW)
  "has_file_content": true,           // Whether server has file content
  "file_uploaded_at": "2024-01-15...", // When content was uploaded

  // Timestamps
  "created_at": "2024-01-15..."
}
```

## Client Implementation

The client should:

1. ✅ Calculate SHA256 before contacting server
2. ✅ Send metadata to `/put_file`
3. ✅ Check `upload_required` in response
4. ✅ Only upload file if `upload_required == true`
5. ✅ Use the provided `upload_url`

**Example Client Logic:**
```python
# Step 1: Calculate and send metadata
sha256 = calculate_sha256(filepath)
stats = get_file_stats(filepath)
metadata = {
    "filepath": filepath,
    "hostname": hostname,
    "sha256": sha256,
    **stats
}

response = httpx.post(f"{api_url}/put_file", json=metadata)
data = response.json()

# Step 2: Upload file only if needed
if data["upload_required"]:
    with open(filepath, "rb") as f:
        files = {"file": f}
        params = {"hostname": hostname, "filepath": filepath}
        upload_response = httpx.post(
            f"{api_url}/upload_file/{sha256}",
            files=files,
            params=params
        )
    print(f"✓ File uploaded: {filepath}")
else:
    print(f"✓ File already exists (deduplicated): {filepath}")
```

## Benefits

### 1. Bandwidth Savings
- Duplicate files across multiple hosts only uploaded once
- Same file from different locations → single transfer

### 2. Storage Efficiency
- Single copy of file content per unique SHA256
- Metadata stored separately for each location

### 3. Fast Operations
- Check for existing content is a simple database query
- Skip upload for common files (system libraries, config files, etc.)

### 4. Integrity Verification
- Server verifies SHA256 of uploaded content
- Prevents corruption or tampering
- Ensures uploaded file matches metadata

## Security Considerations

✅ **SHA256 Verification**: Uploaded content must match claimed hash
✅ **No Trust on First Contact**: Server verifies every upload
✅ **Metadata Binding**: Upload requires matching hostname+filepath+SHA256
⚠️ **TODO**: Add authentication/authorization for uploads
⚠️ **TODO**: Add file size limits
⚠️ **TODO**: Add storage quotas per user/hostname

## Storage Options

The current implementation marks files as uploaded but doesn't persist the actual content. You can extend this:

### Option 1: Local Filesystem
```python
storage_path = Path(f"/var/putplace/files/{sha256[:2]}/{sha256}")
storage_path.parent.mkdir(parents=True, exist_ok=True)
with open(storage_path, "wb") as f:
    f.write(content)
```

### Option 2: S3/Object Storage
```python
import boto3
s3 = boto3.client('s3')
s3.put_object(
    Bucket='putplace-files',
    Key=f'files/{sha256}',
    Body=content
)
```

### Option 3: Content-Addressable Storage (CAS)
- Use existing CAS solutions (Perkeep, Git-LFS, etc.)
- Store files by their SHA256
- Natural deduplication

## Monitoring & Metrics

Track these metrics:

- **Deduplication Rate**: % of files that skip upload
- **Upload Success Rate**: successful uploads / total attempts
- **Storage Savings**: Total bytes saved by deduplication
- **Average File Size**: Track typical file sizes
- **Hash Collisions**: Should be zero (monitor anyway)

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/put_file` | POST | Register file metadata, get upload decision |
| `/upload_file/{sha256}` | POST | Upload file content (if required) |
| `/get_file/{sha256}` | GET | Retrieve file metadata by SHA256 |
| `/health` | GET | Health check with database status |

## Future Enhancements

- [ ] Chunked uploads for large files
- [ ] Resume interrupted uploads
- [ ] Download endpoint to retrieve file content
- [ ] File expiration/TTL
- [ ] Storage backend plugins
- [ ] Compression before storage
- [ ] Encryption at rest
- [ ] Access control lists (ACLs)
- [ ] Audit logging
