# API Reference

Complete REST API reference for PutPlace server.

## Base URL

```
http://localhost:8000
```

For production, use your server's domain:
```
https://putplace.example.com
```

## Authentication

All endpoints except `/`, `/health`, `/api/register`, and `/api/login` require authentication.

PutPlace supports **two authentication methods**:

### Method 1: JWT Bearer Token (Recommended)

Login with username/password to get a JWT token:

```bash
# 1. Login to get token
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'

# Returns: {"access_token": "eyJ0eXAi...", "token_type": "bearer"}

# 2. Use token in Authorization header
curl -H "Authorization: Bearer eyJ0eXAi..." http://localhost:8000/api/my_files
```

### Method 2: API Key Header (Advanced)

For backwards compatibility and advanced use cases:

```http
X-API-Key: your-api-key-here
```

**Example:**
```bash
curl -H "X-API-Key: a1b2c3d4e5f6..." http://localhost:8000/api_keys
```

## Interactive Documentation

PutPlace provides automatic interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Endpoints

### Health Endpoints

#### GET /

Root endpoint - Returns basic API information.

**Authentication:** Not required

**Response:**
```json
{
  "message": "PutPlace API - File Metadata Storage",
  "status": "running"
}
```

**Example:**
```bash
curl http://localhost:8000/
```

---

#### GET /health

Health check endpoint with database connectivity check.

**Authentication:** Not required

**Response (Healthy):**
```json
{
  "status": "healthy",
  "database": {
    "status": "connected",
    "type": "mongodb"
  }
}
```

**Response (Degraded):**
```json
{
  "status": "degraded",
  "database": {
    "status": "disconnected",
    "type": "mongodb"
  }
}
```

**Example:**
```bash
curl http://localhost:8000/health
```

### File Endpoints

#### POST /put_file

Store file metadata in database and determine if file upload is needed.

**Authentication:** Required

**Request Body:**
```json
{
  "filepath": "/var/www/html/index.html",
  "hostname": "web-server-01",
  "ip_address": "192.168.1.100",
  "sha256": "a1b2c3d4e5f6...",
  "file_size": 1234,
  "file_mode": 33188,
  "file_uid": 33,
  "file_gid": 33,
  "file_mtime": 1609459200.0,
  "file_atime": 1609459200.0,
  "file_ctime": 1609459200.0,
  "is_symlink": false,
  "link_target": null
}
```

**Response (Upload Required):**
```json
{
  "_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "filepath": "/var/www/html/index.html",
  "hostname": "web-server-01",
  "ip_address": "192.168.1.100",
  "sha256": "a1b2c3d4e5f6...",
  "file_size": 1234,
  "file_mode": 33188,
  "file_uid": 33,
  "file_gid": 33,
  "file_mtime": 1609459200.0,
  "file_atime": 1609459200.0,
  "file_ctime": 1609459200.0,
  "is_symlink": false,
  "link_target": null,
  "has_file_content": false,
  "file_uploaded_at": null,
  "upload_required": true,
  "upload_url": "/upload_file/a1b2c3d4e5f6..."
}
```

**Response (Upload Not Required):**
```json
{
  "_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  ...
  "upload_required": false,
  "upload_url": null
}
```

**Status Codes:**
- `201 Created` - Metadata stored successfully
- `400 Bad Request` - Invalid request body
- `401 Unauthorized` - Missing or invalid authentication
- `500 Internal Server Error` - Database error

**Example:**
```bash
curl -X POST http://localhost:8000/put_file \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "filepath": "/var/www/html/index.html",
    "hostname": "web-server-01",
    "ip_address": "192.168.1.100",
    "sha256": "abc123...",
    "file_size": 1234,
    "file_mode": 33188,
    "file_uid": 33,
    "file_gid": 33,
    "file_mtime": 1609459200.0,
    "file_atime": 1609459200.0,
    "file_ctime": 1609459200.0,
    "is_symlink": false
  }'
```

