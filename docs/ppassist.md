# PutPlace Assist

Local assistant daemon for automated file scanning and uploads to the PutPlace server.

## Overview

PutPlace Assist (`ppassist`) is a background daemon that runs on client machines to automate file uploads. It provides:

- **Path Registration**: Register directories to be scanned and uploaded
- **File Watching**: Automatic detection of file changes via watchdog
- **SHA256 Checksums**: Automatic calculation and tracking of file hashes
- **Upload Queue**: Background file uploads with retry logic
- **Real-time Activity**: SSE and WebSocket endpoints for monitoring
- **Web UI**: Browser-based dashboard for monitoring and control
- **SQLite Database**: Local tracking of files, upload status, and activity

## Offline Operation

PutPlace Assist is designed to work independently of the PutPlace server (`pp_server`). This makes it resilient to network issues and allows local-first operation.

### What Works Without pp_server

| Feature | Works Offline |
|---------|---------------|
| Directory watching | Yes |
| File scanning | Yes |
| Metadata collection | Yes |
| SHA256 checksum calculation | Yes |
| Local database storage | Yes |
| Activity logging | Yes |
| Path/exclude management | Yes |
| Web UI dashboard | Yes |
| All local API endpoints | Yes |

### What Requires pp_server

| Feature | Requires Server |
|---------|-----------------|
| Uploading file metadata | Yes |
| Uploading file content | Yes |
| Server authentication | Yes |

### How Offline Mode Works

1. **Queue Everything Locally**: When you register paths and trigger scans, ppassist stores all file metadata in its local SQLite database.

2. **Calculate Checksums**: The SHA256 background processor calculates checksums for all files, regardless of server availability.

3. **Queue Uploads**: Upload triggers queue files for upload. These remain queued until a server is configured and reachable.

4. **Sync When Available**: Once the server is available, queued uploads are processed automatically.

### Example: Starting Without a Server

```bash
# Start ppassist - works without pp_server
ppassist start

# Verify it's running
curl http://localhost:8765/health
# {"status": "ok", "version": "0.1.0", "database_ok": true}

# Register a path - files are scanned and stored locally
curl -X POST http://localhost:8765/paths \
  -H "Content-Type: application/json" \
  -d '{"path": "/home/user/Documents", "recursive": true}'

# Check status - shows local file tracking
curl http://localhost:8765/status
# {
#   "running": true,
#   "files_tracked": 1250,
#   "pending_sha256": 50,
#   "pending_uploads": 1250
# }
```

Files remain in `pending_uploads` until a server is configured and uploads are triggered.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Machine                           │
│                                                                 │
│  ┌───────────────┐        ┌─────────────────────────────────┐  │
│  │   pp_client    │        │         ppassist daemon         │  │
│  │  (CLI tool)   │───────▶│  ┌─────────────────────────────┐│  │
│  └───────────────┘  HTTP  │  │     FastAPI Server          ││  │
│                           │  │     (port 8765)             ││  │
│  ┌───────────────┐        │  └─────────────────────────────┘│  │
│  │   Web UI      │───────▶│  ┌──────────┐ ┌──────────────┐  │  │
│  │  (Browser)    │  HTTP  │  │ Watcher  │ │   Uploader   │──┼──┼──▶ PutPlace
│  └───────────────┘        │  │(watchdog)│ │   (queue)    │  │  │    Server
│                           │  └──────────┘ └──────────────┘  │  │
│                           │  ┌─────────────────────────────┐│  │
│                           │  │    SQLite Database          ││  │
│                           │  │  (paths, files, activity)   ││  │
│                           │  └─────────────────────────────┘│  │
│                           └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
pip install putplace-assist
```

Or install from source:

```bash
cd packages/putplace-assist
pip install -e '.[dev]'
```

## Quick Start

### Start the Daemon

```bash
# Start in background (daemonized)
ppassist start

# Start in foreground (for development/debugging)
ppassist start --foreground

# Check status
ppassist status

# Stop daemon
ppassist stop
```

### Access the Web UI

Once the daemon is running, open your browser to:

```
http://127.0.0.1:8765/ui
```

The web UI provides:
- Real-time statistics dashboard
- Live activity feed (via SSE)
- Path management (add/remove/scan)
- Upload progress monitoring

### Register a Path

Using the CLI:
```bash
pp_client --path /path/to/watch
```

Using curl:
```bash
curl -X POST http://127.0.0.1:8765/paths \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/watch", "recursive": true}'
```

### Trigger Uploads

```bash
# Upload metadata only
curl -X POST http://127.0.0.1:8765/uploads \
  -H "Content-Type: application/json" \
  -d '{"upload_content": false}'

# Upload metadata and file content
curl -X POST http://127.0.0.1:8765/uploads \
  -H "Content-Type: application/json" \
  -d '{"upload_content": true}'
