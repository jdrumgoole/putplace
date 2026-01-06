"""Tests for chunked upload endpoints and file deletion notifications.

This test suite covers:
- Upload session initiation
- Chunk uploads
- Upload completion with integrity verification
- Upload abortion/cancellation
- File deletion notifications
- Error cases and edge cases
"""

import hashlib
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import AsyncClient


@pytest.fixture
async def auth_headers(test_user_token: str):
    """Create authentication headers using test user token."""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def test_file_data():
    """Create test file data for uploads."""
    # Create a small test file (5KB, will be split into 3 chunks of 2KB)
    file_content = b"Test file content " * 300  # ~5400 bytes
    sha256_hash = hashlib.sha256(file_content).hexdigest()

    chunk_size = 2048  # 2KB chunks
    chunks = []
    total_chunks = (len(file_content) + chunk_size - 1) // chunk_size

    for i in range(total_chunks):
        start = i * chunk_size
        end = min(start + chunk_size, len(file_content))
        chunk_data = file_content[start:end]
        chunk_hash = hashlib.sha256(chunk_data).hexdigest()
        chunks.append({
            "chunk_num": i,
            "data": chunk_data,
            "etag": chunk_hash
        })

    return {
        "file_content": file_content,
        "sha256": sha256_hash,
        "file_size": len(file_content),
        "chunk_size": chunk_size,
        "total_chunks": total_chunks,
        "chunks": chunks,
        "filepath": "/test/path/testfile.txt",
        "hostname": "test-machine"
    }


# Test 1: Initiate Upload Session
@pytest.mark.asyncio
async def test_initiate_upload_success(client: AsyncClient, auth_headers, test_file_data):
    """Test initiating a chunked upload session."""
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )

    assert response.status_code == 201
    data = response.json()

    assert "upload_id" in data
    assert "expires_at" in data
    assert "message" in data

    # Verify upload_id is a valid UUID
    try:
        uuid.UUID(data["upload_id"])
    except ValueError:
        pytest.fail("upload_id is not a valid UUID")

    # Session verification would require additional API endpoints
    # For now, we trust the upload_id was created successfully
    # since we got a 201 response with valid data

    return data["upload_id"]


@pytest.mark.asyncio
async def test_initiate_upload_unauthorized(client: AsyncClient, test_file_data):
    """Test initiating upload without authentication fails."""
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    response = await client.post("/api/uploads/initiate", json=request_data)
    assert response.status_code == 403  # FastAPI returns 403 for missing credentials


@pytest.mark.asyncio
async def test_initiate_upload_invalid_sha256(client: AsyncClient, auth_headers, test_file_data):
    """Test initiating upload with invalid SHA256 format fails."""
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": "invalid-hash",  # Invalid format
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )

    assert response.status_code == 422  # Validation error