**Deduplication Logic:**
- If server already has file content for this SHA256: `upload_required=false`
- If this is a new file: `upload_required=true`, client should call `/upload_file/{sha256}`

---

#### POST /upload_file/{sha256}

Upload actual file content for previously registered metadata.

**Authentication:** Required

**Path Parameters:**
- `sha256` (string, required): SHA256 hash of the file (64 characters)

**Query Parameters:**
- `hostname` (string, required): Hostname where file is located
- `filepath` (string, required): Full path to the file

**Request Body:**
- Multipart form data with file upload
- Field name: `file`

**Response:**
```json
{
  "message": "File uploaded successfully",
  "sha256": "a1b2c3d4e5f6...",
  "file_size": 1234,
  "hostname": "web-server-01",
  "filepath": "/var/www/html/index.html"
}
```

**Status Codes:**
- `200 OK` - File uploaded successfully
- `400 Bad Request` - Invalid SHA256 or hash mismatch
- `401 Unauthorized` - Missing or invalid authentication
- `404 Not Found` - No metadata found for this file
- `500 Internal Server Error` - Storage error

**Example:**
```bash
curl -X POST "http://localhost:8000/upload_file/abc123...?hostname=web-server-01&filepath=/var/www/html/index.html" \
  -H "X-API-Key: your-api-key" \
  -F "file=@/path/to/local/file.txt"
```

**Validation:**
- Server calculates SHA256 of uploaded content
- If calculated hash doesn't match provided SHA256: `400 Bad Request`

**Storage:**
- File stored using configured backend (local or S3)
- Database updated with `has_file_content=true` and `file_uploaded_at` timestamp

---

#### GET /get_file/{sha256}

Retrieve file metadata by SHA256 hash.

**Authentication:** Required

**Path Parameters:**
- `sha256` (string, required): SHA256 hash of the file (64 characters)

**Response:**
```json
{
  "_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "filepath": "/var/www/html/index.html",
  "hostname": "web-server-01",
  "ip_address": "192.168.1.100",
  "sha256": "a1b2c3d4e5f6...",
  "file_size": 1234,
  "file_mode": 33188,
  "file_uid": 33,
  "file_gid": 33,
  "file_mtime": 1609459200.0,
  "file_atime": 1609459200.0,
  "file_ctime": 1609459200.0,
  "is_symlink": false,
  "link_target": null,
  "has_file_content": true,
  "file_uploaded_at": "2025-01-15T10:31:00Z"
}
```

**Status Codes:**
- `200 OK` - File found
- `400 Bad Request` - Invalid SHA256 format
- `401 Unauthorized` - Missing or invalid authentication
- `404 Not Found` - File not found
- `500 Internal Server Error` - Database error

**Example:**
```bash
curl -H "X-API-Key: your-api-key" \
  http://localhost:8000/get_file/abc123...
```

**Note:** This returns the FIRST matching file. If multiple files with the same SHA256 exist (duplicates on different hosts/paths), only one is returned. Use `/api/clones/{sha256}` to get all files with the same hash.

---

#### GET /api/clones/{sha256}

Get all files with identical SHA256 hash across all users (clone detection).

**Authentication:** Required (JWT token)

**Path Parameters:**
- `sha256` (string, required): SHA256 hash of the file (64 characters)

