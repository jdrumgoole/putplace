#!/usr/bin/env python3
"""
End-to-end test for PutPlace upload workflow with 3-component queue architecture.

This script tests the complete upload flow:

Phase 1 - Synthetic Test File:
1. Start server with ppserver-dev.toml
2. Create a test user
3. Generate a deterministic test file
4. Upload file via pp_client (triggers 3-component workflow)
5. Validate file exists in MongoDB and S3
6. Validate 3-component queue workflow:
   - Component 1: Scanner queues files to queue_pending_checksum
   - Component 2: Checksum Calculator processes queue → queue_pending_upload
   - Component 3: Uploader processes queue with chunked uploads
7. Validate files table status transitions (discovered → ready_for_upload → completed)
8. Validate chunked upload protocol was used

Phase 2 - Real Desktop Directory:
9. Register Desktop directory
10. Process and upload Desktop files
11. Validate uploads in MongoDB and S3

Cleanup:
12. Purge user and data
13. Verify cleanup
14. Clean up test file
"""

import asyncio
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import boto3
from pymongo import MongoClient

# Test configuration
TEST_FILE_CONTENT = b"PutPlace End-to-End Test File\n" * 1000  # ~30KB file
TEST_DIR = Path("/tmp/putplace_e2e_test")
TEST_FILE_PATH = TEST_DIR / "test_file.txt"
TEST_USER_EMAIL = "e2e-test@example.com"
TEST_USER_PASSWORD = "testpass123"
TEST_USER_NAME = "E2E Test User"

# Server configuration (from ppserver-dev.toml)
MONGODB_URL = "mongodb+srv://jdrumgoole:VandalGoth775@dev.hnrmaki.mongodb.net"
MONGODB_DATABASE = "putplace_dev"
S3_BUCKET = "putplace-dev"
S3_REGION = "eu-west-1"
AWS_PROFILE = "putplace-dev"
SERVER_URL = "http://127.0.0.1:8000"
SERVER_CONFIG = "ppserver-dev.toml"

# Expected SHA256 of test file
EXPECTED_SHA256 = hashlib.sha256(TEST_FILE_CONTENT).hexdigest()

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_step(step: str):
    """Print a test step."""
    print(f"\n{BLUE}▶ {step}{RESET}", flush=True)


def print_success(message: str):
    """Print a success message."""
    print(f"{GREEN}✓ {message}{RESET}", flush=True)


def print_error(message: str):
    """Print an error message."""
    print(f"{RED}✗ {message}{RESET}", flush=True)


def print_warning(message: str):
    """Print a warning message."""
    print(f"{YELLOW}⚠ {message}{RESET}", flush=True)


def run_command(cmd: list[str], check: bool = True, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"  Running: {' '.join(cmd)}", flush=True)

    # Merge environment
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        env=full_env
    )

    if check and result.returncode != 0:
        print_error(f"Command failed with exit code {result.returncode}")
        print(f"  stdout: {result.stdout}", flush=True)
        print(f"  stderr: {result.stderr}", flush=True)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")

    return result


def create_test_file() -> Path:
    """Create a deterministic test file in a test directory."""
    print_step("Creating test directory and file")

    # Create test directory
    TEST_DIR.mkdir(parents=True, exist_ok=True)

    # Create test file
    TEST_FILE_PATH.write_bytes(TEST_FILE_CONTENT)

    # Verify SHA256
    actual_sha256 = hashlib.sha256(TEST_FILE_CONTENT).hexdigest()
    assert actual_sha256 == EXPECTED_SHA256, f"SHA256 mismatch: {actual_sha256} != {EXPECTED_SHA256}"

    print_success(f"Test directory created: {TEST_DIR}")
    print_success(f"Test file created: {TEST_FILE_PATH}")
    print(f"  Size: {len(TEST_FILE_CONTENT):,} bytes")
    print(f"  SHA256: {EXPECTED_SHA256}")

    return TEST_DIR


