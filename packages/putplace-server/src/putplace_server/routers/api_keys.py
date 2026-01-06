"""API key management router for PutPlace API."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import APIKeyAuth
from ..database import MongoDB
from ..dependencies import get_db, get_current_user
from ..models import APIKeyCreate, APIKeyInfo, APIKeyResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api_keys", tags=["auth"])


@router.post(
    "",
    response_model=APIKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    key_data: APIKeyCreate,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> APIKeyResponse:
    """Create a new API key.

    Requires user authentication via JWT Bearer token.
    Include the token in the Authorization header: `Authorization: Bearer <token>`

    Args:
        key_data: API key creation data (name, description)
        db: Database instance (injected)
        current_user: Current logged-in user (injected)

    Returns:
        The new API key and its metadata. SAVE THE API KEY - it won't be shown again!

    Raises:
        HTTPException: If database operation fails or authentication fails
    """
    auth = APIKeyAuth(db)

    try:
        # Create new API key associated with the current user
        new_api_key, key_metadata = await auth.create_api_key(
            name=key_data.name,
            user_id=str(current_user["_id"]),  # Associate with logged-in user
            description=key_data.description,
        )

        # Return the key (only time it's shown)
        return APIKeyResponse(
            api_key=new_api_key,
            **key_metadata,
        )

    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}",
        ) from e


@router.get(
    "",
    response_model=list[APIKeyInfo],
)
async def list_api_keys(
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[APIKeyInfo]:
    """List all API keys for the current user (without showing the actual keys).

    Requires user authentication via JWT Bearer token.

    Args:
        db: Database instance (injected)
        current_user: Current logged-in user (injected)

    Returns:
        List of API key metadata owned by the current user

    Raises:
        HTTPException: If database operation fails or authentication fails
    """
    auth = APIKeyAuth(db)

    try:
        # List only the keys owned by the current user
        keys = await auth.list_api_keys(user_id=str(current_user["_id"]))
        return [APIKeyInfo(**key) for key in keys]

    except Exception as e:
        logger.error(f"Error listing API keys: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list API keys: {str(e)}",
        ) from e


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_api_key(
    key_id: str,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Permanently delete an API key.

    Requires user authentication via JWT Bearer token.

    WARNING: This cannot be undone! Consider using PUT /api_keys/{key_id}/revoke instead.

    Args:
        key_id: API key ID to delete
        db: Database instance (injected)
        current_user: Current logged-in user (injected)

    Returns:
        Success message

    Raises:
        HTTPException: If key not found, database operation fails, or authentication fails
    """
    auth = APIKeyAuth(db)

    try:
        deleted = await auth.delete_api_key(key_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key {key_id} not found",
            )

        return {"message": f"API key {key_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}",
        ) from e


@router.put(
    "/{key_id}/revoke",
    status_code=status.HTTP_200_OK,
)
async def revoke_api_key(
    key_id: str,
    db: MongoDB = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Revoke (deactivate) an API key without deleting it.

    Requires user authentication via JWT Bearer token.

    The key will be marked as inactive and can no longer be used for authentication,
    but its metadata is retained for audit purposes.

    Args:
        key_id: API key ID to revoke
        db: Database instance (injected)
        current_user: Current logged-in user (injected)

    Returns:
        Success message

    Raises:
        HTTPException: If key not found, database operation fails, or authentication fails
    """
    auth = APIKeyAuth(db)

    try:
        revoked = await auth.revoke_api_key(key_id)

        if not revoked:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key {key_id} not found",
            )

        return {"message": f"API key {key_id} revoked successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke API key: {str(e)}",
        ) from e
