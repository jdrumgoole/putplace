"""Background cleanup tasks for expired pending users and upload sessions."""

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .database import mongodb

logger = logging.getLogger(__name__)


async def cleanup_expired_pending_users_task():
    """
    Periodically clean up expired pending users.

    Runs every hour and deletes pending users whose confirmation has expired.
    """
    while True:
        try:
            # Wait 1 hour between cleanup runs
            await asyncio.sleep(3600)  # 3600 seconds = 1 hour

            logger.info("Running cleanup task for expired pending users...")

            # Delete expired pending users
            deleted_count = await mongodb.cleanup_expired_pending_users()

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired pending user(s)")
            else:
                logger.debug("No expired pending users to clean up")

        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            # Continue running even if there's an error
            continue


async def cleanup_expired_upload_sessions_task():
    """
    Periodically clean up expired upload sessions.

    Runs every hour and deletes expired upload sessions along with their temporary chunk files.
    """
    while True:
        try:
            # Wait 1 hour between cleanup runs
            await asyncio.sleep(3600)  # 3600 seconds = 1 hour

            logger.info("Running cleanup task for expired upload sessions...")

            # Get expired sessions before deleting to clean up chunk files
            expired_sessions = []
            if mongodb.upload_sessions_collection:
                cursor = mongodb.upload_sessions_collection.find({
                    "expires_at": {"$lt": datetime.utcnow()},
                    "status": {"$ne": "completed"}
                })
                async for session in cursor:
                    expired_sessions.append(session)

            # Delete expired upload sessions from database
            deleted_count = await mongodb.cleanup_expired_upload_sessions()

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired upload session(s)")

                # Clean up temporary chunk files for expired sessions
                chunk_base_dir = Path("/tmp/putplace_chunks")
                if chunk_base_dir.exists():
                    for session in expired_sessions:
                        upload_id = session.get("upload_id")
                        if upload_id:
                            chunk_dir = chunk_base_dir / upload_id
                            if chunk_dir.exists():
                                try:
                                    shutil.rmtree(chunk_dir)
                                    logger.debug(f"Cleaned up chunk directory for expired session: {upload_id}")
                                except Exception as e:
                                    logger.error(f"Failed to clean up chunk directory {chunk_dir}: {e}")
            else:
                logger.debug("No expired upload sessions to clean up")

        except Exception as e:
            logger.error(f"Error in upload session cleanup task: {e}")
            # Continue running even if there's an error
            continue


def start_cleanup_task():
    """Start the cleanup background tasks."""
    asyncio.create_task(cleanup_expired_pending_users_task())
    logger.info("Started background cleanup task for expired pending users")

    asyncio.create_task(cleanup_expired_upload_sessions_task())
    logger.info("Started background cleanup task for expired upload sessions")