```

## CLI Commands

### ppassist

The daemon control CLI:

```bash
ppassist [OPTIONS] COMMAND
```

#### Commands

| Command | Description |
|---------|-------------|
| `start` | Start the daemon |
| `stop` | Stop the daemon |
| `status` | Show daemon status |
| `restart` | Restart the daemon |

#### Start Options

| Option | Default | Description |
|--------|---------|-------------|
| `--foreground` | `false` | Run in foreground (don't daemonize) |
| `--host HOST` | `127.0.0.1` | Host to bind to |
| `--port PORT` | `8765` | Port to bind to |

### pp_client

The command-line client for interacting with the daemon:

```bash
pp_client [OPTIONS]
```

#### Options

| Option | Description |
|--------|-------------|
| `--path PATH` | Register a directory to watch |
| `--exclude PATTERN` | Add exclude pattern (repeatable) |
| `--no-recursive` | Don't scan recursively |
| `--upload` | Trigger uploads after registration |
| `--upload-content` | Upload file content (not just metadata) |
| `--wait` | Wait for uploads to complete |
| `--status` | Show daemon status |
| `--daemon-url URL` | Daemon URL (default: http://127.0.0.1:8765) |
| `--configure-server` | Configure remote server credentials |
| `--verbose, -v` | Stream activity events |

#### Examples

```bash
# Register a path and trigger upload
pp_client --path ~/Documents --upload --wait

# Add exclude patterns
pp_client --path ~/Projects --exclude "*.log" --exclude ".git" --exclude "node_modules"

# Check daemon status
pp_client --status

# Configure remote server
pp_client --configure-server

# Watch activity in real-time
pp_client --verbose
```

## Web UI

The web UI is accessible at `http://127.0.0.1:8765/ui` when the daemon is running.

### Features

#### Dashboard
- **Paths Watched**: Number of registered directories
- **Files Tracked**: Total files being monitored
- **Uploads Complete**: Successfully uploaded files
- **In Queue**: Files waiting to be uploaded

#### Watched Paths Panel
- View all registered paths
- Add new paths via modal dialog
- Remove paths
- Trigger manual rescans
- See file counts and last scan time

#### Live Activity Feed
- Real-time event stream via SSE
- Color-coded event types:
  - **Blue**: Upload events
  - **Green**: Successful operations
  - **Yellow**: Scan events
  - **Red**: Errors
- Timestamps and detailed messages

#### Upload Progress
- Active upload status
- Progress bars for in-progress uploads
- Queue size indicator

## API Reference

The daemon exposes a REST API on port 8765.

### Status Endpoints

#### GET /
Root endpoint with version info.

```bash
curl http://127.0.0.1:8765/
```

Response:
```json
{
  "name": "PutPlace Assist",
  "version": "0.1.0",
  "status": "running"
}
```

#### GET /health
Health check endpoint.

```bash
curl http://127.0.0.1:8765/health
```

Response:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "database_ok": true
}
```

#### GET /status
Detailed daemon status.

```bash
curl http://127.0.0.1:8765/status
```

Response:
```json
{
  "running": true,
  "uptime_seconds": 3600.5,
  "version": "0.1.0",
  "watcher_active": true,
  "paths_watched": 3,
  "files_tracked": 1250,
  "upload_queue_size": 5
}
```

### Path Endpoints

#### GET /paths
List all registered paths.

```bash
curl http://127.0.0.1:8765/paths
```

#### POST /paths
Register a new path.

```bash
curl -X POST http://127.0.0.1:8765/paths \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/watch", "recursive": true}'
```

#### GET /paths/{id}
Get details for a specific path.

#### DELETE /paths/{id}
Unregister a path.

#### POST /paths/{id}/scan
Trigger a rescan of a path.

### Exclude Endpoints

#### GET /excludes
List all exclude patterns.

#### POST /excludes
Add an exclude pattern.

```bash
curl -X POST http://127.0.0.1:8765/excludes \
  -H "Content-Type: application/json" \
  -d '{"pattern": "*.log"}'
```

#### DELETE /excludes/{id}
Remove an exclude pattern.

### File Endpoints

#### GET /files
List tracked files with optional filtering.

Query parameters:
- `path_prefix`: Filter by path prefix
- `sha256`: Filter by SHA256 hash
- `limit`: Max results (default: 100)
- `offset`: Pagination offset

#### GET /files/stats
Get file statistics.

```bash
curl http://127.0.0.1:8765/files/stats
```

Response:
```json
{
  "total_files": 1250,
  "total_size": 5368709120,
  "pending_uploads": 10,
  "successful_uploads": 1200,
  "failed_uploads": 5,
  "paths_watched": 3
}
```

#### GET /files/{id}
Get details for a specific file.

#### DELETE /files/{id}
Remove a file from tracking.

### Server Endpoints

#### GET /servers
List configured remote servers.

#### POST /servers
Add a server configuration.

```bash
curl -X POST http://127.0.0.1:8765/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production",
    "url": "https://app.putplace.org",
    "username": "user",
    "password": "password"
  }'
