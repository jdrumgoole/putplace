"""MongoDB database connection and operations."""

import logging
from typing import Optional

from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection
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

    client: Optional[AsyncMongoClient] = None
    collection: Optional[AsyncCollection] = None
    users_collection: Optional[AsyncCollection] = None
    pending_users_collection: Optional[AsyncCollection] = None

    async def connect(self) -> None:
        """Connect to MongoDB.

        Raises:
            ConnectionFailure: If unable to connect to MongoDB
            ServerSelectionTimeoutError: If connection times out
            OperationFailure: If authentication or other operation fails
        """
        try:
            logger.info(f"Connecting to MongoDB at {settings.mongodb_url}")
            self.client = AsyncMongoClient(
                settings.mongodb_url,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
            )

            # Verify connection by pinging the server
            await self.client.admin.command("ping")
            logger.info("Successfully connected to MongoDB")

            db = self.client[settings.mongodb_database]
            self.collection = db[settings.mongodb_collection]
            self.users_collection = db["users"]
            self.pending_users_collection = db["pending_users"]

            # Create indexes on sha256 for efficient lookups
            await self.collection.create_index("sha256")
            await self.collection.create_index([("hostname", 1), ("filepath", 1)])
            await self.collection.create_index("uploaded_by_user_id")
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

            # Create indexes for pending_users collection
            await self.pending_users_collection.create_index("confirmation_token", unique=True)
            await self.pending_users_collection.create_index("email", unique=True)
            await self.pending_users_collection.create_index("expires_at")  # For cleanup queries
            logger.info("Pending users indexes created successfully")

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
            await self.client.close()

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

    async def mark_file_uploaded(self, sha256: str, hostname: str, filepath: str, storage_path: str) -> bool:
        """Mark that file content has been uploaded for a specific metadata record.

        Args:
            sha256: SHA256 hash of the file
            hostname: Hostname where file is located
            filepath: Full path to the file
            storage_path: Full storage path where file is stored (local path or S3 URI)

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
                        "storage_path": storage_path,
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

    async def get_files_by_user(self, user_id: str, limit: int = 100, skip: int = 0) -> list[dict]:
        """Get all files uploaded by a specific user.

        Args:
            user_id: User ID to filter by
            limit: Maximum number of files to return
            skip: Number of files to skip (for pagination)

        Returns:
            List of file metadata documents

        Raises:
            RuntimeError: If database not connected
            ConnectionFailure: If database connection is lost
        """
        if self.collection is None:
            raise RuntimeError("Database not connected")

        try:
            cursor = self.collection.find(
                {"uploaded_by_user_id": user_id}
            ).sort("created_at", -1).limit(limit).skip(skip)

            files = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                files.append(doc)

            return files
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Database connection lost during get_files_by_user: {e}")
            raise ConnectionFailure("Lost connection to database") from e
        except OperationFailure as e:
            logger.error(f"Database operation failed during get_files_by_user: {e}")
            raise

    async def get_files_by_sha256(self, sha256: str) -> list[dict]:
        """Get all files with a specific SHA256 hash (across all users).

        Args:
            sha256: SHA256 hash to search for

        Returns:
            List of file metadata documents, sorted with epoch file first

        Raises:
            RuntimeError: If database not connected
            ConnectionFailure: If database connection is lost
        """
        if self.collection is None:
            raise RuntimeError("Database not connected")

        try:
            cursor = self.collection.find({"sha256": sha256})

            files = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                files.append(doc)

            # Sort: files with content first (by upload time), then metadata-only (by created time)
            def sort_key(file):
                if file.get("has_file_content"):
                    # Files with content: sort by upload time (earliest first)
                    return (0, file.get("file_uploaded_at", file.get("created_at")))
                else:
                    # Files without content: sort after files with content
                    return (1, file.get("created_at"))

            files.sort(key=sort_key)
            return files

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Database connection lost during get_files_by_sha256: {e}")
            raise ConnectionFailure("Lost connection to database") from e
        except OperationFailure as e:
            logger.error(f"Database operation failed during get_files_by_sha256: {e}")
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

    # Pending user methods

    async def create_pending_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        confirmation_token: str,
        expires_at,
        full_name: Optional[str] = None
    ) -> str:
        """Create a pending user awaiting email confirmation.

        Args:
            username: User's username
            email: User's email
            hashed_password: Hashed password
            confirmation_token: Email confirmation token
            expires_at: Expiration datetime
            full_name: User's full name (optional)

        Returns:
            Inserted pending user document ID

        Raises:
            DuplicateKeyError: If username or email already exists
        """
        if self.pending_users_collection is None:
            raise RuntimeError("Database not connected")

        from datetime import datetime

        pending_user_data = {
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "full_name": full_name,
            "confirmation_token": confirmation_token,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
        }

        try:
            result = await self.pending_users_collection.insert_one(pending_user_data)
            return str(result.inserted_id)
        except DuplicateKeyError as e:
            if "email" in str(e):
                raise DuplicateKeyError("Email already registered (pending or active)")
            elif "confirmation_token" in str(e):
                # This should be extremely rare
                raise DuplicateKeyError("Token collision - please try again")
            raise

    async def get_pending_user_by_token(self, confirmation_token: str) -> Optional[dict]:
        """Get pending user by confirmation token.

        Args:
            confirmation_token: Confirmation token

        Returns:
            Pending user document or None if not found
        """
        if self.pending_users_collection is None:
            raise RuntimeError("Database not connected")

        return await self.pending_users_collection.find_one({"confirmation_token": confirmation_token})

    async def delete_pending_user(self, confirmation_token: str) -> bool:
        """Delete a pending user by confirmation token.

        Args:
            confirmation_token: Confirmation token

        Returns:
            True if deleted, False if not found
        """
        if self.pending_users_collection is None:
            raise RuntimeError("Database not connected")

        result = await self.pending_users_collection.delete_one({"confirmation_token": confirmation_token})
        return result.deleted_count > 0

    async def cleanup_expired_pending_users(self) -> int:
        """Delete all expired pending users.

        Returns:
            Number of deleted pending users
        """
        if self.pending_users_collection is None:
            raise RuntimeError("Database not connected")

        from datetime import datetime

        result = await self.pending_users_collection.delete_many({
            "expires_at": {"$lt": datetime.utcnow()}
        })
        return result.deleted_count


# Global database instance
mongodb = MongoDB()
