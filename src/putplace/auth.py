"""Authentication and authorization for PutPlace API."""

import hashlib
import secrets
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pymongo.asynchronous.collection import AsyncCollection

from . import database

if TYPE_CHECKING:
    from .database import MongoDB

# API key header name
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_auth_db() -> "MongoDB":
    """Get database instance for authentication.

    This function is used as a dependency in FastAPI routes.
    Returns the global database.mongodb instance.
    """
    return database.mongodb


def generate_api_key() -> str:
    """Generate a new API key.

    Returns:
        A cryptographically secure random API key (hex string, 64 characters)
    """
    return secrets.token_hex(32)  # 32 bytes = 64 hex characters


def hash_api_key(api_key: str) -> str:
    """Hash an API key for secure storage.

    Args:
        api_key: The API key to hash

    Returns:
        SHA256 hash of the API key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


class APIKeyAuth:
    """API Key authentication manager."""

    def __init__(self, db: database.MongoDB):
        """Initialize API key authentication.

        Args:
            db: MongoDB database instance
        """
        self.db = db

    async def get_api_keys_collection(self) -> AsyncCollection:
        """Get the API keys collection.

        Returns:
            MongoDB collection for API keys
        """
        if self.db.client is None:
            raise RuntimeError("Database not connected")

        db = self.db.client[self.db.collection.database.name]
        return db["api_keys"]

    async def create_api_key(
        self,
        name: str,
        user_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> tuple[str, dict]:
        """Create a new API key.

        Args:
            name: Name/identifier for this API key
            user_id: Optional user ID who owns this key
            description: Optional description

        Returns:
            Tuple of (api_key, key_metadata)
            The api_key is returned only once and should be given to the user.
            The key_metadata contains the stored information (without the actual key).

        Raises:
            RuntimeError: If database not connected
        """
        collection = await self.get_api_keys_collection()

        # Generate new API key
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)

        # Create metadata document
        key_doc = {
            "key_hash": key_hash,
            "name": name,
            "description": description,
            "user_id": user_id,  # Associate with user
            "created_at": datetime.utcnow(),
            "last_used_at": None,
            "is_active": True,
        }

        # Insert into database
        result = await collection.insert_one(key_doc.copy())

        # Return the plain API key (only time we show it) and metadata
        key_doc["_id"] = str(result.inserted_id)
        key_doc.pop("key_hash")  # Don't include hash in response

        return api_key, key_doc

    async def verify_api_key(self, api_key: str) -> Optional[dict]:
        """Verify an API key and return its metadata.

        Args:
            api_key: The API key to verify

        Returns:
            Key metadata if valid and active, None otherwise
        """
        collection = await self.get_api_keys_collection()

        # Hash the provided key
        key_hash = hash_api_key(api_key)

        # Look up in database
        key_doc = await collection.find_one({
            "key_hash": key_hash,
            "is_active": True,
        })

        if key_doc:
            # Update last used timestamp
            await collection.update_one(
                {"_id": key_doc["_id"]},
                {"$set": {"last_used_at": datetime.utcnow()}}
            )

            # Return metadata (without hash)
            key_doc.pop("key_hash", None)
            key_doc["_id"] = str(key_doc["_id"])
            return key_doc

        return None

    async def revoke_api_key(self, key_id: str) -> bool:
        """Revoke (deactivate) an API key.

        Args:
            key_id: MongoDB ObjectId of the key to revoke

        Returns:
            True if key was revoked, False if not found
        """
        from bson import ObjectId

        collection = await self.get_api_keys_collection()

        result = await collection.update_one(
            {"_id": ObjectId(key_id)},
            {"$set": {"is_active": False}}
        )

        return result.modified_count > 0

    async def list_api_keys(self, user_id: Optional[str] = None) -> list[dict]:
        """List all API keys (without showing actual keys).

        Args:
            user_id: Optional user ID to filter keys by owner

        Returns:
            List of API key metadata
        """
        collection = await self.get_api_keys_collection()

        # Build query filter
        query = {}
        if user_id:
            query["user_id"] = user_id

        cursor = collection.find(query, {"key_hash": 0})
        keys = []

        async for key_doc in cursor:
            key_doc["_id"] = str(key_doc["_id"])
            keys.append(key_doc)

        return keys

    async def delete_api_key(self, key_id: str) -> bool:
        """Permanently delete an API key.

        Args:
            key_id: MongoDB ObjectId of the key to delete

        Returns:
            True if key was deleted, False if not found
        """
        from bson import ObjectId

        collection = await self.get_api_keys_collection()

        result = await collection.delete_one({"_id": ObjectId(key_id)})

        return result.deleted_count > 0


# Dependency for protected endpoints
async def get_current_api_key(
    api_key: str = Security(API_KEY_HEADER),
    db: "MongoDB" = Depends(get_auth_db),
) -> dict:
    """FastAPI dependency to validate API key.

    Args:
        api_key: API key from request header
        db: Database instance (injected)

    Returns:
        API key metadata if valid

    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Include X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Get API key authenticator
    auth = APIKeyAuth(db)

    # Verify the key
    key_metadata = await auth.verify_api_key(api_key)

    if not key_metadata:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return key_metadata


# Optional dependency - allows unauthenticated access
async def get_optional_api_key(
    api_key: str = Security(API_KEY_HEADER),
    db: "MongoDB" = Depends(get_auth_db),
) -> Optional[dict]:
    """FastAPI dependency for optional API key authentication.

    Returns API key metadata if provided and valid, None otherwise.
    Does not raise an error if no key is provided.

    Args:
        api_key: API key from request header
        db: Database instance (injected)

    Returns:
        API key metadata if valid, None if not provided or invalid
    """
    if not api_key:
        return None

    auth = APIKeyAuth(db)
    return await auth.verify_api_key(api_key)