```

#### DELETE /servers/{id}
Remove a server configuration.

#### POST /servers/{id}/default
Set a server as the default.

### Upload Endpoints

#### POST /uploads
Trigger file uploads.

```bash
curl -X POST http://127.0.0.1:8765/uploads \
  -H "Content-Type: application/json" \
  -d '{
    "path_prefix": "/optional/filter",
    "upload_content": true
  }'
```

#### GET /uploads/status
Get current upload status with in-progress details.

#### GET /uploads/queue
Get upload queue status.

### Activity Endpoints

#### GET /activity
List recent activity events.

Query parameters:
- `limit`: Max results (default: 50)
- `since_id`: Get events after this ID
- `event_type`: Filter by event type

#### GET /activity/stream
Server-Sent Events (SSE) stream for real-time activity.

```bash
curl -N http://127.0.0.1:8765/activity/stream
```

Event types:
- `scan_started`, `scan_complete`
- `file_discovered`, `file_changed`, `file_deleted`
- `upload_started`, `upload_progress`, `upload_complete`, `upload_failed`
- `error`

#### WS /ws/activity
WebSocket endpoint for real-time activity.

### Scanning Endpoints

#### POST /scan
Trigger a full scan of all registered paths.

```bash
curl -X POST http://127.0.0.1:8765/scan
```

## Configuration

Configuration can be set via:
1. Environment variables (prefix: `PPASSIST_`)
2. TOML config file (`~/.config/putplace/ppassist.toml`)
3. Command-line arguments

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PPASSIST_SERVER_HOST` | `127.0.0.1` | Host to bind to |
| `PPASSIST_SERVER_PORT` | `8765` | Port to bind to |
| `PPASSIST_SERVER_LOG_LEVEL` | `INFO` | Logging level |
| `PPASSIST_DB_PATH` | `~/.local/share/putplace/assist.db` | Database path |
| `PPASSIST_WATCHER_ENABLED` | `true` | Enable file watching |
| `PPASSIST_WATCHER_DEBOUNCE` | `2.0` | Debounce delay in seconds |
| `PPASSIST_UPLOADER_PARALLEL` | `4` | Parallel upload workers |
| `PPASSIST_UPLOADER_RETRY` | `3` | Retry attempts |

### Config File

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

### Data Locations

| Type | Default Path |
|------|--------------|
| Database | `~/.local/share/putplace/assist.db` |
| PID file | `~/.local/share/putplace/ppassist.pid` |
| Config file | `~/.config/putplace/ppassist.toml` |
| Log file | `~/.local/share/putplace/ppassist.log` |

## Use Cases

### Automated Backup Monitoring

Set up ppassist to watch your backup directories and automatically upload metadata to PutPlace:

```bash
# Start daemon
ppassist start

# Register backup directories
pp_client --path /backups/daily --upload
pp_client --path /backups/weekly --upload

# Exclude temporary files
curl -X POST http://127.0.0.1:8765/excludes \
  -H "Content-Type: application/json" \
  -d '{"pattern": "*.tmp"}'
```

### Development Workflow

Monitor source code directories and track changes:

```bash
# Register project directories
pp_client --path ~/Projects/myapp \
  --exclude ".git" \
  --exclude "node_modules" \
  --exclude "__pycache__" \
  --exclude "*.pyc"
```

### Server Fleet Management

Deploy ppassist on multiple servers to centralize file tracking:

```bash
# Configure remote server
pp_client --configure-server

# Register system directories
pp_client --path /etc --upload
pp_client --path /var/log --exclude "*.gz" --upload
```

## Troubleshooting

### Daemon Won't Start

Check if another process is using port 8765:
```bash
lsof -i :8765
```

Check the log file:
```bash
cat ~/.local/share/putplace/ppassist.log
```

### Connection Refused

Ensure the daemon is running:
```bash
ppassist status
```

If using a different port, specify it:
```bash
pp_client --daemon-url http://127.0.0.1:9000 --status
```

### Files Not Being Detected

1. Check that the watcher is enabled:
   ```bash
   curl http://127.0.0.1:8765/status | jq .watcher_active
   ```

2. Trigger a manual rescan:
   ```bash
   curl -X POST http://127.0.0.1:8765/scan
   ```

3. Check exclude patterns aren't too broad:
   ```bash
   curl http://127.0.0.1:8765/excludes
   ```

### Uploads Failing

1. Check server configuration:
   ```bash
   curl http://127.0.0.1:8765/servers
   ```

2. Check upload status for error messages:
   ```bash
   curl http://127.0.0.1:8765/uploads/status
   ```

3. Verify credentials are correct by testing the server directly.

## Development

### Running Tests

```bash
cd packages/putplace-assist
invoke test
```

### Running Linter

```bash
invoke lint
invoke format
```

### Development Server

```bash
invoke serve
```

This starts the daemon in development mode with auto-reload.
