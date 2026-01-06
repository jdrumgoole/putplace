"""FastAPI application for putplace-assist daemon."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from .activity import (
    activity_manager,
    event_to_json,
    get_recent_activity,
    stream_activity_sse,
)
from .config import settings
from .database import db
from .models import (
    ActivityListResponse,
    AuthResponse,
    DaemonStatus,
    EventType,
    ExcludeCreate,
    ExcludeListResponse,
    ExcludeResponse,
    FileLogListResponse,
    FileLogSha256Entry,
    FileStats,
    HealthResponse,
    LoginRequest,
    PathCreate,
    PathListResponse,
    PathResponse,
    QueueStatus,
    RegisterRequest,
    Sha256ProcessorStatus,
    ServerCreate,
    ServerListResponse,
    ServerResponse,
    UploadHistoryRecord,
    UploadHistoryResponse,
    UploadProgressInfo,
    UploadRequest,
    UploadStatusResponse,
)
from .scanner import scan_all_paths, scan_directory
from .sha256_processor import sha256_processor
from .uploader import Uploader, encrypt_password
from .uploader_v3 import uploader_v3
from .version import __version__
from .watcher import watcher

logger = logging.getLogger(__name__)

# Track startup time
_startup_time: Optional[datetime] = None

# Global uploader instance
uploader = Uploader()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _startup_time
    _startup_time = datetime.utcnow()

    # Connect to database
    await db.connect()
    logger.info("Database connected")

    # Auto-configure remote server from settings if specified
    if settings.remote_server_url:
        try:
            # Check if server already exists
            servers = await db.get_all_servers()
            server_exists = any(s.url == settings.remote_server_url for s in servers)

            if not server_exists:
                # Encrypt password if provided
                encrypted_password = None
                if settings.remote_server_password:
                    encrypted_password = encrypt_password(settings.remote_server_password)

                # Create server as default if it's the first one
                is_default = len(servers) == 0

                server_id = await db.add_server(
                    name=settings.remote_server_name or "default",
                    url=settings.remote_server_url,
                    username=settings.remote_server_username,
                    password_encrypted=encrypted_password,
                    is_default=is_default,
                )
                logger.info(f"Auto-configured remote server: {settings.remote_server_url}")
        except Exception as e:
            logger.warning(f"Failed to auto-configure remote server: {e}")

    # Start activity manager
    await activity_manager.start()

    # Start file watcher if enabled
    if settings.watcher_enabled:
        await watcher.start()

    # Start all 3 components of the queue-based architecture
    # Component 1: Scanner (used via scan_directory/scan_all_paths - no background task needed)
    # Component 2: SHA256 Processor (processes queue_pending_checksum)
    await sha256_processor.start()
    logger.info("Component 2 (SHA256 Processor) started")

    # Component 3: Uploader (processes queue_pending_upload and queue_pending_deletion)
    await uploader_v3.start()
    logger.info("Component 3 (Uploader) started")

    # Keep old uploader for backward compatibility (can be removed later)
    await uploader.start()

    logger.info("PutPlace Assist daemon started (3-component queue-based architecture)")

    yield

    # Shutdown
    logger.info("Shutting down...")

    # Stop all 3 components
    await uploader_v3.stop()
    logger.info("Component 3 (Uploader) stopped")

    await sha256_processor.stop()
    logger.info("Component 2 (SHA256 Processor) stopped")

    # Stop old uploader
    await uploader.stop()

    await watcher.stop()
    await activity_manager.stop()
    await db.disconnect()

    logger.info("PutPlace Assist daemon stopped")


app = FastAPI(
    title="PutPlace Assist",
    description="Local assistant daemon for file uploads",
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware for Electron/web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store authentication tokens (server_url -> token)
_auth_tokens: dict[str, str] = {}


# ===== Health & Status =====


@app.get("/health", response_model=HealthResponse, tags=["Status"])
async def health_check():
    """Health check endpoint."""
    try:
        # Quick database check
        await db.get_file_stats()
        db_ok = True
    except Exception:
        db_ok = False

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=__version__,
        database_ok=db_ok,
    )


@app.get("/status", response_model=DaemonStatus, tags=["Status"])
async def get_status():
    """Get daemon status."""
    stats = await db.get_file_stats()

    uptime = 0.0
    if _startup_time:
        uptime = (datetime.utcnow() - _startup_time).total_seconds()

    return DaemonStatus(
        running=True,
        uptime_seconds=uptime,
        version=__version__,
        watcher_active=watcher.is_running,
        sha256_processor_active=sha256_processor.is_running,
        paths_watched=stats.paths_watched,
        files_tracked=stats.total_files,
        pending_sha256=stats.pending_sha256,
        pending_uploads=stats.pending_uploads,
    )


# ===== Authentication =====


@app.post("/login", response_model=AuthResponse, tags=["Authentication"])
async def login(request: LoginRequest):
    """
    Login to the remote server through pp_assist.

    This endpoint proxies the login request to the configured remote server,
    stores the JWT token, and returns it to the client.
    """
    # Get the default server
    servers = await db.get_all_servers()
    default_server = next((s for s in servers if s.is_default), None)

    if not default_server:
        return AuthResponse(
            success=False,
            error="No default server configured. Please configure a server first."
        )

    # Make login request to remote server
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{default_server.url.rstrip('/')}/api/login",
                json={"email": request.email, "password": request.password},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                user_id = data.get("user_id")

                # Store the token
                if token:
                    _auth_tokens[default_server.url] = token

                logger.info(f"Successfully logged in to {default_server.url}")
                return AuthResponse(
                    success=True,
                    token=token,
                    user_id=user_id
                )
            else:
                # Try to parse error response as JSON, fallback to status text
                try:
                    error_detail = response.json().get("detail", "Login failed")
                except (ValueError, KeyError):
                    error_detail = f"Login failed with status {response.status_code}: {response.text[:200]}"

                logger.warning(f"Login failed: {error_detail}")
                return AuthResponse(
                    success=False,
                    error=error_detail
                )

    except httpx.RequestError as e:
        logger.error(f"Login request failed to {default_server.url}: {e}")
        return AuthResponse(
            success=False,
            error=f"Cannot connect to server at {default_server.url}. Is the server running?"
        )


@app.post("/register", response_model=AuthResponse, tags=["Authentication"])
async def register(request: RegisterRequest):
    """
    Register a new user on the remote server through pp_assist.

    This endpoint proxies the registration request to the configured remote server.
    """
    # Get the default server
    servers = await db.get_all_servers()
    default_server = next((s for s in servers if s.is_default), None)

    if not default_server:
        return AuthResponse(
            success=False,
            error="No default server configured. Please configure a server first."
        )

    # Make registration request to remote server
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {
                "username": request.username,
                "email": request.email,
                "password": request.password,
            }
            if request.full_name:
                payload["full_name"] = request.full_name

            response = await client.post(
                f"{default_server.url.rstrip('/')}/api/register",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 201:
                data = response.json()
                user_id = data.get("id")

                logger.info(f"Successfully registered user {request.username}")
                return AuthResponse(
                    success=True,
                    user_id=user_id
                )
            else:
                # Try to parse error response as JSON, fallback to status text
                try:
                    error_detail = response.json().get("detail", "Registration failed")
                except (ValueError, KeyError):
                    error_detail = f"Registration failed with status {response.status_code}: {response.text[:200]}"

                logger.warning(f"Registration failed: {error_detail}")
                return AuthResponse(
                    success=False,
                    error=error_detail
                )

    except httpx.RequestError as e:
        logger.error(f"Registration request failed to {default_server.url}: {e}")
        return AuthResponse(
            success=False,
            error=f"Cannot connect to server at {default_server.url}. Is the server running?"
        )


# ===== Paths =====


@app.post("/paths", response_model=PathResponse, tags=["Paths"])
async def register_path(request: PathCreate):
    """Register a new path to watch."""
    path = Path(request.path).expanduser().resolve()

    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")

    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")

    # Check if already registered
    existing = await db.get_path_by_path(str(path))
    if existing:
        raise HTTPException(status_code=409, detail="Path already registered")

    # Add to database
    path_id = await db.add_path(str(path), request.recursive)

    # Add to watcher
    if watcher.is_running:
        await watcher.add_path(path_id, str(path))

    # Get full response
    path_response = await db.get_path(path_id)

    # Trigger initial scan in background
    asyncio.create_task(scan_path_background(path_id, path, request.recursive))

    return path_response


async def scan_path_background(path_id: int, path: Path, recursive: bool):
    """Scan a path in the background."""
    try:
        excludes = await db.get_all_excludes()
        exclude_patterns = [e.pattern for e in excludes]

        await scan_directory(
            path_id=path_id,
            directory=path,
            recursive=recursive,
            exclude_patterns=exclude_patterns,
        )
    except Exception as e:
        logger.error(f"Background scan failed: {e}")


@app.get("/paths", response_model=PathListResponse, tags=["Paths"])
async def list_paths():
    """List all registered paths."""
    paths = await db.get_all_paths()

    # Populate file counts
    for path in paths:
        path.file_count = await db.get_path_file_count(path.id)

    return PathListResponse(paths=paths, total=len(paths))


@app.get("/paths/{path_id}", response_model=PathResponse, tags=["Paths"])
async def get_path(path_id: int):
    """Get a specific path."""
    path = await db.get_path(path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")

    path.file_count = await db.get_path_file_count(path_id)
    return path


@app.delete("/paths/{path_id}", tags=["Paths"])
async def delete_path(path_id: int):
    """Delete a registered path."""
    # Remove from watcher
    if watcher.is_running:
        await watcher.remove_path(path_id)

    # Delete from database
    if not await db.delete_path(path_id):
        raise HTTPException(status_code=404, detail="Path not found")

    return {"status": "deleted"}


@app.post("/paths/{path_id}/scan", tags=["Paths"])
async def trigger_scan(path_id: int):
    """Trigger a rescan of a path."""
    path = await db.get_path(path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")

    # Trigger scan in background
    asyncio.create_task(
        scan_path_background(path_id, Path(path.path), path.recursive)
    )

    return {"status": "scan_started", "path_id": path_id}


# ===== Exclude Patterns =====


@app.post("/excludes", response_model=ExcludeResponse, tags=["Excludes"])
async def add_exclude(request: ExcludeCreate):
    """Add an exclude pattern."""
    try:
        exclude_id = await db.add_exclude(request.pattern)
    except Exception:
        raise HTTPException(status_code=409, detail="Pattern already exists")

    excludes = await db.get_all_excludes()
    for exclude in excludes:
        if exclude.id == exclude_id:
            return exclude

    raise HTTPException(status_code=500, detail="Failed to create exclude")


@app.get("/excludes", response_model=ExcludeListResponse, tags=["Excludes"])
async def list_excludes():
    """List all exclude patterns."""
    excludes = await db.get_all_excludes()
    return ExcludeListResponse(patterns=excludes, total=len(excludes))


@app.delete("/excludes/{exclude_id}", tags=["Excludes"])
async def delete_exclude(exclude_id: int):
    """Delete an exclude pattern."""
    if not await db.delete_exclude(exclude_id):
        raise HTTPException(status_code=404, detail="Exclude pattern not found")
    return {"status": "deleted"}


# ===== Files =====


@app.get("/files", response_model=FileLogListResponse, tags=["Files"])
async def list_files(
    path_prefix: Optional[str] = Query(None, description="Filter by path prefix"),
    upload_status: Optional[str] = Query(
        None, description="Filter by upload status (meta, full, or empty for pending)"
    ),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List tracked files from filelog_sha256."""
    entries, total = await db.get_sha256_entries(
        filepath_prefix=path_prefix,
        upload_status=upload_status,
        limit=limit,
        offset=offset,
    )
    return FileLogListResponse(
        entries=entries,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/files/stats", response_model=FileStats, tags=["Files"])
async def get_file_stats():
    """Get file statistics."""
    return await db.get_file_stats()


@app.get("/files/{sha256}", response_model=FileLogSha256Entry, tags=["Files"])
async def get_file_by_hash(sha256: str):
    """Get a file by its SHA256 hash."""
    entry = await db.get_sha256_by_hash(sha256)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found")
    return entry


# ===== Servers =====


@app.post("/servers", response_model=ServerResponse, tags=["Servers"])
async def add_server(request: ServerCreate):
    """Add a remote server configuration."""
    # Encrypt password
    encrypted_password = encrypt_password(request.password)

    # Determine if this should be the default server
    servers = await db.get_all_servers()
    # First server is always default, or honor explicit is_default request
    is_default = len(servers) == 0 or request.is_default

    try:
        server_id = await db.add_server(
            name=request.name,
            url=request.url,
            username=request.username,
            password_encrypted=encrypted_password,
            is_default=is_default,
        )
    except Exception:
        raise HTTPException(status_code=409, detail="Server name already exists")

    server = await db.get_server(server_id)
    return server


@app.get("/servers", response_model=ServerListResponse, tags=["Servers"])
async def list_servers():
    """List all configured servers."""
    servers = await db.get_all_servers()
    return ServerListResponse(servers=servers, total=len(servers))


@app.delete("/servers/{server_id}", tags=["Servers"])
async def delete_server(server_id: int):
    """Delete a server configuration."""
    if not await db.delete_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")
    return {"status": "deleted"}


@app.post("/servers/{server_id}/default", tags=["Servers"])
async def set_default_server(server_id: int):
    """Set a server as the default."""
    if not await db.set_default_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")
    return {"status": "default_set"}


# ===== Uploads =====


@app.post("/uploads", tags=["Uploads"])
async def trigger_uploads(request: UploadRequest):
    """Trigger file uploads.

    If process_inline=True (default), calculates SHA256 inline for unprocessed files
    and also uploads files that already have SHA256 calculated.
    """
    files_queued = 0
    processing_modes = []

    if request.process_inline:
        # First, process unprocessed files with inline SHA256 calculation
        unprocessed_count = await uploader.queue_unprocessed_files(
            path_prefix=request.path_prefix,
            upload_content=request.upload_content,
            limit=request.limit,
        )
        files_queued += unprocessed_count
        if unprocessed_count > 0:
            processing_modes.append("inline")

    # Also queue files that already have SHA256 calculated but haven't been uploaded
    pending_count = await uploader.queue_pending_files(
        path_prefix=request.path_prefix,
        upload_content=request.upload_content
    )
    files_queued += pending_count
    if pending_count > 0:
        processing_modes.append("pre-calculated")

    processing_mode = "+".join(processing_modes) if processing_modes else "none"

    return {
        "status": "upload_queued",
        "files_queued": files_queued,
        "upload_type": "full" if request.upload_content else "meta",
        "processing_mode": processing_mode,
    }


@app.get("/uploads/queue", response_model=QueueStatus, tags=["Uploads"])
async def get_queue_status():
    """Get upload queue status."""
    stats = await db.get_file_stats()

    return QueueStatus(
        pending_sha256=stats.pending_sha256,
        pending_upload=stats.pending_uploads,
        in_progress=len(uploader.get_in_progress()),
        completed_today=uploader.completed_count,
        failed_today=uploader.failed_count,
    )


@app.get("/uploads/progress", response_model=UploadStatusResponse, tags=["Uploads"])
async def get_upload_progress():
    """Get current upload progress with details."""
    in_progress_uploads = uploader.get_in_progress()

    # Convert uploader.UploadProgress to models.UploadProgressInfo
    progress_info = [
        UploadProgressInfo(
            entry_id=p.file_id,
            filepath=p.filepath,
            sha256="",  # Not needed for progress display
            status=p.status.value,
            progress_percent=p.progress_percent,
            bytes_uploaded=p.bytes_uploaded,
            total_bytes=p.total_bytes,
            error_message=p.error_message,
        )
        for p in in_progress_uploads
    ]

    return UploadStatusResponse(
        is_uploading=len(in_progress_uploads) > 0,
        queue_size=uploader._queue.qsize(),
        in_progress=progress_info,
        completed_count=uploader.completed_count,
        failed_count=uploader.failed_count,
    )


@app.get("/uploads/history", response_model=UploadHistoryResponse, tags=["Uploads"])
async def get_upload_history(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    upload_status: Optional[str] = Query(
        None, description="Filter by status (meta, full)"
    ),
):
    """Get upload history from filelog_sha256."""
    entries, total = await db.get_sha256_entries(
        upload_status=upload_status if upload_status else None,
        limit=limit,
        offset=offset,
    )

    # Convert to UploadHistoryRecord format
    records = [
        UploadHistoryRecord(
            id=e.id,
            filepath=e.filepath,
            sha256=e.sha256,
            file_size=e.file_size,
            upload_status=e.upload_status,
            processed_at=e.processed_at,
        )
        for e in entries
        if e.upload_status is not None  # Only show uploaded files
    ]

    return UploadHistoryResponse(
        records=records,
        total=len(records),
        limit=limit,
        offset=offset,
    )


# ===== SHA256 Processor =====


@app.get("/sha256/status", response_model=Sha256ProcessorStatus, tags=["SHA256"])
async def get_sha256_status():
    """Get SHA256 processor status."""
    pending = await sha256_processor.get_pending_count()

    return Sha256ProcessorStatus(
        is_running=sha256_processor.is_running,
        pending_count=pending,
        processed_today=sha256_processor.processed_today,
        failed_today=sha256_processor.failed_today,
        current_file=sha256_processor.current_file,
    )


# ===== Activity =====


@app.get("/activity", response_model=ActivityListResponse, tags=["Activity"])
async def list_activity(
    limit: int = Query(50, ge=1, le=500),
    since_id: Optional[int] = Query(None, description="Get events after this ID"),
    event_type: Optional[EventType] = Query(None, description="Filter by event type"),
):
    """List recent activity events."""
    events, has_more = await db.get_activity(
        limit=limit,
        since_id=since_id,
        event_type=event_type,
    )
    return ActivityListResponse(
        events=events,
        total=len(events),
        has_more=has_more,
    )


@app.get("/activity/stream", tags=["Activity"])
async def stream_activity(
    event_type: Optional[EventType] = Query(None, description="Filter by event type"),
):
    """Stream activity events via Server-Sent Events."""
    return EventSourceResponse(stream_activity_sse(event_type))


@app.websocket("/ws/activity")
async def websocket_activity(websocket: WebSocket):
    """WebSocket endpoint for activity events."""
    await websocket.accept()

    # Subscribe to events
    queue = activity_manager.subscribe()

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(event_to_json(event))
            except asyncio.TimeoutError:
                # Send ping
                await websocket.send_json({"type": "ping", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        activity_manager.unsubscribe(queue)


# ===== Scanning =====


@app.post("/scan", tags=["Scanning"])
async def trigger_full_scan():
    """Trigger a full scan of all registered paths."""
    # Start scan in background
    asyncio.create_task(scan_all_paths_background())
    return {"status": "scan_started"}


async def scan_all_paths_background():
    """Scan all paths in the background."""
    try:
        await scan_all_paths()
    except Exception as e:
        logger.error(f"Full scan failed: {e}")


# ===== Root =====


@app.get("/config", tags=["Configuration"])
async def get_config():
    """Get current configuration and config file location."""
    from .config import find_config_file

    config_file = find_config_file()

    return {
        "config_file": str(config_file) if config_file else None,
        "config": {
            "server": {
                "host": settings.server_host,
                "port": settings.server_port,
                "log_level": settings.server_log_level,
            },
            "remote_server": {
                "name": settings.remote_server_name,
                "url": settings.remote_server_url,
                "username": settings.remote_server_username,
                # Don't expose password
            },
            "database": {
                "path": settings.db_path,
            },
            "watcher": {
                "enabled": settings.watcher_enabled,
                "debounce_seconds": settings.watcher_debounce_seconds,
            },
            "uploader": {
                "parallel_uploads": settings.uploader_parallel_uploads,
                "retry_attempts": settings.uploader_retry_attempts,
                "retry_delay_seconds": settings.uploader_retry_delay_seconds,
            },
            "sha256": {
                "chunk_size": settings.sha256_chunk_size,
                "chunk_delay_ms": settings.sha256_chunk_delay_ms,
                "batch_size": settings.sha256_batch_size,
                "batch_delay_seconds": settings.sha256_batch_delay_seconds,
            },
        }
    }


@app.post("/config", tags=["Configuration"])
async def save_config(config: dict):
    """Save configuration to config file."""
    from .config import find_config_file
    import tomli_w
    import sys

    # Use tomllib (Python 3.11+) or tomli (Python < 3.11) for reading
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    config_file = find_config_file()
    if not config_file:
        # Create default location if no config file exists
        config_file = Path.home() / ".config" / "putplace" / "pp_assist.toml"
        config_file.parent.mkdir(parents=True, exist_ok=True)

    # If password not provided in new config, preserve existing password
    if config_file.exists() and "password" not in config.get("remote_server", {}):
        try:
            with open(config_file, "rb") as f:
                existing_config = tomllib.load(f)
            # Preserve existing password if present
            if "remote_server" in existing_config and "password" in existing_config["remote_server"]:
                if "remote_server" not in config:
                    config["remote_server"] = {}
                config["remote_server"]["password"] = existing_config["remote_server"]["password"]
        except Exception:
            pass  # If we can't read existing config, just save the new one

    # Write TOML file
    with open(config_file, "wb") as f:
        tomli_w.dump(config, f)

    return {
        "status": "saved",
        "config_file": str(config_file),
        "message": "Configuration saved. Restart pp_assist for changes to take effect."
    }


@app.get("/", tags=["Status"])
async def root():
    """Redirect to web UI."""
    return RedirectResponse(url="/ui")


# ===== Web UI =====

# Get path to static files
_static_dir = Path(__file__).parent / "static"


@app.get("/ui", tags=["UI"])
async def web_ui():
    """Serve the web UI."""
    index_file = _static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file, media_type="text/html")
    raise HTTPException(status_code=404, detail="Web UI not found")


# Mount static files (must be after other routes to avoid conflicts)
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