**Response:**
```json
[
  {
    "_id": "65a1b2c3d4e5f6g7h8i9j0k1",
    "filepath": "/var/www/html/index.html",
    "hostname": "web-server-01",
    "ip_address": "192.168.1.100",
    "sha256": "a1b2c3d4e5f6...",
    "file_size": 1234,
    "file_mode": 33188,
    "file_uid": 1000,
    "file_gid": 1000,
    "file_mtime": 1705318200.0,
    "file_atime": 1705320000.0,
    "file_ctime": 1705316400.0,
    "has_file_content": true,
    "file_uploaded_at": "2025-01-15T10:31:00Z",
    "created_at": "2025-01-15T10:30:00Z",
    "uploaded_by_user_id": "user123"
  },
  {
    "_id": "65a1b2c3d4e5f6g7h8i9j0k2",
    "filepath": "/backup/html/index.html",
    "hostname": "backup-server",
    "ip_address": "192.168.1.101",
    "sha256": "a1b2c3d4e5f6...",
    "file_size": 1234,
    "file_mode": 33188,
    "file_uid": 1001,
    "file_gid": 1001,
    "file_mtime": 1705318300.0,
    "file_atime": 1705320100.0,
    "file_ctime": 1705316500.0,
    "has_file_content": false,
    "file_uploaded_at": null,
    "created_at": "2025-01-15T10:35:00Z",
    "uploaded_by_user_id": "user456"
  }
]
```

**Status Codes:**
- `200 OK` - Success (returns empty array if no files found)
- `400 Bad Request` - Invalid SHA256 format
- `401 Unauthorized` - Missing or invalid JWT token
- `500 Internal Server Error` - Database error

**Example:**
```bash
curl -H "Authorization: Bearer your-jwt-token" \
  http://localhost:8000/api/clones/abc123...
```

**Sorting:**
- Files are sorted with "epoch file" (first uploaded with content) first
- Files with content are prioritized over metadata-only files
- Among files with content, earliest upload time comes first

**Use Cases:**
- **Deduplication Discovery**: Find all locations where identical file exists
- **Epoch File Identification**: Identify the canonical copy of a file
- **Cross-User File Discovery**: Find file content uploaded by other users
- **Storage Optimization**: Identify duplicate files for cleanup

---

#### GET /api/my_files

Get all files uploaded by the current user.

**Authentication:** Required (JWT token)

**Query Parameters:**
- `limit` (integer, optional): Maximum number of files to return (default: 100)
- `skip` (integer, optional): Number of files to skip for pagination (default: 0)

**Response:**
```json
[
  {
    "_id": "65a1b2c3d4e5f6g7h8i9j0k1",
    "filepath": "/var/www/html/index.html",
    "hostname": "web-server-01",
    "ip_address": "192.168.1.100",
    "sha256": "a1b2c3d4e5f6...",
    "file_size": 1234,
    "file_mode": 33188,
    "file_uid": 1000,
    "file_gid": 1000,
    "file_mtime": 1705318200.0,
    "file_atime": 1705320000.0,
    "file_ctime": 1705316400.0,
    "has_file_content": true,
    "file_uploaded_at": "2025-01-15T10:31:00Z",
    "created_at": "2025-01-15T10:30:00Z",
    "uploaded_by_user_id": "user123"
  }
]
```

**Status Codes:**
- `200 OK` - Success (returns empty array if no files found)
- `401 Unauthorized` - Missing or invalid JWT token
- `500 Internal Server Error` - Database error

**Example:**
```bash
# Get first 100 files
curl -H "Authorization: Bearer your-jwt-token" \
  http://localhost:8000/api/my_files

# Get next 100 files (pagination)
curl -H "Authorization: Bearer your-jwt-token" \
  "http://localhost:8000/api/my_files?limit=100&skip=100"
```

**Sorting:**
- Files are sorted by creation time (most recent first)

### Authentication Endpoints

#### POST /api_keys

Create a new API key.

**Authentication:** Required (existing API key needed)

**Note:** For creating the first API key, use the bootstrap script:
```bash
python -m putplace.scripts.create_api_key
```

**Request Body:**
```json
{
  "name": "web-server-02",
  "description": "API key for web server 02"
}
```

**Response:**
```json
{
  "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6...",
  "_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "name": "web-server-02",
  "description": "API key for web server 02",
  "created_at": "2025-01-15T10:00:00Z",
  "is_active": true
}
```

