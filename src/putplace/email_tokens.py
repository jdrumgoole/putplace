"""Token generation and validation for email confirmation."""

import secrets
from datetime import datetime, timedelta
from typing import Optional


def generate_confirmation_token() -> str:
    """
    Generate a secure random confirmation token.

    Returns:
        64-character hexadecimal token
    """
    return secrets.token_urlsafe(48)  # 48 bytes = 64 URL-safe characters


def calculate_expiration_time(hours: int = 24) -> datetime:
    """
    Calculate expiration time from now.

    Args:
        hours: Number of hours until expiration (default 24)

    Returns:
        datetime object for expiration
    """
    return datetime.utcnow() + timedelta(hours=hours)


def is_token_expired(expires_at: datetime) -> bool:
    """
    Check if a token has expired.

    Args:
        expires_at: Expiration datetime

    Returns:
        True if expired, False otherwise
    """
    return datetime.utcnow() >= expires_at
