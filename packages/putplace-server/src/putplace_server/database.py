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
    upload_sessions_collection: Optional[AsyncCollection] = None

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
            self.upload_sessions_collection = db["upload_sessions"]

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
            await self.users_collection.create_index("email", unique=True)
            logger.info("Users indexes created successfully")

            # Create indexes for pending_users collection
            await self.pending_users_collection.create_index("confirmation_token", unique=True)
            await self.pending_users_collection.create_index("email", unique=True)
            await self.pending_users_collection.create_index("expires_at")  # For cleanup queries
            logger.info("Pending users indexes created successfully")

            # Create indexes for upload_sessions collection
            await self.upload_sessions_collection.create_index("upload_id", unique=True)
            await self.upload_sessions_collection.create_index("expires_at")  # For cleanup queries
            await self.upload_sessions_collection.create_index("status")
            logger.info("Upload sessions indexes created successfully")

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

    async def create_user(
        self,
        email: str,
        hashed_password: str,
        is_admin: bool = False
    ) -> str:
        """Create a new user.

        Args:
            email: User's email
            hashed_password: Hashed password
            is_admin: Whether the user has admin privileges (default: False)

        Returns:
            Inserted user document ID

        Raises:
            RuntimeError: If database not connected
            DuplicateKeyError: If email already exists
        """
        if self.users_collection is None:
            raise RuntimeError("Database not connected")

        from datetime import datetime

        user_data = {
            "email": email,
            "username": email,  # Use email as username
            "hashed_password": hashed_password,
            "is_active": True,
            "is_admin": is_admin,
            "created_at": datetime.utcnow(),
        }

        try:
            result = await self.users_collection.insert_one(user_data)
            return str(result.inserted_id)
        except DuplicateKeyError as e:
            if "email" in str(e):
                raise DuplicateKeyError("Email already exists")
            raise

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

    # Admin dashboard methods

    async def get_all_users(self) -> list[dict]:
        """Get all registered users.

        Returns:
            List of user documents (without passwords)
        """
        if self.users_collection is None:
            raise RuntimeError("Database not connected")

        users = []
        cursor = self.users_collection.find(
            {},
            {"hashed_password": 0}  # Exclude password hash
        ).sort("created_at", -1)

        async for user in cursor:
            user["_id"] = str(user["_id"])
            users.append(user)

        return users

    async def get_all_pending_users(self) -> list[dict]:
        """Get all pending users awaiting email confirmation.

        Returns:
            List of pending user documents (without passwords)
        """
        if self.pending_users_collection is None:
            raise RuntimeError("Database not connected")

        pending_users = []
        cursor = self.pending_users_collection.find(
            {},
            {"hashed_password": 0}  # Exclude password hash
        ).sort("created_at", -1)

        async for user in cursor:
            user["_id"] = str(user["_id"])
            pending_users.append(user)

        return pending_users

    async def get_user_file_counts(self) -> dict[str, int]:
        """Get file upload counts per user.

        Returns:
            Dictionary mapping user_id to file count
        """
        if self.collection is None:
            raise RuntimeError("Database not connected")

        pipeline = [
            {"$match": {"uploaded_by_user_id": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$uploaded_by_user_id", "count": {"$sum": 1}}}
        ]

        counts = {}
        cursor = await self.collection.aggregate(pipeline)
        async for doc in cursor:
            counts[doc["_id"]] = doc["count"]

        return counts

    async def get_dashboard_stats(self) -> dict:
        """Get statistics for admin dashboard.

        Returns:
            Dictionary with dashboard statistics
        """
        if self.users_collection is None or self.collection is None:
            raise RuntimeError("Database not connected")

        total_users = await self.users_collection.count_documents({})
        active_users = await self.users_collection.count_documents({"is_active": True})
        admin_users = await self.users_collection.count_documents({"is_admin": True})
        total_files = await self.collection.count_documents({})
        files_with_content = await self.collection.count_documents({"has_file_content": True})

        pending_count = 0
        if self.pending_users_collection is not None:
            pending_count = await self.pending_users_collection.count_documents({})

        return {
            "total_users": total_users,
            "active_users": active_users,
            "admin_users": admin_users,
            "pending_users": pending_count,
            "total_files": total_files,
            "files_with_content": files_with_content,
        }

    # Pending user methods

    async def create_pending_user(
        self,
        email: str,
        hashed_password: str,
        confirmation_token: str,
        expires_at
    ) -> str:
        """Create a pending user awaiting email confirmation.

        Args:
            email: User's email
            hashed_password: Hashed password
            confirmation_token: Email confirmation token
            expires_at: Expiration datetime

        Returns:
            Inserted pending user document ID

        Raises:
            DuplicateKeyError: If email already exists
        """
        if self.pending_users_collection is None:
            raise RuntimeError("Database not connected")

        from datetime import datetime

        pending_user_data = {
            "email": email,
            "hashed_password": hashed_password,
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

    # Chunked upload session methods

    async def create_upload_session(
        self,
        upload_id: str,
        filepath: str,
        hostname: str,
        sha256: str,
        file_size: int,
        chunk_size: int,
        total_chunks: int,
        storage_backend: str,
        user_id: str
    ) -> str:
        """Create a new upload session for chunked uploads.

        Args:
            upload_id: Unique upload identifier (UUID)
            filepath: Full path to the file
            hostname: Hostname where file is located
            sha256: SHA256 hash of the complete file
            file_size: Total file size in bytes
            chunk_size: Size of each chunk in bytes
            total_chunks: Total number of chunks
            storage_backend: Storage backend type ('local' or 's3')
            user_id: User ID who initiated the upload

        Returns:
            Inserted upload session document ID

        Raises:
            RuntimeError: If database not connected
            DuplicateKeyError: If upload_id already exists
        """
        if self.upload_sessions_collection is None:
            raise RuntimeError("Database not connected")

        from datetime import datetime, timedelta

        session_data = {
            "upload_id": upload_id,
            "filepath": filepath,
            "hostname": hostname,
            "sha256": sha256,
            "file_size": file_size,
            "chunk_size": chunk_size,
            "total_chunks": total_chunks,
            "uploaded_chunks": [],
            "status": "initiated",  # initiated, uploading, completed, aborted, expired
            "storage_backend": storage_backend,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=1),
            "completed_at": None,
        }

        try:
            result = await self.upload_sessions_collection.insert_one(session_data)
            return str(result.inserted_id)
        except DuplicateKeyError as e:
            if "upload_id" in str(e):
                raise DuplicateKeyError("Upload ID already exists")
            raise

    async def get_upload_session(self, upload_id: str) -> Optional[dict]:
        """Get upload session by upload_id.

        Args:
            upload_id: Upload identifier

        Returns:
            Upload session document or None if not found
        """
        if self.upload_sessions_collection is None:
            raise RuntimeError("Database not connected")

        return await self.upload_sessions_collection.find_one({"upload_id": upload_id})

    async def add_uploaded_chunk(
        self,
        upload_id: str,
        chunk_num: int,
        etag: str
    ) -> bool:
        """Add an uploaded chunk to the session.

        Args:
            upload_id: Upload identifier
            chunk_num: Chunk number (0-indexed)
            etag: Chunk hash/ETag

        Returns:
            True if updated successfully, False if not found
        """
        if self.upload_sessions_collection is None:
            raise RuntimeError("Database not connected")

        from datetime import datetime

        result = await self.upload_sessions_collection.update_one(
            {"upload_id": upload_id},
            {
                "$push": {
                    "uploaded_chunks": {
                        "chunk_num": chunk_num,
                        "etag": etag,
                        "uploaded_at": datetime.utcnow(),
                    }
                },
                "$set": {
                    "status": "uploading",
                }
            }
        )
        return result.modified_count > 0

    async def complete_upload_session(self, upload_id: str) -> bool:
        """Mark upload session as completed.

        Args:
            upload_id: Upload identifier

        Returns:
            True if updated successfully, False if not found
        """
        if self.upload_sessions_collection is None:
            raise RuntimeError("Database not connected")

        from datetime import datetime

        result = await self.upload_sessions_collection.update_one(
            {"upload_id": upload_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                }
            }
        )
        return result.modified_count > 0

    async def abort_upload_session(self, upload_id: str) -> bool:
        """Mark upload session as aborted.

        Args:
            upload_id: Upload identifier

        Returns:
            True if updated successfully, False if not found
        """
        if self.upload_sessions_collection is None:
            raise RuntimeError("Database not connected")

        result = await self.upload_sessions_collection.update_one(
            {"upload_id": upload_id},
            {
                "$set": {
                    "status": "aborted",
                }
            }
        )
        return result.modified_count > 0

    async def delete_upload_session(self, upload_id: str) -> bool:
        """Delete an upload session.

        Args:
            upload_id: Upload identifier

        Returns:
            True if deleted, False if not found
        """
        if self.upload_sessions_collection is None:
            raise RuntimeError("Database not connected")

        result = await self.upload_sessions_collection.delete_one({"upload_id": upload_id})
        return result.deleted_count > 0

    async def cleanup_expired_upload_sessions(self) -> int:
        """Delete all expired upload sessions.

        Returns:
            Number of deleted sessions
        """
        if self.upload_sessions_collection is None:
            raise RuntimeError("Database not connected")

        from datetime import datetime

        result = await self.upload_sessions_collection.delete_many({
            "expires_at": {"$lt": datetime.utcnow()},
            "status": {"$ne": "completed"}
        })
        return result.deleted_count

    # File deletion methods

    async def mark_file_deleted(
        self,
        sha256: str,
        hostname: str,
        filepath: str,
        deleted_at
    ) -> bool:
        """Mark a file as deleted (soft delete).

        Args:
            sha256: SHA256 hash of the file
            hostname: Hostname where file was located
            filepath: Full path to the file
            deleted_at: Deletion timestamp

        Returns:
            True if updated successfully, False if not found
        """
        if self.collection is None:
            raise RuntimeError("Database not connected")

        result = await self.collection.update_one(
            {"sha256": sha256, "hostname": hostname, "filepath": filepath},
            {
                "$set": {
                    "status": "deleted",
                    "deleted_at": deleted_at,
                }
            }
        )
        return result.modified_count > 0


# Global database instance
mongodb = MongoDB()