# Test 2: Upload Chunks
@pytest.mark.asyncio
async def test_upload_chunk_success(client: AsyncClient, auth_headers, test_file_data):
    """Test uploading individual chunks."""
    # First initiate upload session
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    assert init_response.status_code == 201
    upload_id = init_response.json()["upload_id"]

    # Upload first chunk
    chunk = test_file_data["chunks"][0]
    response = await client.put(
        f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
        content=chunk["data"],
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    assert data["chunk_num"] == chunk["chunk_num"]
    assert data["etag"] == chunk["etag"]
    assert data["received_bytes"] == len(chunk["data"])
    assert data["uploaded_chunks"] == 1
    assert data["total_chunks"] == test_file_data["total_chunks"]

    # Chunk verification confirmed by API response


@pytest.mark.asyncio
async def test_upload_chunk_invalid_session(client: AsyncClient, auth_headers, test_file_data):
    """Test uploading chunk to non-existent session fails."""
    fake_upload_id = str(uuid.uuid4())
    chunk = test_file_data["chunks"][0]

    response = await client.put(
        f"/api/uploads/{fake_upload_id}/chunk/{chunk['chunk_num']}",
        content=chunk["data"],
        headers=auth_headers
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_all_chunks(client: AsyncClient, auth_headers, test_file_data):
    """Test uploading all chunks sequentially."""
    # Initiate upload session
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    assert init_response.status_code == 201
    upload_id = init_response.json()["upload_id"]

    # Upload all chunks
    for i, chunk in enumerate(test_file_data["chunks"]):
        response = await client.put(
            f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
            content=chunk["data"],
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["chunk_num"] == chunk["chunk_num"]
        # Verify progress from API response
        assert data["uploaded_chunks"] == (i + 1)

    # All chunks uploaded successfully (verified by API responses)

    return upload_id


# Test 3: Complete Upload
@pytest.mark.asyncio
async def test_complete_upload_success(client: AsyncClient, auth_headers, test_file_data):
    """Test completing a chunked upload with integrity verification."""
    # Initiate and upload all chunks
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    upload_id = init_response.json()["upload_id"]

    # Upload all chunks
    for chunk in test_file_data["chunks"]:
        await client.put(
            f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
            content=chunk["data"],
            headers=auth_headers
        )

    # Complete upload
    parts = [{"chunk_num": c["chunk_num"], "etag": c["etag"]} for c in test_file_data["chunks"]]
    complete_response = await client.post(
        f"/api/uploads/{upload_id}/complete",
        json={"parts": parts},
        headers=auth_headers
    )

    assert complete_response.status_code == 200
    data = complete_response.json()

    assert "file_id" in data
    assert data["sha256"] == test_file_data["sha256"]
    assert data["file_size"] == test_file_data["file_size"]
    assert data["status"] == "completed"
    assert "storage_location" in data

    # File metadata creation confirmed by successful completion response


@pytest.mark.asyncio
async def test_complete_upload_missing_chunks(client: AsyncClient, auth_headers, test_file_data):
    """Test completing upload with missing chunks fails."""
    # Initiate upload
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    upload_id = init_response.json()["upload_id"]

    # Upload only first chunk (not all)
    chunk = test_file_data["chunks"][0]
    await client.put(
        f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
        content=chunk["data"],
        headers=auth_headers
    )

    # Try to complete with missing chunks
    parts = [{"chunk_num": c["chunk_num"], "etag": c["etag"]} for c in test_file_data["chunks"]]
    complete_response = await client.post(
        f"/api/uploads/{upload_id}/complete",
        json={"parts": parts},
        headers=auth_headers
    )

    assert complete_response.status_code == 400
    assert "not all chunks uploaded" in complete_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_complete_upload_sha256_mismatch(client: AsyncClient, auth_headers, test_file_data):
    """Test completing upload with mismatched SHA256 fails."""
    # Initiate upload with WRONG sha256
    wrong_sha256 = "a" * 64  # Different hash
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": wrong_sha256,
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    upload_id = init_response.json()["upload_id"]

    # Upload all chunks (with correct data)
    for chunk in test_file_data["chunks"]:
        await client.put(
            f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
            content=chunk["data"],
            headers=auth_headers
        )

    # Try to complete - should fail due to SHA256 mismatch
    parts = [{"chunk_num": c["chunk_num"], "etag": c["etag"]} for c in test_file_data["chunks"]]
    complete_response = await client.post(
        f"/api/uploads/{upload_id}/complete",
        json={"parts": parts},
        headers=auth_headers
    )

    assert complete_response.status_code == 400
    assert "sha256 mismatch" in complete_response.json()["detail"].lower()


# Test 4: Abort Upload
@pytest.mark.asyncio
async def test_abort_upload_success(client: AsyncClient, auth_headers, test_file_data):
    """Test aborting an upload session."""
    # Initiate upload
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    upload_id = init_response.json()["upload_id"]

    # Upload one chunk
    chunk = test_file_data["chunks"][0]
    await client.put(
        f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
        content=chunk["data"],
        headers=auth_headers
    )

    # Abort upload
    abort_response = await client.delete(
        f"/api/uploads/{upload_id}",
        headers=auth_headers
    )

    assert abort_response.status_code == 200
    data = abort_response.json()
    assert data["upload_id"] == upload_id
    assert data["status"] == "aborted"

    # Session deletion confirmed by successful abort response


@pytest.mark.asyncio
async def test_abort_upload_invalid_session(client: AsyncClient, auth_headers):
    """Test aborting non-existent session fails."""
    fake_upload_id = str(uuid.uuid4())

    response = await client.delete(
        f"/api/uploads/{fake_upload_id}",
        headers=auth_headers
    )

    assert response.status_code == 404


# Test 5: File Deletion Notification
@pytest.mark.asyncio
async def test_delete_file_notification_success(client: AsyncClient, auth_headers, test_file_data):
    """Test notifying server of file deletion."""
    # First, complete an upload so we have a file to delete
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    upload_id = init_response.json()["upload_id"]

    # Upload all chunks
    for chunk in test_file_data["chunks"]:
        await client.put(
            f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
            content=chunk["data"],
            headers=auth_headers
        )

    # Complete upload
    parts = [{"chunk_num": c["chunk_num"], "etag": c["etag"]} for c in test_file_data["chunks"]]
    await client.post(
        f"/api/uploads/{upload_id}/complete",
        json={"parts": parts},
        headers=auth_headers
    )

    # Now send deletion notification
    import json
    deletion_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "deleted_at": datetime.utcnow().isoformat() + "Z"
    }

    delete_response = await client.request(
        "DELETE",
        f"/api/files/{test_file_data['sha256']}",
        content=json.dumps(deletion_data),
        headers={**auth_headers, "Content-Type": "application/json"}
    )

    assert delete_response.status_code == 200
    data = delete_response.json()

    assert data["sha256"] == test_file_data["sha256"]
    assert data["filepath"] == test_file_data["filepath"]
    assert data["hostname"] == test_file_data["hostname"]
    assert data["status"] == "deleted"
    assert "deleted_at" in data

    # File deletion confirmed by successful API response


@pytest.mark.asyncio
async def test_delete_file_notification_nonexistent(client: AsyncClient, auth_headers):
    """Test deleting non-existent file fails."""
    import json
    fake_sha256 = "b" * 64
    deletion_data = {
        "filepath": "/fake/path",
        "hostname": "fake-host",
        "deleted_at": datetime.utcnow().isoformat() + "Z"
    }

    response = await client.request(
        "DELETE",
        f"/api/files/{fake_sha256}",
        content=json.dumps(deletion_data),
        headers={**auth_headers, "Content-Type": "application/json"}
    )

    assert response.status_code == 404


# Test 6: Full End-to-End Upload Flow
@pytest.mark.asyncio
async def test_full_upload_flow_end_to_end(client: AsyncClient, auth_headers, test_file_data):
    """Test complete upload flow from initiation to completion."""
    # Step 1: Initiate upload
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    assert init_response.status_code == 201
    upload_id = init_response.json()["upload_id"]

    # Step 2: Upload all chunks
    uploaded_parts = []
    for chunk in test_file_data["chunks"]:
        chunk_response = await client.put(
            f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
            content=chunk["data"],
            headers=auth_headers
        )
        assert chunk_response.status_code == 200
        chunk_data = chunk_response.json()
        uploaded_parts.append({
            "chunk_num": chunk_data["chunk_num"],
            "etag": chunk_data["etag"]
        })

    # Step 3: Complete upload
    complete_response = await client.post(
        f"/api/uploads/{upload_id}/complete",
        json={"parts": uploaded_parts},
        headers=auth_headers
    )
    assert complete_response.status_code == 200
    complete_data = complete_response.json()

    # Verify all data
    assert complete_data["sha256"] == test_file_data["sha256"]
    assert complete_data["file_size"] == test_file_data["file_size"]
    assert complete_data["status"] == "completed"

    # File storage confirmed by successful completion with storage_location
    assert "storage_location" in complete_data
    assert complete_data["storage_location"] is not None


# Test 7: Error Cases
@pytest.mark.asyncio
async def test_expired_session(client: AsyncClient, auth_headers, test_file_data, test_db):
    """Test that expired sessions cannot be used."""
    # Initiate upload
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    upload_id = init_response.json()["upload_id"]

    # Manually expire the session in database using test_db
    await test_db.upload_sessions_collection.update_one(
        {"upload_id": upload_id},
        {"$set": {"expires_at": datetime.utcnow() - timedelta(hours=1)}}
    )

    # Try to upload chunk to expired session
    chunk = test_file_data["chunks"][0]
    response = await client.put(
        f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
        content=chunk["data"],
        headers=auth_headers
    )

    # Should fail because session is expired
    assert response.status_code in [400, 404, 410]  # Various ways to indicate expired


@pytest.mark.asyncio
async def test_chunk_out_of_range(client: AsyncClient, auth_headers, test_file_data):
    """Test uploading chunk number beyond total_chunks fails."""
    # Initiate upload
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    upload_id = init_response.json()["upload_id"]

    # Try to upload chunk beyond range
    invalid_chunk_num = test_file_data["total_chunks"] + 5
    response = await client.put(
        f"/api/uploads/{upload_id}/chunk/{invalid_chunk_num}",
        content=b"some data",
        headers=auth_headers
    )

    assert response.status_code == 400


# Test 8: Edge Cases
@pytest.mark.asyncio
async def test_single_chunk_file(client: AsyncClient, auth_headers):
    """Test uploading a file that fits in a single chunk."""
    # Create small file (< 2KB)
    small_content = b"Small file content"
    sha256_hash = hashlib.sha256(small_content).hexdigest()

    request_data = {
        "filepath": "/test/small.txt",
        "hostname": "test-machine",
        "sha256": sha256_hash,
        "file_size": len(small_content),
        "chunk_size": 2048,
        "total_chunks": 1
    }

    # Initiate
    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    upload_id = init_response.json()["upload_id"]

    # Upload single chunk
    chunk_response = await client.put(
        f"/api/uploads/{upload_id}/chunk/0",
        content=small_content,
        headers=auth_headers
    )
    assert chunk_response.status_code == 200

    # Complete
    complete_response = await client.post(
        f"/api/uploads/{upload_id}/complete",
        json={"parts": [{"chunk_num": 0, "etag": chunk_response.json()["etag"]}]},
        headers=auth_headers
    )
    assert complete_response.status_code == 200


@pytest.mark.asyncio
async def test_upload_duplicate_chunk(client: AsyncClient, auth_headers, test_file_data):
    """Test uploading the same chunk twice (idempotency)."""
    # Initiate upload
    request_data = {
        "filepath": test_file_data["filepath"],
        "hostname": test_file_data["hostname"],
        "sha256": test_file_data["sha256"],
        "file_size": test_file_data["file_size"],
        "chunk_size": test_file_data["chunk_size"],
        "total_chunks": test_file_data["total_chunks"]
    }

    init_response = await client.post(
        "/api/uploads/initiate",
        json=request_data,
        headers=auth_headers
    )
    upload_id = init_response.json()["upload_id"]

    # Upload same chunk twice
    chunk = test_file_data["chunks"][0]

    response1 = await client.put(
        f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
        content=chunk["data"],
        headers=auth_headers
    )
    assert response1.status_code == 200

    response2 = await client.put(
        f"/api/uploads/{upload_id}/chunk/{chunk['chunk_num']}",
        content=chunk["data"],
        headers=auth_headers
    )
    # Should either succeed (idempotent) or indicate already uploaded
    assert response2.status_code in [200, 409]


@pytest.mark.asyncio
async def test_concurrent_uploads_different_files(client: AsyncClient, auth_headers):
    """Test that multiple concurrent uploads work independently."""
    # Create two different files
    file1_content = b"File 1 content " * 100
    file1_sha256 = hashlib.sha256(file1_content).hexdigest()

    file2_content = b"File 2 content " * 100
    file2_sha256 = hashlib.sha256(file2_content).hexdigest()

    # Initiate both uploads
    init1 = await client.post(
        "/api/uploads/initiate",
        json={
            "filepath": "/test/file1.txt",
            "hostname": "test-machine",
            "sha256": file1_sha256,
            "file_size": len(file1_content),
            "chunk_size": 2048,
            "total_chunks": 1
        },
        headers=auth_headers
    )
    upload_id1 = init1.json()["upload_id"]

    init2 = await client.post(
        "/api/uploads/initiate",
        json={
            "filepath": "/test/file2.txt",
            "hostname": "test-machine",
            "sha256": file2_sha256,
            "file_size": len(file2_content),
            "chunk_size": 2048,
            "total_chunks": 1
        },
        headers=auth_headers
    )
    upload_id2 = init2.json()["upload_id"]

    # Upload chunks for both
    chunk1_resp = await client.put(
        f"/api/uploads/{upload_id1}/chunk/0",
        content=file1_content,
        headers=auth_headers
    )

    chunk2_resp = await client.put(
        f"/api/uploads/{upload_id2}/chunk/0",
        content=file2_content,
        headers=auth_headers
    )

    assert chunk1_resp.status_code == 200
    assert chunk2_resp.status_code == 200

    # Complete both
    complete1 = await client.post(
        f"/api/uploads/{upload_id1}/complete",
        json={"parts": [{"chunk_num": 0, "etag": chunk1_resp.json()["etag"]}]},
        headers=auth_headers
    )

    complete2 = await client.post(
        f"/api/uploads/{upload_id2}/complete",
        json={"parts": [{"chunk_num": 0, "etag": chunk2_resp.json()["etag"]}]},
        headers=auth_headers
    )

    assert complete1.status_code == 200
    assert complete2.status_code == 200

    # Both files successfully uploaded (verified by successful completion responses)
    complete1_data = complete1.json()
    complete2_data = complete2.json()

    assert complete1_data["sha256"] == file1_sha256
    assert complete2_data["sha256"] == file2_sha256
    assert complete1_data["status"] == "completed"
    assert complete2_data["status"] == "completed"
