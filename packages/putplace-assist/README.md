# PutPlace Assist

Local assistant daemon for file uploads to the PutPlace server.

## Overview

PutPlace Assist is a local FastAPI daemon that runs on client machines to assist with file uploads. It provides:

- **Path Registration**: Register directories to be scanned and uploaded
- **File Watching**: Automatic detection of file changes via watchdog
- **SHA256 Checksums**: Automatic calculation and tracking of file hashes
- **Upload Queue**: Background file uploads with retry logic
- **Real-time Activity**: SSE and WebSocket endpoints for monitoring
- **SQLite Database**: Local tracking of files, upload status, and activity

## Installation

```bash
pip install putplace-assist
```

## Quick Start

### Start the Daemon

```bash
# Start in background
ppassist start

# Start in foreground (for development)
ppassist start --foreground

# Check status
ppassist status

# Stop daemon
ppassist stop
```

### Using the API

Register a path:
```bash
curl -X POST http://localhost:8765/paths \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/watch", "recursive": true}'
```

Add exclude patterns:
```bash
curl -X POST http://localhost:8765/excludes \
  -H "Content-Type: application/json" \
  -d '{"pattern": "*.log"}'
```

Configure remote server:
```bash
curl -X POST http://localhost:8765/servers \
  -H "Content-Type: application/json" \
  -d '{"name": "production", "url": "https://app.putplace.org", "username": "user", "password": "pass"}'
```

Trigger uploads:
```bash
curl -X POST http://localhost:8765/uploads \
  -H "Content-Type: application/json" \
  -d '{"upload_content": true}'
```

Monitor activity (SSE):
```bash
curl http://localhost:8765/activity/stream
```

## API Endpoints

### Status
- `GET /` - Root endpoint
- `GET /health` - Health check
- `GET /status` - Daemon status

### Paths
- `GET /paths` - List registered paths
- `POST /paths` - Register a new path
- `GET /paths/{id}` - Get path details
- `DELETE /paths/{id}` - Unregister a path
- `POST /paths/{id}/scan` - Trigger rescan

### Excludes
- `GET /excludes` - List exclude patterns
- `POST /excludes` - Add exclude pattern
- `DELETE /excludes/{id}` - Remove pattern

### Files
- `GET /files` - List tracked files
- `GET /files/{id}` - Get file details
- `DELETE /files/{id}` - Remove from tracking
- `GET /files/stats` - File statistics

### Servers
- `GET /servers` - List configured servers
- `POST /servers` - Add server configuration
- `DELETE /servers/{id}` - Remove server
- `POST /servers/{id}/default` - Set as default

### Uploads
- `POST /uploads` - Trigger file uploads
- `GET /uploads/status` - Upload status
- `GET /uploads/queue` - Queue status

### Activity
- `GET /activity` - Recent activity events
- `GET /activity/stream` - SSE event stream
- `WS /ws/activity` - WebSocket events

### Scanning
- `POST /scan` - Full scan of all paths

## Configuration

Configuration can be set via:
1. Environment variables (prefix: `PPASSIST_`)
2. TOML config file (`ppassist.toml`)
3. Command-line defaults

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PPASSIST_SERVER_HOST` | `127.0.0.1` | Host to bind to |
| `PPASSIST_SERVER_PORT` | `8765` | Port to bind to |
| `PPASSIST_SERVER_LOG_LEVEL` | `INFO` | Logging level |
| `PPASSIST_DB_PATH` | `~/.local/share/putplace/assist.db` | Database path |
| `PPASSIST_WATCHER_ENABLED` | `true` | Enable file watching |

### Config File Example

Create `~/.config/putplace/ppassist.toml`:

```toml
[server]
host = "127.0.0.1"
port = 8765
log_level = "INFO"

[database]
path = "~/.local/share/putplace/assist.db"

[watcher]
enabled = true
debounce_seconds = 2.0

[uploader]
parallel_uploads = 4
retry_attempts = 3
```

## Development

```bash
# Install dev dependencies
uv pip install -e '.[dev]'

# Run tests
invoke test

# Run linter
invoke lint

# Format code
invoke format

# Run all checks
invoke check

# Run development server
invoke serve
```

## License

MIT
