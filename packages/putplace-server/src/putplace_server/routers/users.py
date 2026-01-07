"""User authentication router for PutPlace API."""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from ..config import settings
from ..database import MongoDB
from ..dependencies import get_db
from ..models import GoogleOAuthLogin, Token, UserCreate, UserLogin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["users"])


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


@router.get("/confirm-email", response_class=HTMLResponse)
async def confirm_email(token: str, db: MongoDB = Depends(get_db)):
    """
    Confirm user email and activate account.

    Args:
        token: Email confirmation token from the confirmation link

    Returns:
        HTML page with confirmation result
    """
    from ..email_tokens import is_token_expired

    def render_confirmation_page(success: bool, title: str, message: str):
        """Render a styled confirmation result page."""
        icon = "✓" if success else "✗"
        icon_color = "#28a745" if success else "#dc3545"
        button_text = "Login to Your Account" if success else "Register Again"
        button_link = "/login" if success else "/register"

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title} - PutPlace</title>
            <link rel="icon" type="image/svg+xml" href="/static/images/favicon.svg">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    max-width: 500px;
                    width: 100%;
                    background: white;
                    border-radius: 10px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    overflow: hidden;
                    text-align: center;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                }}
                .header h1 {{
                    font-size: 1.8em;
                    margin-bottom: 5px;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .icon {{
                    font-size: 4em;
                    color: {icon_color};
                    margin-bottom: 20px;
                }}
                .message {{
                    font-size: 1.1em;
                    color: #555;
                    margin-bottom: 30px;
                }}
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-weight: bold;
                    transition: transform 0.2s, box-shadow 0.2s;
                }}
                .button:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                }}
                .footer {{
                    padding: 20px;
                    background: #f8f9fa;
                    font-size: 0.9em;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>PutPlace</h1>
                </div>
                <div class="content">
                    <div class="icon">{icon}</div>
                    <h2 style="margin-bottom: 15px;">{title}</h2>
                    <p class="message">{message}</p>
                    <a href="{button_link}" class="button">{button_text}</a>
                </div>
                <div class="footer">
                    <p>Need help? Contact support@putplace.org</p>
                </div>
            </div>
        </body>
        </html>
        """

    # Get pending user by token
    pending_user = await db.get_pending_user_by_token(token)

    if not pending_user:
        return HTMLResponse(
            content=render_confirmation_page(
                success=False,
                title="Invalid Link",
                message="This confirmation link is invalid or has already been used. If you haven't confirmed your account yet, please register again."
            ),
            status_code=404
        )

    # Check if token is expired
    if is_token_expired(pending_user["expires_at"]):
        # Delete expired pending user
        await db.delete_pending_user(token)
        return HTMLResponse(
            content=render_confirmation_page(
                success=False,
                title="Link Expired",
                message="This confirmation link has expired. Confirmation links are valid for 24 hours. Please register again to receive a new confirmation email."
            ),
            status_code=400
        )

    # Create actual user account
    from pymongo.errors import DuplicateKeyError

    try:
        user_id = await db.create_user(
            email=pending_user["email"],
            hashed_password=pending_user["hashed_password"]
        )

        # Delete pending user after successful creation
        await db.delete_pending_user(token)

        return HTMLResponse(
            content=render_confirmation_page(
                success=True,
                title="Email Confirmed!",
                message=f"Welcome! Your email has been confirmed and your account is now active. You can now log in to start using PutPlace."
            )
        )

    except DuplicateKeyError:
        # User already exists - this can happen if the link was clicked twice
        # or if they registered again. Delete pending user and let them log in.
        await db.delete_pending_user(token)
        return HTMLResponse(
            content=render_confirmation_page(
                success=True,
                title="Account Already Active",
                message="Your account is already active! You can log in using your email and password."
            )
        )

    except Exception as e:
        # Log error and return generic message
        logger.error(f"Error creating user from pending: {e}")
        return HTMLResponse(
            content=render_confirmation_page(
                success=False,
                title="Activation Failed",
                message="We encountered an error while activating your account. Please try again or contact support if the problem persists."
            ),
            status_code=500
        )


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