**Status Codes:**
- `201 Created` - API key created successfully
- `400 Bad Request` - Invalid request body
- `401 Unauthorized` - Missing or invalid authentication
- `500 Internal Server Error` - Database error

**Example:**
```bash
curl -X POST http://localhost:8000/api_keys \
  -H "X-API-Key: your-existing-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "web-server-02",
    "description": "API key for production web server 02"
  }'
```

**Important:** The `api_key` field in the response is the ONLY time the actual API key is shown. Save it immediately!

---

#### GET /api_keys

List all API keys (without showing actual keys).

**Authentication:** Required

**Response:**
```json
[
  {
    "_id": "65a1b2c3d4e5f6g7h8i9j0k1",
    "name": "web-server-01",
    "description": "API key for web server 01",
    "created_at": "2025-01-15T09:00:00Z",
    "last_used_at": "2025-01-15T11:30:00Z",
    "is_active": true
  },
  {
    "_id": "65a1b2c3d4e5f6g7h8i9j0k2",
    "name": "web-server-02",
    "description": "API key for web server 02",
    "created_at": "2025-01-15T10:00:00Z",
    "last_used_at": null,
    "is_active": true
  }
]
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Missing or invalid authentication
- `500 Internal Server Error` - Database error

**Example:**
```bash
curl -H "X-API-Key: your-api-key" \
  http://localhost:8000/api_keys
```

---

#### PUT /api_keys/{key_id}/revoke

Revoke (deactivate) an API key without deleting it.

**Authentication:** Required

**Path Parameters:**
- `key_id` (string, required): MongoDB ObjectId of the API key

**Response:**
```json
{
  "message": "API key 65a1b2c3d4e5f6g7h8i9j0k1 revoked successfully"
}
```

**Status Codes:**
- `200 OK` - API key revoked
- `401 Unauthorized` - Missing or invalid authentication
- `404 Not Found` - API key not found
- `500 Internal Server Error` - Database error

**Example:**
```bash
curl -X PUT http://localhost:8000/api_keys/65a1b2c3d4e5f6g7h8i9j0k1/revoke \
  -H "X-API-Key: your-api-key"
```

**Effect:** The key is marked as `is_active=false` and can no longer be used for authentication. Metadata is retained for audit purposes.

---

#### DELETE /api_keys/{key_id}

Permanently delete an API key.

**Authentication:** Required

**Path Parameters:**
- `key_id` (string, required): MongoDB ObjectId of the API key

**Response:**
```json
{
  "message": "API key 65a1b2c3d4e5f6g7h8i9j0k1 deleted successfully"
}
```

**Status Codes:**
- `200 OK` - API key deleted
- `401 Unauthorized` - Missing or invalid authentication
- `404 Not Found` - API key not found
- `500 Internal Server Error` - Database error

**Example:**
```bash
curl -X DELETE http://localhost:8000/api_keys/65a1b2c3d4e5f6g7h8i9j0k1 \
  -H "X-API-Key: your-api-key"
