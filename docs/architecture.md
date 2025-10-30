# Architecture

Technical architecture and design decisions for PutPlace.

## System Overview

PutPlace is a distributed file metadata storage and content deduplication system built with modern Python technologies.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Clients                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Server  │  │  Server  │  │  Server  │  │  Laptop  │   │
│  │    A     │  │    B     │  │    C     │  │          │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
└───────┼─────────────┼─────────────┼─────────────┼──────────┘
        │             │             │             │
        │    HTTPS + X-API-Key Authentication    │
        │             │             │             │
        └─────────────┼─────────────┼─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │      PutPlace API          │
        │      (FastAPI)             │
        │                            │
        │  ┌──────────────────────┐  │
        │  │  Authentication      │  │
        │  │  (API Keys)          │  │
        │  └──────────────────────┘  │
        │  ┌──────────────────────┐  │
        │  │  File Metadata       │  │
        │  │  Processing          │  │
        │  └──────────────────────┘  │
        │  ┌──────────────────────┐  │
        │  │  Deduplication       │  │
        │  │  Logic               │  │
        │  └──────────────────────┘  │
        └────┬──────────────────┬────┘
             │                  │
    ┌────────▼────────┐   ┌────▼────────┐
    │   MongoDB       │   │  Storage    │
    │   (Metadata)    │   │  Backend    │
    └─────────────────┘   └────┬────────┘
                               │
                        ┌──────┴──────┐
                        │             │
                   ┌────▼────┐   ┌───▼────┐
                   │  Local  │   │  AWS   │
                   │   FS    │   │   S3   │
                   └─────────┘   └────────┘
