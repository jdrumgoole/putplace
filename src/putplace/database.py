"""MongoDB database connection and operations."""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import (
    ConnectionFailure,
    DuplicateKeyError,
    OperationFailure,
    ServerSelectionTimeoutError,
)

from .config import settings

logger = logging.getLogger(__name__)


class MongoDB:
    """MongoDB connection manager."""

    client: Optional[AsyncIOMotorClient] = None
    collection: Optional[AsyncIOMotorCollection] = None

    async def connect(self) -> None:
        """Connect to MongoDB.

        Raises:
            ConnectionFailure: If unable to connect to MongoDB
            ServerSelectionTimeoutError: If connection times out
            OperationFailure: If authentication or other operation fails
        """
        try:
            logger.info(f"Connecting to MongoDB at {settings.mongodb_url}")
            self.client = AsyncIOMotorClient(
                settings.mongodb_url,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
            )

            # Verify connection by pinging the server
            await self.client.admin.command("ping")
            logger.info("Successfully connected to MongoDB")

            db = self.client[settings.mongodb_database]
            self.collection = db[settings.mongodb_collection]

            # Create indexes on sha256 for efficient lookups
            await self.collection.create_index("sha256")
            await self.collection.create_index([("hostname", 1), ("filepath", 1)])
            logger.info("Database indexes created successfully")

        except ServerSelectionTimeoutError as e:
            logger.error(f"MongoDB connection timeout: {e}")
            self.client = None
            self.collection = None
            raise ConnectionFailure(f"Could not connect to MongoDB at {settings.mongodb_url}") from e
        except ConnectionFailure as e:
            logger.error(f"MongoDB connection failed: {e}")
            self.client = None
            self.collection = None
            raise
        except OperationFailure as e:
            logger.error(f"MongoDB operation failed (check authentication): {e}")
            self.client = None
            self.collection = None
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            self.client = None
            self.collection = None
            raise ConnectionFailure(f"Unexpected error connecting to MongoDB: {e}") from e

    async def close(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            logger.info("Closing MongoDB connection")
            self.client.close()

    async def is_healthy(self) -> bool:
        """Check if database connection is healthy.

        Returns:
            True if database is reachable, False otherwise
        """
        if self.client is None or self.collection is None:
            return False

        try:
            # Ping the database to verify connection
            await self.client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return False

    async def insert_file_metadata(self, data: dict) -> str:
        """Insert file metadata into MongoDB.

        Args:
            data: File metadata dictionary

        Returns:
            Inserted document ID

        Raises:
            RuntimeError: If database not connected
            ConnectionFailure: If database connection is lost
            OperationFailure: If database operation fails
        """
        if self.collection is None:
            raise RuntimeError("Database not connected")

        try:
            # Make a copy to avoid modifying the input dict
            # (insert_one adds an _id field to the dict)
            data_copy = data.copy()
            result = await self.collection.insert_one(data_copy)
            return str(result.inserted_id)
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Database connection lost during insert: {e}")
            raise ConnectionFailure("Lost connection to database") from e
        except OperationFailure as e:
            logger.error(f"Database operation failed during insert: {e}")
            raise

    async def find_by_sha256(self, sha256: str) -> Optional[dict]:
        """Find file metadata by SHA256 hash.

        Args:
            sha256: SHA256 hash to search for

        Returns:
            File metadata document or None if not found

        Raises:
            RuntimeError: If database not connected
            ConnectionFailure: If database connection is lost
            OperationFailure: If database operation fails
        """
        if self.collection is None:
            raise RuntimeError("Database not connected")

        try:
            return await self.collection.find_one({"sha256": sha256})
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Database connection lost during find: {e}")
            raise ConnectionFailure("Lost connection to database") from e
        except OperationFailure as e:
            logger.error(f"Database operation failed during find: {e}")
            raise


# Global database instance
mongodb = MongoDB()