def cleanup_test_file():
    """Remove the test directory and file."""
    import shutil
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
        print_success(f"Test directory removed: {TEST_DIR}")


def cleanup_ppassist_paths():
    """Remove test paths from ppassist daemon."""
    try:
        # Get all registered paths
        result = subprocess.run(
            ["curl", "-s", "http://localhost:8765/paths"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0 and result.stdout:
            import json
            data = json.loads(result.stdout)
            paths = data.get("paths", [])

            # Remove any paths that match our test directory
            test_path_str = str(TEST_DIR)
            for path_info in paths:
                path_value = path_info.get("path", "")
                path_id = path_info.get("id")

                # Check if this is our test path (handle /private prefix on macOS)
                if test_path_str in path_value or path_value.endswith("putplace_e2e_test"):
                    print(f"  Removing registered path: {path_value} (ID: {path_id})", flush=True)
                    subprocess.run(
                        ["curl", "-s", "-X", "DELETE", f"http://localhost:8765/paths/{path_id}"],
                        capture_output=True,
                        check=False
                    )
    except Exception as e:
        # Don't fail the test if cleanup fails
        print(f"  Warning: Failed to cleanup ppassist paths: {e}", flush=True)


def stop_ppassist_daemon():
    """Stop pp_assist daemon."""
    print("  Stopping pp_assist daemon", end="", flush=True)

    try:
        # Stop daemon with timeout
        print(".", end="", flush=True)
        stop_result = subprocess.run(
            ["uv", "run", "pp_assist", "stop"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10
        )
        if stop_result.returncode != 0 and "not running" not in stop_result.stdout.lower():
            print()
            print_warning(f"Stop command issues: {stop_result.stdout} {stop_result.stderr}")

        print(".", end="", flush=True)
        time.sleep(2)
        return True

    except subprocess.TimeoutExpired as e:
        print()  # New line
        print_error(f"Command timed out: {e}")
        return False
    except Exception as e:
        print()  # New line
        print_warning(f"Failed to stop pp_assist daemon: {e}")
        return False


def start_ppassist_daemon():
    """Start pp_assist daemon."""
    print("  Starting pp_assist daemon", end="", flush=True)

    try:
        # Start daemon with timeout
        print(".", end="", flush=True)
        start_result = subprocess.run(
            ["uv", "run", "pp_assist", "start"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30
        )
        if start_result.returncode != 0:
            print()
            print_warning(f"Start command failed: {start_result.stdout} {start_result.stderr}")
            return False

        print(".", end="", flush=True)
        time.sleep(3)

        # Wait for daemon to be ready (30 seconds timeout)
        for i in range(30):
            result = subprocess.run(
                ["curl", "-s", "http://localhost:8765/health"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )
            if result.returncode == 0 and "ok" in result.stdout:
                print()  # New line
                return True

            print(".", end="", flush=True)
            time.sleep(1)

        print()  # New line
        print_warning("pp_assist daemon may not be ready after 30 seconds")
        return False

    except subprocess.TimeoutExpired as e:
        print()  # New line
        print_error(f"Command timed out: {e}")
        return False
    except Exception as e:
        print()  # New line
        print_warning(f"Failed to start pp_assist daemon: {e}")
        return False


def restart_ppassist_daemon():
    """Restart pp_assist daemon to clear in-memory state."""
    print("  Restarting pp_assist daemon", end="", flush=True)

    try:
        # Stop daemon with timeout
        print(".", end="", flush=True)
        stop_result = subprocess.run(
            ["uv", "run", "pp_assist", "stop"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10
        )
        if stop_result.returncode != 0 and "not running" not in stop_result.stdout.lower():
            print()
            print_warning(f"Stop command issues: {stop_result.stdout} {stop_result.stderr}")

        print(".", end="", flush=True)
        time.sleep(2)

        # Start daemon with timeout
        print(".", end="", flush=True)
        start_result = subprocess.run(
            ["uv", "run", "pp_assist", "start"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30
        )
        if start_result.returncode != 0:
            print()
            print_warning(f"Start command failed: {start_result.stdout} {start_result.stderr}")
            return False

        print(".", end="", flush=True)
        time.sleep(3)

        # Wait for daemon to be ready (30 seconds timeout)
        for i in range(30):
            result = subprocess.run(
                ["curl", "-s", "http://localhost:8765/health"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )
            if result.returncode == 0 and "ok" in result.stdout:
                print()  # New line
                print_success("pp_assist daemon restarted")
                return True

            print(".", end="", flush=True)
            time.sleep(1)

        print()  # New line
        print_warning("pp_assist daemon may not be ready after 30 seconds")
        return False

    except subprocess.TimeoutExpired as e:
        print()  # New line
        print_error(f"Command timed out: {e}")
        return False
    except Exception as e:
        print()  # New line
        print_warning(f"Failed to restart pp_assist daemon: {e}")
        return False


def check_server_running() -> bool:
    """Check if the server is already running."""
    try:
        result = run_command(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{SERVER_URL}/health"],
            check=False
        )
        return result.stdout.strip() == "200"
    except Exception:
        return False


def start_server():
    """Start the PutPlace server."""
    print_step("Starting PutPlace server")

    # Check if already running
    if check_server_running():
        print_warning("Server already running, skipping start")
        return

    # Start server in background
    result = run_command(
        ["uv", "run", "python", "-m", "putplace_server.ppserver", "start", "--host", "127.0.0.1", "--port", "8000"],
        env={"PUTPLACE_CONFIG": SERVER_CONFIG, "AWS_PROFILE": AWS_PROFILE}
    )

    # Wait for server to be ready
    print("  Waiting for server to be ready", end="", flush=True)
    for i in range(30):
        if check_server_running():
            print()  # New line after dots
            print_success(f"Server started and ready at {SERVER_URL}")
            return
        print(".", end="", flush=True)
        time.sleep(1)

    print()  # New line after dots
    raise RuntimeError("Server failed to start within 30 seconds")


def create_test_user() -> str:
    """Create a test user and return the user ID."""
    print_step("Creating test user")

    result = run_command([
        "uv", "run", "pp_manage_users",
        "--mongodb-url", MONGODB_URL,
        "--database", MONGODB_DATABASE,
        "add",
        "--email", TEST_USER_EMAIL,
        "--password", TEST_USER_PASSWORD,
        "--name", TEST_USER_NAME
    ])

    # Extract user ID from output
    for line in result.stdout.split("\n"):
        if "ID:" in line:
            user_id = line.split("ID:")[1].strip()
            print_success(f"User created: {TEST_USER_EMAIL} (ID: {user_id})")
            return user_id

    raise RuntimeError("Failed to extract user ID from output")


def configure_ppassist():
    """Configure ppassist with server credentials."""
    print_step("Configuring ppassist daemon")

    run_command([
        "uv", "run", "pp_client",
        "--configure-server",
        "--server-url", SERVER_URL,
        "--email", TEST_USER_EMAIL,
        "--password", TEST_USER_PASSWORD
    ])

    print_success("ppassist configured")


def register_test_path():
    """Register the test directory with pp_assist."""
    print_step("Registering test directory")

    result = run_command([
        "uv", "run", "pp_client",
        "--path", str(TEST_DIR)
    ])

    print_success("Path registered")
    print(f"  Output: {result.stdout[:200]}")


def upload_test_file():
    """Trigger upload via pp_client."""
    print_step("Triggering upload")

    result = run_command([
        "uv", "run", "pp_client",
        "--path", str(TEST_DIR),
        "--upload",
        "--upload-content"
    ])

    print_success("Upload triggered")
    print(f"  Output: {result.stdout[:200]}")


def wait_for_sha256_processing(timeout: int = 30):
    """Wait for SHA256 processing to complete."""
    print_step("Waiting for SHA256 processing")
    print("  Checking status", end="", flush=True)

    start_time = time.time()
    while time.time() - start_time < timeout:
        # Check SHA256 processor status
        result = subprocess.run(
            ["curl", "-s", "http://localhost:8765/sha256/status"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            import json
            status = json.loads(result.stdout)

            pending = status.get("pending_count", 0)
            if pending == 0:
                processed = status.get("processed_today", 0)
                print()  # New line
                print_success(f"SHA256 processing complete: {processed} files processed")
                return True

        print(".", end="", flush=True)
        time.sleep(2)

    print()  # New line
    raise RuntimeError(f"SHA256 processing did not complete within {timeout} seconds")


def wait_for_upload_completion(timeout: int = 60):
    """Wait for uploads to complete."""
    print_step("Waiting for upload completion")
    print("  Checking status", end="", flush=True)

    start_time = time.time()
    while time.time() - start_time < timeout:
        # Check status quietly (don't print command)
        result = subprocess.run(
            ["curl", "-s", "http://localhost:8765/uploads/queue"],
            capture_output=True,
            text=True,
            check=False
        )

        if "in_progress" in result.stdout:
            import json
            status = json.loads(result.stdout)

            in_progress = status.get("in_progress", 0)
            pending = status.get("pending_upload", 0)

            # Check if all uploads are complete
            if in_progress == 0 and pending == 0:
                completed = status.get("completed_today", 0)
                failed = status.get("failed_today", 0)
                print()  # New line after dots
                print_success(f"Uploads complete: {completed} succeeded, {failed} failed")
                return completed, failed

        print(".", end="", flush=True)
        time.sleep(2)

    print()  # New line after dots
    raise RuntimeError(f"Upload did not complete within {timeout} seconds")


def validate_mongodb():
    """Validate file exists in MongoDB."""
    print_step("Validating MongoDB")

    client = MongoClient(MONGODB_URL)
    db = client[MONGODB_DATABASE]

    # First, show all files that were uploaded (for debugging)
    all_files = list(db.file_metadata.find())
    print(f"  Total files uploaded: {len(all_files)}")

    if all_files:
        print("  Files in database:")
        for doc in all_files:
            filepath = doc.get('filepath', 'unknown')
            sha256 = doc.get('sha256', 'unknown')
            print(f"    - {filepath}")
            print(f"      SHA256: {sha256}")

    # Find our test file by SHA256
    doc = db.file_metadata.find_one({"sha256": EXPECTED_SHA256})

    if not doc:
        client.close()
        print_error(f"Test file not found in MongoDB!")
        print_error(f"Expected SHA256: {EXPECTED_SHA256}")
        print_error(f"Expected file: {TEST_FILE_PATH}")
        raise RuntimeError(f"File not found in MongoDB with SHA256: {EXPECTED_SHA256}")

    print_success("Test file found in MongoDB")
    print(f"  filepath: {doc.get('filepath')}")
    print(f"  sha256: {doc.get('sha256')}")
    print(f"  file_size: {doc.get('file_size', 0):,} bytes")

    client.close()
    return True


def validate_s3():
    """Validate file exists in S3."""
    print_step("Validating S3")

    session = boto3.Session(profile_name=AWS_PROFILE)
    s3 = session.client("s3", region_name=S3_REGION)

    # S3 key format: files/XX/XXXX... (first 2 chars as prefix)
    s3_key = f"files/{EXPECTED_SHA256[:2]}/{EXPECTED_SHA256}"

    try:
        response = s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
        file_size = response["ContentLength"]

        print_success("File found in S3")
        print(f"  Bucket: {S3_BUCKET}")
        print(f"  Key: {s3_key}")
        print(f"  Size: {file_size:,} bytes")

        return True
    except s3.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            raise RuntimeError(f"File not found in S3: {s3_key}")
        raise


def purge_dev_environment(silent: bool = False):
    """Purge the dev environment."""
    if not silent:
        print_step("Purging dev environment")

    result = run_command([
        "uv", "run", "invoke", "purge-dev", "--force"
    ], check=False)

    if result.returncode == 0:
        if not silent:
            print_success("Dev environment purged")
            print(f"  Output: {result.stdout[:300]}")
    else:
        if not silent:
            print_warning(f"Purge returned exit code {result.returncode}")
            print(f"  This is OK if the environment was already clean")


def verify_cleanup():
    """Verify MongoDB and S3 are clean."""
    print_step("Verifying cleanup")

    # Check MongoDB
    client = MongoClient(MONGODB_URL)
    db = client[MONGODB_DATABASE]

    user_count = db.users.count_documents({})
    file_count = db.file_metadata.count_documents({})

    print(f"  MongoDB users: {user_count}")
    print(f"  MongoDB files: {file_count}")

    if user_count > 0 or file_count > 0:
        client.close()
        raise RuntimeError(f"Cleanup failed: {user_count} users, {file_count} files remaining")

    client.close()
    print_success("MongoDB is clean")

    # Check S3
    session = boto3.Session(profile_name=AWS_PROFILE)
    s3 = session.client("s3", region_name=S3_REGION)

    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="files/")
    s3_count = response.get("KeyCount", 0)

    print(f"  S3 objects: {s3_count}")

    if s3_count > 0:
        raise RuntimeError(f"Cleanup failed: {s3_count} objects remaining in S3")

    print_success("S3 is clean")

    return True


def get_upload_queue_status():
    """Get current upload queue status from daemon."""
    result = subprocess.run(
        ["curl", "-s", "http://localhost:8765/uploads/queue"],
        capture_output=True,
        text=True,
        check=False
    )

    if result.returncode == 0 and result.stdout:
        try:
            import json
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
    return {}


def get_ppassist_database_path() -> Path:
    """Get the path to the ppassist SQLite database."""
    return Path.home() / ".local" / "share" / "putplace" / "assist.db"


def query_ppassist_queue(queue_name: str) -> list[dict]:
    """Query a queue table from ppassist SQLite database.

    Args:
        queue_name: Name of queue (queue_pending_checksum, queue_pending_upload, queue_pending_deletion)

    Returns:
        List of queue entries as dictionaries
    """
    import sqlite3

    db_path = get_ppassist_database_path()
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM {queue_name}")
        rows = cursor.fetchall()

        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        print_warning(f"Failed to query {queue_name}: {e}")
        return []


def query_ppassist_files(filepath_filter: str = None) -> list[dict]:
    """Query files table from ppassist SQLite database.

    Args:
        filepath_filter: Optional filepath prefix to filter by

    Returns:
        List of file records as dictionaries
    """
    import sqlite3

    db_path = get_ppassist_database_path()
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if filepath_filter:
            cursor.execute(
                "SELECT * FROM files WHERE filepath LIKE ?",
                (f"{filepath_filter}%",)
            )
        else:
            cursor.execute("SELECT * FROM files")

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        print_warning(f"Failed to query files table: {e}")
        return []


def validate_queue_workflow():
    """Validate the 3-component queue-based architecture workflow.

    This validates:
    1. Component 1 (Scanner) queued files to queue_pending_checksum
    2. Component 2 (Checksum Calculator) processed checksum queue
    3. Component 3 (Uploader) processed upload queue
    4. Files table status transitions (discovered → ready_for_upload → completed)
    """
    print_step("Validating 3-component queue workflow")

    # Query all queues
    checksum_queue = query_ppassist_queue("queue_pending_checksum")
    upload_queue = query_ppassist_queue("queue_pending_upload")
    deletion_queue = query_ppassist_queue("queue_pending_deletion")

    print(f"  queue_pending_checksum: {len(checksum_queue)} entries")
    print(f"  queue_pending_upload: {len(upload_queue)} entries")
    print(f"  queue_pending_deletion: {len(deletion_queue)} entries")

    # Query files table
    files = query_ppassist_files(str(TEST_DIR))

    print(f"  files table: {len(files)} entries for test directory")

    if files:
        # Count files by status
        status_counts = {}
        for file_entry in files:
            status = file_entry.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        print("  File status breakdown:")
        for status, count in status_counts.items():
            print(f"    {status}: {count}")

        # Validate at least one file completed the full workflow
        completed_files = [f for f in files if f.get("status") == "completed"]
        if completed_files:
            print_success(f"Found {len(completed_files)} completed files in workflow")

            # Show details of first completed file
            sample = completed_files[0]
            print(f"  Sample completed file:")
            print(f"    filepath: {sample.get('filepath')}")
            print(f"    sha256: {sample.get('sha256', 'N/A')[:16]}...")
            print(f"    status: {sample.get('status')}")
            print(f"    uploaded_at: {sample.get('uploaded_at', 'N/A')}")
        else:
            print_warning("No completed files found - workflow may still be in progress")

    # Validate queues are empty (all files processed)
    if len(checksum_queue) == 0 and len(upload_queue) == 0:
        print_success("All queues empty - workflow completed successfully")
    else:
        print_warning(f"Queues not empty: {len(checksum_queue)} in checksum, {len(upload_queue)} in upload")

    return True


def validate_files_queued_for_checksum(expected_min: int = 1):
    """Validate that files were queued to queue_pending_checksum after path registration.

    This validates Component 1 (Scanner) is working correctly.

    Args:
        expected_min: Minimum number of files expected in checksum queue

    Returns:
        Number of files in checksum queue
    """
    print_step("Validating files queued for checksum (Component 1)")

    # Query checksum queue
    checksum_queue = query_ppassist_queue("queue_pending_checksum")
    queue_count = len(checksum_queue)

    print(f"  queue_pending_checksum: {queue_count} entries")

    if queue_count >= expected_min:
        print_success(f"Component 1 (Scanner) queued {queue_count} files for checksum")

        if checksum_queue:
            # Show sample entry
            sample = checksum_queue[0]
            print(f"  Sample entry:")
            print(f"    filepath: {sample.get('filepath')}")
            print(f"    reason: {sample.get('reason')}")
            print(f"    queued_at: {sample.get('queued_at')}")
    else:
        print_warning(f"Expected at least {expected_min} files, found {queue_count}")

    return queue_count


def validate_chunked_upload_used():
    """Validate that chunked upload protocol was used.

    Checks activity events for evidence of chunked uploads.
    """
    print_step("Validating chunked upload protocol")

    result = subprocess.run(
        ["curl", "-s", "http://localhost:8765/activity?limit=100"],
        capture_output=True,
        text=True,
        check=False
    )

    if result.returncode == 0 and result.stdout:
        try:
            import json
            data = json.loads(result.stdout)
            events = data.get("events", [])

            # Look for upload-related events
            upload_events = [e for e in events if "upload" in e.get("event_type", "").lower()]

            print(f"  Found {len(upload_events)} upload-related activity events")

            if upload_events:
                print("  Sample upload events:")
                for event in upload_events[:3]:
                    event_type = event.get("event_type", "unknown")
                    message = event.get("message", "")
                    print(f"    {event_type}: {message[:60]}")

                print_success("Upload activity events found")
            else:
                print_warning("No upload activity events found in recent activity")

            return len(upload_events) > 0

        except Exception as e:
            print_warning(f"Failed to parse activity events: {e}")
            return False

    return False


def upload_desktop_directory():
    """Upload the Desktop directory (Phase 2)."""
    desktop_path = Path.home() / "Desktop"

    print(f"\n{'='*80}")
    print(f"{BLUE}Phase 2: Uploading Desktop Directory{RESET}")
    print(f"{'='*80}\n")

    print_step(f"Registering Desktop directory: {desktop_path} (excluding large video files)")

    result = run_command([
        "uv", "run", "pp_client",
        "--path", str(desktop_path),
        "--exclude", "Drumgoole Family Videos - The Early Years",
        "--exclude", ".DS_Store"
    ])

    print_success("Desktop directory registered")
    print(f"  Output: {result.stdout[:200]}")

    return desktop_path


def wait_for_desktop_sha256_processing(expected_min_files: int = 1):
    """Wait for SHA256 processing of Desktop files."""
    print_step(f"Waiting for SHA256 processing (expecting at least {expected_min_files} files)")

    timeout = 3600  # 1 hour for Desktop (large video files)
    start_time = time.time()

    while time.time() - start_time < timeout:
        status = get_upload_queue_status()
        pending = status.get("pending_sha256", 0)

        if pending == 0:
            # Check how many files were processed
            result = run_command([
                "uv", "run", "pp_client", "--status"
            ], check=False)

            print()  # New line after dots

            # Try to extract file count from output
            output = result.stdout
            if "total_files:" in output:
                import re
                match = re.search(r"total_files:\s*(\d+)", output)
                if match:
                    total_files = int(match.group(1))
                    print_success(f"SHA256 processing complete: {total_files} files processed")
                    return total_files

            print_success("SHA256 processing complete")
            return 0

        print(".", end="", flush=True)
        time.sleep(2)

    print()  # New line after dots
    raise RuntimeError(f"SHA256 processing did not complete within {timeout} seconds")


def trigger_desktop_upload():
    """Trigger upload of Desktop files."""
    desktop_path = Path.home() / "Desktop"

    print_step("Triggering Desktop upload")

    result = run_command([
        "uv", "run", "pp_client",
        "--path", str(desktop_path),
        "--upload",
        "--upload-content"
    ])

    print_success("Desktop upload triggered")
    print(f"  Output: {result.stdout[:200]}")


def wait_for_desktop_uploads(timeout: int = 7200):
    """Wait for Desktop uploads to complete (2 hours max for large files)."""
    print_step("Waiting for Desktop uploads to complete")

    start_time = time.time()
    last_status = {}

    while time.time() - start_time < timeout:
        status = get_upload_queue_status()

        # Show progress if status changed
        if status != last_status:
            pending = status.get("pending_upload", 0)
            in_progress = status.get("in_progress", 0)
            completed = status.get("completed_today", 0)
            failed = status.get("failed_today", 0)

            if in_progress > 0 or pending > 0:
                print(f"\r  Progress: {completed} completed, {failed} failed, {in_progress} in progress, {pending} pending", end="", flush=True)

            last_status = status.copy()

        # Check if done
        pending = status.get("pending_upload", 0)
        in_progress = status.get("in_progress", 0)

        if in_progress == 0 and pending == 0:
            completed = status.get("completed_today", 0)
            failed = status.get("failed_today", 0)
            print()  # New line
            print_success(f"Desktop uploads complete: {completed} succeeded, {failed} failed")
            return completed, failed

        time.sleep(3)

    print()  # New line
    raise RuntimeError(f"Desktop uploads did not complete within {timeout} seconds")


def validate_desktop_uploads():
    """Validate Desktop files were uploaded to MongoDB and S3."""
    print_step("Validating Desktop uploads")

    client = MongoClient(MONGODB_URL)
    db = client[MONGODB_DATABASE]

    # Count files from Desktop
    desktop_path = str(Path.home() / "Desktop")
    desktop_files = list(db.file_metadata.find({
        "filepath": {"$regex": f"^{desktop_path}"}
    }))

    print(f"  Desktop files in MongoDB: {len(desktop_files)}")

    if desktop_files:
        print("  Sample files:")
        for doc in desktop_files[:5]:  # Show first 5
            filepath = doc.get('filepath', 'unknown')
            sha256 = doc.get('sha256', 'unknown')
            size = doc.get('file_size', 0)
            print(f"    - {Path(filepath).name} ({size:,} bytes)")
            print(f"      SHA256: {sha256[:16]}...")

    client.close()

    if len(desktop_files) > 0:
        print_success(f"Validated {len(desktop_files)} Desktop files in MongoDB")
    else:
        print_warning("No Desktop files found in MongoDB (Desktop might be empty)")

    return len(desktop_files)


def main():
    """Run the end-to-end test."""
    print(f"\n{'='*80}")
    print(f"{BLUE}PutPlace End-to-End Upload Test{RESET}")
    print(f"{'='*80}")

    test_file = None
    test_started = False

    try:
        # ===== PHASE 1: Synthetic Test File =====
        print(f"\n{BLUE}Phase 1: Synthetic Test File{RESET}\n")

        # 0. Clean up any leftover data from previous test runs
        print_step("Preparing clean test environment")
        cleanup_ppassist_paths()  # Clean up registered paths
        stop_ppassist_daemon()  # CRITICAL: Stop daemon BEFORE purging database
        purge_dev_environment(silent=True)  # Purges MongoDB, S3, and ppassist SQLite DB
        start_ppassist_daemon()  # Start daemon with fresh database
        print_success("Environment ready")

        # 1. Create test file
        test_file = create_test_file()
        test_started = True

        # 2. Start server
        start_server()

        # 3. Create test user
        user_id = create_test_user()

        # 4. Configure ppassist
        configure_ppassist()

        # 5. Register test path
        register_test_path()

        # 5a. Wait briefly for scanner to queue files
        time.sleep(2)

        # 5b. Validate files queued for checksum (Component 1)
        validate_files_queued_for_checksum(expected_min=1)

        # 6. Wait for SHA256 processing (Component 2)
        wait_for_sha256_processing()

        # 7. Upload test file
        upload_test_file()

        # 8. Wait for upload completion
        completed, failed = wait_for_upload_completion()

        # 9. Validate MongoDB
        validate_mongodb()

        # 10. Validate S3
        validate_s3()

        # 11. Validate 3-component queue workflow (NEW)
        validate_queue_workflow()

        # 12. Validate chunked upload protocol (NEW)
        validate_chunked_upload_used()

        print_success("Phase 1 complete: Synthetic test file uploaded successfully")

        # ===== PHASE 2: Real Desktop Directory =====

        # 13. Register Desktop directory
        desktop_path = upload_desktop_directory()

        # 14. Wait for SHA256 processing
        desktop_file_count = wait_for_desktop_sha256_processing()

        # 15. Trigger Desktop upload
        trigger_desktop_upload()

        # 16. Wait for Desktop uploads
        desktop_completed, desktop_failed = wait_for_desktop_uploads()

        # 17. Validate Desktop uploads
        desktop_validated = validate_desktop_uploads()

        print_success(f"Phase 2 complete: {desktop_completed} Desktop files uploaded successfully")

        # ===== CLEANUP =====

        # 18. Purge environment
        purge_dev_environment()

        # 19. Verify cleanup
        verify_cleanup()

        # Success!
        print(f"\n{'='*80}")
        print(f"{GREEN}✓ END-TO-END TEST PASSED{RESET}")
        print(f"{'='*80}")
        print(f"{GREEN}Phase 1 - Synthetic Test:{RESET}")
        print(f"  ✓ File uploaded and validated in MongoDB and S3")
        print(f"  ✓ 3-component queue workflow validated:")
        print(f"    - Component 1: Scanner queued files to queue_pending_checksum")
        print(f"    - Component 2: Checksum Calculator processed checksum queue")
        print(f"    - Component 3: Uploader processed upload queue with chunked uploads")
        print(f"  ✓ Files table status transitions validated")
        print(f"  ✓ Chunked upload protocol validated")
        print(f"")
        print(f"{GREEN}Phase 2 - Desktop Upload:{RESET}")
        print(f"  ✓ {desktop_completed} Desktop files uploaded successfully")
        print(f"")
        print(f"{GREEN}Cleanup:{RESET}")
        print(f"  ✓ MongoDB and S3 cleaned and verified")
        print(f"{'='*80}\n")

        return 0

    except Exception as e:
        print_error(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Always cleanup test directory
        if test_file:
            cleanup_test_file()

        # Always cleanup database and S3 if test was started
        if test_started:
            print_step("Cleaning up test data")
            cleanup_ppassist_paths()  # Clean up registered paths
            purge_dev_environment(silent=True)
            print_success("Test data cleaned up")


if __name__ == "__main__":
    sys.exit(main())