```

## Core Components

### 1. FastAPI Application (`main.py`)

**Purpose:** REST API server

**Key Features:**
- Asynchronous request handling
- Automatic OpenAPI documentation
- Dependency injection
- Lifespan event management

**Endpoints:**
- Health checks (`/`, `/health`)
- File operations (`/put_file`, `/upload_file/{sha256}`, `/get_file/{sha256}`)
- Authentication (`/api_keys/*`)

**Technology Stack:**
- **FastAPI**: Web framework
- **Uvicorn**: ASGI server (development)
- **Gunicorn**: Process manager (production)

### 2. Data Models (`models.py`)

**Purpose:** Pydantic models for validation and serialization

**Key Models:**
- `FileMetadata`: Client file metadata
- `FileMetadataResponse`: Server response with MongoDB ID
- `FileMetadataUploadResponse`: Response with upload requirement info
- `APIKeyCreate`: API key creation request
- `APIKeyResponse`: API key with actual key (shown once)
- `APIKeyInfo`: API key metadata (without key)

**Technology Stack:**
- **Pydantic v2**: Data validation and settings
- Type hints for IDE support
- JSON schema generation

### 3. Database Layer (`database.py`)

**Purpose:** MongoDB interface with async operations

**Key Features:**
- Async MongoDB operations using PyMongo async (native asyncio)
- Connection pooling
- Automatic index creation
- Error handling and logging

**Collections:**
- `file_metadata`: File metadata and upload status
- `api_keys`: API key hashes and metadata

**Indexes:**
- `file_metadata`:
  - `sha256` (unique)
  - `hostname + filepath` (compound)
  - `has_file_content`
- `api_keys`:
  - `key_hash` (unique)
  - `is_active`

**Technology Stack:**
- **PyMongo Async**: Native async MongoDB driver (PyMongo 4.10+)
- Direct asyncio implementation for better performance vs deprecated Motor library

### 4. Authentication (`auth.py`)

**Purpose:** API key authentication and management

**Key Features:**
- SHA256-hashed key storage
- Token generation with `secrets` module
- API key verification
- Usage tracking (`last_used_at`)

**Security:**
- Keys hashed before storage (SHA256)
- 64-character hex tokens (256 bits of entropy)
- Constant-time comparison
- Automatic timestamp updates

**Technology Stack:**
- **secrets**: Cryptographically secure random generation
- **hashlib**: SHA256 hashing
- **FastAPI Security**: Header-based authentication

### 5. Storage Backends (`storage.py`)

**Purpose:** Abstract storage with multiple backend implementations

**Architecture:**
```python
class StorageBackend(ABC):
    @abstractmethod
    async def store(sha256: str, content: bytes) -> bool
    @abstractmethod
    async def retrieve(sha256: str) -> Optional[bytes]
    @abstractmethod
    async def exists(sha256: str) -> bool
    @abstractmethod
    async def delete(sha256: str) -> bool
```

**Implementations:**

#### LocalStorage
- Stores files in local filesystem
- Directory structure: `{base_path}/{sha256[:2]}/{sha256}`
- 256 subdirectories for distribution
- Async file I/O with `aiofiles`

#### S3Storage
- Stores files in AWS S3
- Key structure: `{prefix}{sha256[:2]}/{sha256}`
- Supports multiple credential methods
- Async S3 operations with `aioboto3`

**Technology Stack:**
- **aiofiles**: Async file operations
- **aioboto3**: Async AWS SDK
- **Abstract Base Classes**: Enforces interface

### 6. Configuration (`config.py`)

**Purpose:** Centralized configuration management

**Key Features:**
- Environment variable loading
- `.env` file support
- Type validation with Pydantic
- Default values

**Configuration Groups:**
- API settings
- MongoDB settings
- Storage settings
- AWS settings (optional)
- Logging settings

**Technology Stack:**
- **Pydantic Settings**: Configuration management
- **python-dotenv**: `.env` file loading

### 7. Client (`ppclient.py`)

**Purpose:** Command-line client for file scanning

**Key Features:**
- Recursive directory scanning
- SHA256 calculation
- Pattern-based exclusion
- Progress display with Rich
- Configuration file support

**Workflow:**
1. Scan directory for files
2. Calculate file metadata (SHA256, size, permissions, etc.)
3. Send metadata to server
4. Upload file content if required
5. Display progress and results

**Technology Stack:**
- **httpx**: HTTP client with async support
- **rich**: Terminal output formatting
- **configargparse**: Unified CLI/env/file configuration

## Data Flow

### File Upload Workflow

```
┌─────────┐
│ Client  │
└────┬────┘
     │
     │ 1. Scan file
     │    - Calculate SHA256
     │    - Get file stats
     ▼
┌─────────────────┐
│  File Metadata  │
│  {filepath,     │
│   hostname,     │
│   sha256,       │
│   size, ...}    │
└────┬────────────┘
     │
     │ 2. POST /put_file
     │    Headers: X-API-Key
     ▼
┌─────────────┐
│  FastAPI    │
│  Server     │
└──────┬──────┘
       │
       │ 3. Verify API key
       ▼
┌──────────────┐
│ Auth System  │
│ - Hash key   │
│ - Check DB   │
│ - Update     │
│   last_used  │
└──────┬───────┘
       │
       │ 4. Store metadata
       ▼
┌──────────────┐     ┌─────────────┐
│  MongoDB     │────▶│  Check for  │
│              │     │  duplicate  │
└──────────────┘     │  (SHA256)   │
                     └──────┬──────┘
                            │
                ┌───────────┴───────────┐
                │                       │
            Exists                  New File
                │                       │
                ▼                       ▼
       ┌──────────────┐       ┌─────────────┐
       │  Response:   │       │  Response:  │
       │  upload_     │       │  upload_    │
       │  required    │       │  required   │
       │  = false     │       │  = true     │
       └──────────────┘       └──────┬──────┘
                                     │
                    ┌────────────────┘
                    │
                    │ 5. POST /upload_file/{sha256}
                    │    Multipart: file content
                    ▼
              ┌─────────────┐
              │  FastAPI    │
              │  Server     │
              └──────┬──────┘
                     │
                     │ 6. Verify SHA256 matches
                     ▼
              ┌─────────────┐
              │  Calculate  │
              │  SHA256 of  │
              │  uploaded   │
              │  content    │
              └──────┬──────┘
                     │
                     │ 7. Store file
                     ▼
              ┌─────────────┐
              │  Storage    │
              │  Backend    │
              └──────┬──────┘
                     │
              ┌──────┴──────┐
              │             │
              ▼             ▼
         ┌────────┐    ┌───────┐
         │ Local  │    │  S3   │
         │   FS   │    │       │
         └────────┘    └───────┘
              │
              │ 8. Mark uploaded
              ▼
         ┌──────────┐
         │ MongoDB  │
         │ Update   │
         │ has_file │
         │ _content │
         └──────────┘
```

## Design Decisions

### 1. Content-Addressable Storage (CAS)

**Decision:** Use SHA256 as file identifier

**Rationale:**
- Enables automatic deduplication
- Immutable file identification
- Collision-resistant (practically impossible)
- Standard in content-addressable systems

**Trade-offs:**
- Must calculate SHA256 for every file (CPU cost)
- Cannot store multiple versions of same content with different metadata
- Metadata stored separately from content

### 2. Two-Phase Upload Protocol

**Decision:** Separate metadata upload from content upload

**Rationale:**
- Allows server to check for duplicates before content upload
- Saves bandwidth for duplicate files
- Enables metadata tracking without content
- Supports different storage backends

**Trade-offs:**
- Two round trips instead of one
- More complex client logic
- Potential for metadata without content (if client fails)

### 3. Asynchronous Architecture

**Decision:** Use async/await throughout

**Rationale:**
- Better concurrency for I/O-bound operations
- Efficient handling of multiple clients
- Non-blocking database and storage operations
- Modern Python best practice

**Trade-offs:**
- More complex code (async/await everywhere)
- Requires async-compatible libraries
- Debugging can be more challenging

### 4. Abstract Storage Backend

**Decision:** Storage backend abstraction with multiple implementations

**Rationale:**
- Flexibility to switch storage backends
- Easy to add new backends
- Testability (mock storage)
- Separation of concerns

**Trade-offs:**
- Extra abstraction layer
- Slightly more complex codebase
- Must implement full interface for each backend

### 5. API Key Authentication

**Decision:** Header-based API key authentication

**Rationale:**
- Simple to implement and use
- Standard for API authentication
- No session management needed
- Stateless (scales horizontally)

**Trade-offs:**
- Less secure than OAuth2/JWT (no expiration)
- No fine-grained permissions (future enhancement)
- Keys must be rotated manually

### 6. MongoDB for Metadata

**Decision:** Use MongoDB instead of relational database

**Rationale:**
- Flexible schema (easy to add fields)
- Native JSON/Python dict mapping
- Good performance for document lookups
- Horizontal scaling with sharding

**Trade-offs:**
- No ACID transactions across documents (not needed for this use case)
- More complex aggregations than SQL
- Requires MongoDB infrastructure

### 7. Pydantic for Validation

**Decision:** Use Pydantic v2 for all data models

**Rationale:**
- Type safety and validation
- Automatic API documentation
- JSON schema generation
- IDE support with type hints

**Trade-offs:**
- Learning curve for Pydantic
- More verbose than plain dicts
- Runtime overhead (minimal)

## Scalability

### Horizontal Scaling

PutPlace is designed for horizontal scaling:

**Stateless API:**
- No session state
- All state in MongoDB
- Multiple API instances can run in parallel
- Load balancer distributes requests

**MongoDB Scaling:**
- Replica sets for read scaling
- Sharding for write scaling
- Indexes for query performance

**Storage Scaling:**
- Local: Limited to single server
- S3: Unlimited scaling

### Vertical Scaling

**API Server:**
- More CPU cores → More Gunicorn workers
- More RAM → Larger connection pools
- Formula: `workers = (4 × CPU cores) + 1`

**MongoDB:**
- More RAM → Larger working set in memory
- More CPU → Better query performance
- SSD → Faster I/O

### Performance Optimizations

1. **Database Indexes:**
   - SHA256 index for fast duplicate detection
   - Compound index on hostname+filepath
   - has_file_content index for upload checks

2. **Connection Pooling:**
   - MongoDB connection pool (default: 10-100)
   - HTTP client connection reuse

3. **Async I/O:**
   - Non-blocking database operations
   - Non-blocking storage operations
   - Concurrent request handling

4. **Content Distribution:**
   - 256 subdirectories for local storage
   - S3 automatic distribution

## Security Architecture

### Authentication

```
┌─────────┐
│ Client  │
└────┬────┘
     │
     │ X-API-Key: abc123...
     ▼
┌──────────────┐
│  FastAPI     │
│  Security    │
└──────┬───────┘
       │
       │ get_current_api_key()
       ▼
┌──────────────┐
│  Hash key    │
│  SHA256      │
└──────┬───────┘
       │
       │ key_hash
       ▼
┌──────────────┐
│  MongoDB     │
│  api_keys    │
└──────┬───────┘
       │
       │ Find by key_hash
       ▼
┌──────────────┐
│  Verify      │
│  is_active   │
└──────┬───────┘
       │
       │ Update last_used_at
       ▼
┌──────────────┐
│  Return      │
│  API key     │
│  metadata    │
└──────────────┘
```

### Data Protection

1. **API Keys:**
   - Hashed with SHA256 before storage
   - Never stored in plaintext
   - Shown only once during creation

2. **Transport:**
   - HTTPS enforced in production
   - TLS 1.2+ only
   - Strong cipher suites

3. **Storage:**
   - S3 encryption at rest
   - IAM roles instead of credentials
   - Bucket policies for access control

4. **File Content:**
   - SHA256 verification on upload
   - Content-addressable (immutable)
   - Duplicate detection prevents overwrite

## Testing Architecture

### Test Pyramid

```
         ┌────────┐
         │  E2E   │  (Integration tests)
         └────────┘
       ┌────────────┐
       │  API Tests │  (Endpoint tests)
       └────────────┘
     ┌──────────────────┐
     │   Unit Tests     │  (Component tests)
     └──────────────────┘
```

### Test Categories

1. **Unit Tests:**
   - `test_database.py`: Database operations
   - `test_auth.py`: Authentication logic
   - `test_storage.py`: Storage backends

2. **API Tests:**
   - `test_api.py`: API endpoints
   - Request/response validation
   - Authentication checks

3. **Client Tests:**
   - `test_client.py`: Client functionality
   - File scanning
   - Upload logic

### Test Coverage

Target: **100% code coverage**

Current coverage:
- Core: 100%
- API endpoints: 100%
- Authentication: 100%
- Storage backends: 100%
- Client: 95% (excludes __main__)

## Future Enhancements

### Planned Features

1. **Fine-grained Permissions:**
   - Read-only API keys
   - Namespace-based access control
   - Per-bucket permissions

2. **Chunked Uploads:**
   - Support for very large files (>5GB)
   - Resumable uploads
   - Parallel chunk uploads

3. **File Versioning:**
   - Track multiple versions of same file
   - Version history
   - Rollback capability

4. **Query API:**
   - Search by metadata
   - Time-based queries
   - Aggregation API

5. **Webhook Notifications:**
   - File upload events
   - Duplicate detection events
   - Error notifications

6. **Additional Storage Backends:**
   - Google Cloud Storage
   - Azure Blob Storage
   - MinIO (S3-compatible)

### Architectural Improvements

1. **Caching Layer:**
   - Redis for frequently accessed metadata
   - Reduce MongoDB load
   - Faster response times

2. **Message Queue:**
   - Async background processing
   - File content scanning
   - Thumbnail generation

3. **Metrics and Monitoring:**
   - Prometheus metrics
   - Grafana dashboards
   - Alert rules

4. **Rate Limiting:**
   - Per-API-key rate limits
   - Burst handling
   - Quotas

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [PyMongo Async Documentation](https://pymongo.readthedocs.io/en/stable/api/pymongo/asynchronous/index.html)
- [AWS S3 Documentation](https://docs.aws.amazon.com/s3/)
- [Content-Addressable Storage](https://en.wikipedia.org/wiki/Content-addressable_storage)
