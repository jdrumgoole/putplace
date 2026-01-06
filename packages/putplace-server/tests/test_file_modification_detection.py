"""
Test file modification detection during upload.

This test verifies that when a file is modified between scanning and uploading,
the system detects the change and requeues the file for re-processing.
"""
import asyncio
import os
import random
import shutil
import tempfile
import time
from pathlib import Path

import pytest


class TestFileModificationDetection:
    """Test suite for file modification detection during uploads."""

    @pytest.fixture
    def test_dir(self):
        """Create a temporary test directory and clean up after test."""
        temp_dir = tempfile.mkdtemp(prefix="putplace_modtest_")
        yield Path(temp_dir)
        # Cleanup
        if Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    async def ppassist_daemon(self):
        """Start ppassist daemon for testing."""
        import subprocess
        import httpx

        # Start daemon
        proc = subprocess.Popen(
            ["uv", "run", "pp_assist", "start", "--foreground"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait for daemon to be ready by checking health endpoint
        daemon_ready = False
        for attempt in range(30):  # 30 attempts with 0.5s delay = 15 seconds max
            await asyncio.sleep(0.5)
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get("http://localhost:8765/health", timeout=1.0)
                    if response.status_code == 200:
                        daemon_ready = True
                        print("✓ Daemon ready")
                        break
            except (httpx.ConnectError, httpx.TimeoutException):
                pass

        if not daemon_ready:
            proc.kill()
            raise RuntimeError("ppassist daemon failed to start within 15 seconds")

        yield proc

        # Stop daemon
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def create_file_tree(self, base_dir: Path, num_files: int = 10, min_size: int = 3000, max_size: int = 150000):
        """Create a tree of files with varying sizes.

        Args:
            base_dir: Base directory for file tree
            num_files: Number of files to create
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes

        Returns:
            List of created file paths
        """
        files = []

        # Create directory structure (3 levels deep)
        for i in range(3):
            level_dir = base_dir / f"level{i+1}"
            level_dir.mkdir(exist_ok=True)

            for j in range(num_files // 3 + 1):
                if len(files) >= num_files:
                    break

                file_path = level_dir / f"file_{len(files):04d}.txt"
                file_size = random.randint(min_size, max_size)

                # Generate random content
                content = f"File {len(files)}\n"
                content += "=" * 50 + "\n"
                content += "Random data: " + "x" * (file_size - len(content))

                file_path.write_text(content[:file_size])
                files.append(file_path)

        return files

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_file_modification_detection(self, test_dir, ppassist_daemon):
        """Test that file modifications during upload are detected and handled."""
        try:
            # Create test files
            print(f"\nCreating test files in {test_dir}")
            files = self.create_file_tree(test_dir, num_files=10)
            print(f"Created {len(files)} test files")

            # Select a file to modify during upload (middle file)
            target_file = files[len(files) // 2]
            original_size = target_file.stat().st_size
            original_mtime = target_file.stat().st_mtime
            print(f"Target file for modification: {target_file}")
            print(f"Original size: {original_size}, mtime: {original_mtime}")

            # Register directory with ppassist (daemon runs on port 8765)
            import httpx
            PPASSIST_URL = "http://localhost:8765"

            async with httpx.AsyncClient() as client:
                # Register path
                response = await client.post(
                    f"{PPASSIST_URL}/paths",
                    json={"path": str(test_dir), "recursive": True}
                )
                assert response.status_code == 200
                path_data = response.json()
                path_id = path_data["id"]
                print(f"Registered path with ID: {path_id}")

                # Trigger scan
                response = await client.post(
                    f"{PPASSIST_URL}/paths/{path_id}/scan"
                )
                assert response.status_code == 200
                print("Scan initiated")

                # Wait for scan to complete
                await asyncio.sleep(3)

                # Check file stats
                response = await client.get(f"{PPASSIST_URL}/files/stats")
                assert response.status_code == 200
                stats = response.json()
                print(f"Files tracked: {stats['total_files']}")

                # Trigger uploads
                response = await client.post(
                    f"{PPASSIST_URL}/uploads",
                    json={"upload_content": True, "limit": 100}
                )
                assert response.status_code == 200
                upload_data = response.json()
                print(f"Upload triggered: {upload_data['files_queued']} files queued")

                # Immediately modify the target file (before it gets uploaded)
                await asyncio.sleep(0.5)  # Small delay to ensure upload has started

                print(f"\nModifying {target_file} during upload...")
                with open(target_file, "a") as f:
                    f.write("\n" + "=" * 100 + "\n")
                    f.write("MODIFIED CONTENT ADDED DURING UPLOAD\n")
                    f.write("x" * 10000)  # Add 10KB more data

                new_size = target_file.stat().st_size
                new_mtime = target_file.stat().st_mtime
                print(f"Modified size: {new_size}, mtime: {new_mtime}")
                print(f"Size change: {new_size - original_size} bytes")
                print(f"Mtime change: {new_mtime - original_mtime} seconds")

                # Wait for uploads to process
                await asyncio.sleep(10)

                # Check activity log for FILE_MODIFIED event
                response = await client.get(
                    f"{PPASSIST_URL}/activity",
                    params={"limit": 100, "event_type": "FILE_MODIFIED"}
                )
                assert response.status_code == 200
                activity = response.json()

                print(f"\nChecking for FILE_MODIFIED events...")
                file_modified_events = [
                    event for event in activity["events"]
                    if event["event_type"] == "FILE_MODIFIED" and str(target_file) in event.get("filepath", "")
                ]

                if file_modified_events:
                    print(f"✓ FILE_MODIFIED event detected for {target_file}")
                    event = file_modified_events[0]
                    print(f"  Event details: {event.get('details', {})}")

                    # Verify the event contains expected information
                    details = event.get("details", {})
                    assert "old_size" in details, "Event should contain old_size"
                    assert "new_size" in details, "Event should contain new_size"
                    assert details["old_size"] == original_size, "Old size should match original"
                    assert details["new_size"] == new_size, "New size should match modified size"

                    print("✓ File modification was detected and logged correctly")
                else:
                    print(f"✗ No FILE_MODIFIED event found for {target_file}")
                    print(f"All events: {activity['events']}")
                    pytest.fail("File modification was not detected")

                # Verify file was requeued (should be pending again)
                response = await client.get(
                    f"{PPASSIST_URL}/files",
                    params={"path_prefix": str(target_file), "limit": 1}
                )
                assert response.status_code == 200
                file_info = response.json()

                print(f"\nChecking file upload status...")
                if file_info["entries"]:
                    entry = file_info["entries"][0]
                    print(f"File entry: upload_status={entry.get('upload_status')}, size={entry.get('file_size')}")

                    # The modified file should either:
                    # 1. Have a NULL upload_status (requeued for upload)
                    # 2. Have the updated size
                    assert entry.get("file_size") == new_size or entry.get("upload_status") is None, \
                        "File should be requeued with new size"
                    print("✓ File was properly requeued")

                print("\n✓ File modification detection test PASSED")

        except Exception as e:
            print(f"\n✗ Test failed with error: {e}")
            raise


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
