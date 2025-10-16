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
    users_collection: Optional[AsyncIOMotorCollection] = None

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
            self.users_collection = db["users"]

            # Create indexes on sha256 for efficient lookups
            await self.collection.create_index("sha256")
            await self.collection.create_index([("hostname", 1), ("filepath", 1)])
            logger.info("File metadata indexes created successfully")

            # Create indexes for API keys collection
            api_keys_collection = db["api_keys"]
            await api_keys_collection.create_index("key_hash", unique=True)
            await api_keys_collection.create_index([("is_active", 1)])
            logger.info("API keys indexes created successfully")

            # Create indexes for users collection
            await self.users_collection.create_index("username", unique=True)
            await self.users_collection.create_index("email", unique=True)
            logger.info("Users indexes created successfully")

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

    async def has_file_content(self, sha256: str) -> bool:
        """Check if server already has file content for this SHA256.

        Args:
            sha256: SHA256 hash to check

        Returns:
            True if file content exists, False otherwise

        Raises:
            RuntimeError: If database not connected
            ConnectionFailure: If database connection is lost
        """
        if self.collection is None:
            raise RuntimeError("Database not connected")

        try:
            # Check if any document with this SHA256 has file content
            result = await self.collection.find_one(
                {"sha256": sha256, "has_file_content": True}
            )
            return result is not None
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Database connection lost during has_file_content check: {e}")
            raise ConnectionFailure("Lost connection to database") from e
        except OperationFailure as e:
            logger.error(f"Database operation failed during has_file_content check: {e}")
            raise

    async def mark_file_uploaded(self, sha256: str, hostname: str, filepath: str) -> bool:
        """Mark that file content has been uploaded for a specific metadata record.

        Args:
            sha256: SHA256 hash of the file
            hostname: Hostname where file is located
            filepath: Full path to the file

        Returns:
            True if updated successfully, False if not found

        Raises:
            RuntimeError: If database not connected
            ConnectionFailure: If database connection is lost
        """
        if self.collection is None:
            raise RuntimeError("Database not connected")

        try:
            from datetime import datetime

            result = await self.collection.update_one(
                {"sha256": sha256, "hostname": hostname, "filepath": filepath},
                {
                    "$set": {
                        "has_file_content": True,
                        "file_uploaded_at": datetime.utcnow(),
                    }
                },
            )
            return result.modified_count > 0
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Database connection lost during mark_file_uploaded: {e}")
            raise ConnectionFailure("Lost connection to database") from e
        except OperationFailure as e:
            logger.error(f"Database operation failed during mark_file_uploaded: {e}")
            raise

    # User authentication methods

    async def create_user(self, username: str, email: str, hashed_password: str, full_name: Optional[str] = None) -> str:
        """Create a new user.

        Args:
            username: User's username
            email: User's email
            hashed_password: Hashed password
            full_name: User's full name (optional)

        Returns:
            Inserted user document ID

        Raises:
            RuntimeError: If database not connected
            DuplicateKeyError: If username or email already exists
        """
        if self.users_collection is None:
            raise RuntimeError("Database not connected")

        from datetime import datetime

        user_data = {
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "full_name": full_name,
            "is_active": True,
            "created_at": datetime.utcnow(),
        }

        try:
            result = await self.users_collection.insert_one(user_data)
            return str(result.inserted_id)
        except DuplicateKeyError as e:
            if "username" in str(e):
                raise DuplicateKeyError("Username already exists")
            elif "email" in str(e):
                raise DuplicateKeyError("Email already exists")
            raise

    async def get_user_by_username(self, username: str) -> Optional[dict]:
        """Get user by username.

        Args:
            username: Username to search for

        Returns:
            User document or None if not found
        """
        if self.users_collection is None:
            raise RuntimeError("Database not connected")

        return await self.users_collection.find_one({"username": username})

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        """Get user by email.

        Args:
            email: Email to search for

        Returns:
            User document or None if not found
        """
        if self.users_collection is None:
            raise RuntimeError("Database not connected")

        return await self.users_collection.find_one({"email": email})


# Global database instance
mongodb = MongoDB()
