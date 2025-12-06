"""User authentication router for PutPlace API."""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import settings
from ..database import MongoDB
from ..models import GoogleOAuthLogin, Token, UserCreate, UserLogin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["users"])


# These will be injected by main.py
def get_db() -> MongoDB:
    """Get database instance - injected by main.py."""
    raise NotImplementedError("get_db must be overridden")


@router.post("/register")
async def register_user(user_data: UserCreate, db: MongoDB = Depends(get_db)) -> dict:
    """Register a new user (creates pending user and sends confirmation email).

    User must confirm their email within 24 hours to activate the account.
    """
    from pymongo.errors import DuplicateKeyError

    from ..email_service import get_email_service
    from ..email_tokens import calculate_expiration_time, generate_confirmation_token
    from ..user_auth import get_password_hash

    # Check if registration is enabled
    if not settings.registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled. Please contact the administrator.",
        )

    try:
        # Check if user already exists (active)
        existing_user = await db.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
            )

        # Hash the password
        hashed_password = get_password_hash(user_data.password)

        # Generate confirmation token
        confirmation_token = generate_confirmation_token()
        expires_at = calculate_expiration_time(hours=24)

        # Create pending user in database
        await db.create_pending_user(
            email=user_data.email,
            hashed_password=hashed_password,
            confirmation_token=confirmation_token,
            expires_at=expires_at,
            full_name=user_data.full_name,
        )

        # Send confirmation email
        email_service = get_email_service()
        email_sent = email_service.send_confirmation_email(
            recipient_email=user_data.email, confirmation_token=confirmation_token
        )

        if not email_sent:
            # If email fails, delete pending user
            await db.delete_pending_user(confirmation_token)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send confirmation email. Please try again later.",
            )

        return {
            "message": "Registration successful! Please check your email to confirm your account.",
            "detail": "You must confirm your email address before you can log in. Check your inbox for a confirmation link.",
            "email": user_data.email,
            "expires_in_hours": 24,
            "next_step": "Check your email and click the confirmation link to activate your account",
        }

    except DuplicateKeyError as e:
        if "email" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered (pending or active)",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=Token)
async def login_user(user_login: UserLogin, db: MongoDB = Depends(get_db)) -> Token:
    """Login and get access token."""
    from ..user_auth import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, verify_password

    # Get user from database by email
    user = await db.get_user_by_email(user_login.email)

    if not user or not verify_password(user_login.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account"
        )

    # Create access token with email as subject
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )

    return Token(access_token=access_token)


@router.get("/check-confirmation-status")
async def check_confirmation_status(email: str, db: MongoDB = Depends(get_db)) -> dict:
    """Check if a user's email has been confirmed.

    This endpoint is used by the awaiting-confirmation page to poll for confirmation status.

    Args:
        email: The email address to check

    Returns:
        Dictionary with confirmation status
    """
    # Check if user exists in the users collection (confirmed)
    user = await db.get_user_by_email(email)
    if user:
        return {"confirmed": True, "message": "Email confirmed! You can now log in."}

    # Check if user exists in pending_users collection (still waiting)
    if db.pending_users_collection is not None:
        pending = await db.pending_users_collection.find_one({"email": email})
        if pending:
            return {
                "confirmed": False,
                "message": "Awaiting email confirmation. Please check your inbox.",
            }

    # Email not found in either collection
    return {
        "confirmed": False,
        "message": "Email not found. Please register first.",
        "not_found": True,
    }


@router.get("/oauth/config")
async def get_oauth_config() -> dict:
    """Get OAuth configuration for client-side authentication."""
    return {
        "google_client_id": settings.google_client_id if settings.google_client_id else None,
        "google_enabled": bool(settings.google_client_id),
    }


@router.post("/auth/google", response_model=Token)
async def google_oauth_login(
    oauth_data: GoogleOAuthLogin,
    db: MongoDB = Depends(get_db),
) -> Token:
    """Authenticate using Google OAuth2.

    This endpoint verifies a Google ID token and creates/logs in the user.
    """
    from ..user_auth import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token

    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google OAuth is not configured",
        )

    try:
        # Import Google auth library
        from google.oauth2 import id_token
        from google.auth.transport import requests

        # Verify the Google ID token
        idinfo = id_token.verify_oauth2_token(
            oauth_data.credential,
            requests.Request(),
            settings.google_client_id,
        )

        # Get user info from token
        email = idinfo.get("email")
        name = idinfo.get("name", "")
        google_id = idinfo.get("sub")

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not get email from Google token",
            )

        # Check if user exists
        user = await db.get_user_by_email(email)

        if not user:
            # Create new user from Google OAuth
            user_id = await db.create_user(
                email=email,
                hashed_password="",  # No password for OAuth users
                full_name=name,
                google_id=google_id,
            )
            user = await db.get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create or find user",
            )

        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["email"]}, expires_delta=access_token_expires
        )

        return Token(access_token=access_token)

    except ValueError as e:
        logger.error(f"Google OAuth token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )
    except Exception as e:
        logger.error(f"Google OAuth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Google OAuth failed: {str(e)}",
        )