```

**Warning:** This permanently deletes the key. Consider using `/api_keys/{key_id}/revoke` instead to retain audit trail.

## Data Models

### FileMetadata

File metadata submitted by client.

```json
{
  "filepath": "string (required)",
  "hostname": "string (required)",
  "ip_address": "string (required)",
  "sha256": "string (required, 64 chars)",
  "file_size": "integer (required)",
  "file_mode": "integer (required)",
  "file_uid": "integer (required)",
  "file_gid": "integer (required)",
  "file_mtime": "float (required)",
  "file_atime": "float (required)",
  "file_ctime": "float (required)",
  "is_symlink": "boolean (required)",
  "link_target": "string or null (required)"
}
```

**Field Descriptions:**
- `filepath` - Full path to the file
- `hostname` - Hostname where file is located
- `ip_address` - IP address of the host
- `sha256` - SHA256 hash of file content (64 hex characters)
- `file_size` - File size in bytes
- `file_mode` - Unix file mode/permissions (integer, e.g., 33188 for rw-r--r--)
- `file_uid` - File owner user ID (integer)
- `file_gid` - File group ID (integer)
- `file_mtime` - Last modification time (Unix timestamp)
- `file_atime` - Last access time (Unix timestamp)
- `file_ctime` - Creation/metadata change time (Unix timestamp)
- `is_symlink` - Whether file is a symbolic link
- `link_target` - Target path if symlink, null otherwise

### FileMetadataResponse

File metadata returned from server (includes server-generated fields).

```json
{
  "_id": "string (MongoDB ObjectId)",
  "filepath": "string",
  "hostname": "string",
  "ip_address": "string",
  "sha256": "string",
  "file_size": "integer",
  "file_mode": "integer",
  "file_uid": "integer",
  "file_gid": "integer",
  "file_mtime": "float",
  "file_atime": "float",
  "file_ctime": "float",
  "is_symlink": "boolean",
  "link_target": "string or null",
  "has_file_content": "boolean",
  "file_uploaded_at": "datetime or null"
}
```

**Additional Fields:**
- `_id` - MongoDB document ID
- `has_file_content` - Whether server has the actual file content
- `file_uploaded_at` - Timestamp when file was uploaded (null if not uploaded)

### FileMetadataUploadResponse

Response from POST /put_file (includes upload requirement info).

```json
{
  "_id": "string",
  "filepath": "string",
  "hostname": "string",
  "ip_address": "string",
  "sha256": "string",
  "file_size": "integer",
  "file_mode": "integer",
  "file_uid": "integer",
  "file_gid": "integer",
  "file_mtime": "float",
  "file_atime": "float",
  "file_ctime": "float",
  "is_symlink": "boolean",
  "link_target": "string or null",
  "has_file_content": "boolean",
  "file_uploaded_at": "datetime or null",
  "upload_required": "boolean",
  "upload_url": "string or null"
}
```

**Additional Fields:**
- `upload_required` - Whether client should upload file content
- `upload_url` - URL to upload file to (null if upload not required)

### APIKeyCreate

Request body for creating API key.

```json
{
  "name": "string (required, 1-100 chars)",
  "description": "string or null (optional)"
}
```

### APIKeyResponse

Response when creating API key (includes actual key).

```json
{
  "api_key": "string (64 hex chars)",
  "_id": "string (MongoDB ObjectId)",
  "name": "string",
  "description": "string or null",
  "created_at": "datetime",
  "is_active": "boolean"
}
```

**Warning:** This is the ONLY time `api_key` is shown. Save it immediately!

### APIKeyInfo

API key metadata (without actual key).

```json
{
  "_id": "string (MongoDB ObjectId)",
  "name": "string",
  "description": "string or null",
  "created_at": "datetime",
  "last_used_at": "datetime or null",
  "is_active": "boolean"
}
```

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": "Error message"
}
```

### Common Error Codes

**400 Bad Request:**
- Invalid request body
- Invalid SHA256 format
- SHA256 hash mismatch during upload

**401 Unauthorized:**
- Missing X-API-Key header
- Invalid API key
- Revoked API key

**404 Not Found:**
- File not found
- API key not found

**500 Internal Server Error:**
- Database connection failure
- Storage backend error
- Unexpected server error

### Error Examples

**Missing API Key:**
```json
{
  "detail": "Not authenticated"
}
```

**Invalid API Key:**
```json
{
  "detail": "Invalid API key"
}
```

**File Not Found:**
```json
{
  "detail": "File with SHA256 abc123... not found"
}
```

**SHA256 Mismatch:**
```json
{
  "detail": "File content SHA256 (def456...) does not match provided hash (abc123...)"
}
```

## Rate Limiting

PutPlace does not currently implement rate limiting. Consider implementing this at the reverse proxy level (nginx, traefik) or using a service like Cloudflare.

