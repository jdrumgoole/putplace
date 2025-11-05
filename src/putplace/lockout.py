"""Account lockout mechanism to prevent brute force attacks."""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory storage for failed login attempts
# In production, this should be stored in Redis or the database
_failed_attempts: dict[str, list[datetime]] = {}

# Configuration
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15
ATTEMPT_WINDOW_MINUTES = 15


def record_failed_login(username: str) -> None:
    """Record a failed login attempt for a username.

    Args:
        username: Username that had a failed login attempt
    """
    now = datetime.utcnow()

    if username not in _failed_attempts:
        _failed_attempts[username] = []

    # Add this failed attempt
    _failed_attempts[username].append(now)

    # Clean up old attempts outside the window
    cutoff = now - timedelta(minutes=ATTEMPT_WINDOW_MINUTES)
    _failed_attempts[username] = [
        attempt for attempt in _failed_attempts[username]
        if attempt > cutoff
    ]

    # Log if account is now locked
    if len(_failed_attempts[username]) >= MAX_FAILED_ATTEMPTS:
        logger.warning(
            f"Account locked due to excessive failed login attempts: {username}"
        )


def is_account_locked(username: str) -> bool:
    """Check if an account is currently locked out.

    Args:
        username: Username to check

    Returns:
        True if account is locked, False otherwise
    """
    if username not in _failed_attempts:
        return False

    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=ATTEMPT_WINDOW_MINUTES)

    # Clean up old attempts
    _failed_attempts[username] = [
        attempt for attempt in _failed_attempts[username]
        if attempt > cutoff
    ]

    # Check if locked
    return len(_failed_attempts[username]) >= MAX_FAILED_ATTEMPTS


def get_lockout_time_remaining(username: str) -> Optional[int]:
    """Get the remaining lockout time in seconds.

    Args:
        username: Username to check

    Returns:
        Remaining lockout time in seconds, or None if not locked
    """
    if not is_account_locked(username):
        return None

    if username not in _failed_attempts or not _failed_attempts[username]:
        return None

    # Find the oldest failed attempt in the window
    oldest_attempt = min(_failed_attempts[username])
    lockout_expires = oldest_attempt + timedelta(minutes=LOCKOUT_DURATION_MINUTES)

    now = datetime.utcnow()
    if now >= lockout_expires:
        # Lockout expired, clear attempts
        _failed_attempts[username] = []
        return None

    remaining = (lockout_expires - now).total_seconds()
    return int(remaining)


def clear_failed_attempts(username: str) -> None:
    """Clear failed login attempts for a user after successful login.

    Args:
        username: Username to clear attempts for
    """
    if username in _failed_attempts:
        del _failed_attempts[username]
        logger.debug(f"Cleared failed login attempts for: {username}")


def get_failed_attempt_count(username: str) -> int:
    """Get the number of recent failed attempts for a username.

    Args:
        username: Username to check

    Returns:
        Number of failed attempts in the current window
    """
    if username not in _failed_attempts:
        return 0

    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=ATTEMPT_WINDOW_MINUTES)

    # Count only recent attempts
    recent_attempts = [
        attempt for attempt in _failed_attempts[username]
        if attempt > cutoff
    ]

    return len(recent_attempts)
