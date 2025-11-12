"""Background cleanup tasks for expired pending users."""

import asyncio
import logging
from datetime import datetime

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


def start_cleanup_task():
    """Start the cleanup background task."""
    asyncio.create_task(cleanup_expired_pending_users_task())
    logger.info("Started background cleanup task for expired pending users")