**Example nginx rate limiting:**
```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location / {
    limit_req zone=api burst=20 nodelay;
    proxy_pass http://127.0.0.1:8000;
}
```

## Best Practices

### 1. Always Check upload_required

After POST /put_file, check the `upload_required` field:

```python
response = post("/put_file", json=metadata)
if response["upload_required"]:
    upload_url = response["upload_url"]
    upload_file(upload_url, file_path)
else:
    print("File already exists, skipping upload")
```

### 2. Verify SHA256 Before Upload

Calculate SHA256 client-side before uploading:

```python
import hashlib

def calculate_sha256(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
```

### 3. Handle Authentication Errors

Retry with exponential backoff on 401 errors:

```python
import time

max_retries = 3
for attempt in range(max_retries):
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 401:
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
            continue
    break
```

### 4. Use Separate API Keys

Create separate API keys for each client/environment:

```bash
# Development
curl -X POST .../api_keys -d '{"name": "dev-server-01"}'

# Staging
curl -X POST .../api_keys -d '{"name": "staging-server-01"}'

# Production
curl -X POST .../api_keys -d '{"name": "prod-server-01"}'
```

### 5. Monitor last_used_at

Regularly check API key usage:

```bash
curl -H "X-API-Key: admin-key" http://localhost:8000/api_keys
```

Revoke unused keys:

```bash
curl -X PUT http://localhost:8000/api_keys/{key_id}/revoke \
  -H "X-API-Key: admin-key"
```

## Python Client Example

```python
import hashlib
import httpx

class PutPlaceClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key}

    def calculate_sha256(self, filepath: str) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def put_file(self, metadata: dict) -> dict:
        """Send file metadata to server."""
        url = f"{self.base_url}/put_file"
        response = httpx.post(url, json=metadata, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def upload_file(self, sha256: str, hostname: str, filepath: str, file_path: str):
        """Upload file content to server."""
        url = f"{self.base_url}/upload_file/{sha256}"
        params = {"hostname": hostname, "filepath": filepath}

        with open(file_path, "rb") as f:
            files = {"file": f}
            response = httpx.post(url, params=params, files=files, headers=self.headers)
            response.raise_for_status()

        return response.json()

    def scan_and_upload(self, filepath: str, hostname: str):
        """Scan file and upload if needed."""
        import os
        from datetime import datetime

        # Get file stats
        stat = os.stat(filepath)
        sha256 = self.calculate_sha256(filepath)

        # Prepare metadata
        metadata = {
            "filepath": filepath,
            "hostname": hostname,
            "ip_address": "127.0.0.1",
            "sha256": sha256,
            "file_size": stat.st_size,
            "file_mode": stat.st_mode,
            "file_uid": stat.st_uid,
            "file_gid": stat.st_gid,
            "file_mtime": stat.st_mtime,
            "file_atime": stat.st_atime,
            "file_ctime": stat.st_ctime,
            "is_symlink": os.path.islink(filepath),
            "link_target": os.readlink(filepath) if os.path.islink(filepath) else None,
        }

        # Send metadata
        response = self.put_file(metadata)

        # Upload if required
        if response["upload_required"]:
            print(f"Uploading {filepath}...")
            self.upload_file(sha256, hostname, filepath, filepath)
        else:
            print(f"File {filepath} already exists, skipping upload")

        return response

# Usage
client = PutPlaceClient("http://localhost:8000", "your-api-key")
result = client.scan_and_upload("/path/to/file.txt", "my-laptop")
```

## Next Steps

- [Client Guide](client-guide.md) - Using the command-line client
- [Authentication Guide](AUTHENTICATION.md) - JWT tokens and API keys
- [File Upload Workflow](FILE_UPLOAD_WORKFLOW.md) - Understanding the upload process
- [Configuration](configuration.md) - Server and client configuration
