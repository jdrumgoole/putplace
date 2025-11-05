"""Tests for account lockout mechanism."""

import pytest
from datetime import datetime, timedelta

from putplace.lockout import (
    record_failed_login,
    is_account_locked,
    get_lockout_time_remaining,
    clear_failed_attempts,
    get_failed_attempt_count,
    _failed_attempts,
    MAX_FAILED_ATTEMPTS,
    LOCKOUT_DURATION_MINUTES,
    ATTEMPT_WINDOW_MINUTES,
)


@pytest.fixture(autouse=True)
def clear_lockout_data():
    """Clear lockout data before and after each test."""
    _failed_attempts.clear()
    yield
    _failed_attempts.clear()


def test_record_failed_login():
    """Test recording a failed login attempt."""
    username = "testuser"

    # Record first attempt
    record_failed_login(username)
    assert get_failed_attempt_count(username) == 1

    # Record second attempt
    record_failed_login(username)
    assert get_failed_attempt_count(username) == 2


def test_account_not_locked_initially():
    """Test that accounts are not locked by default."""
    username = "testuser"
    assert not is_account_locked(username)
    assert get_lockout_time_remaining(username) is None


def test_account_locks_after_max_attempts():
    """Test that account locks after MAX_FAILED_ATTEMPTS."""
    username = "testuser"

    # Make MAX_FAILED_ATTEMPTS - 1 attempts
    for _ in range(MAX_FAILED_ATTEMPTS - 1):
        record_failed_login(username)

    # Should not be locked yet
    assert not is_account_locked(username)

    # One more attempt should lock the account
    record_failed_login(username)
    assert is_account_locked(username)


def test_lockout_time_remaining():
    """Test that lockout time remaining is calculated correctly."""
    username = "testuser"

    # Lock the account
    for _ in range(MAX_FAILED_ATTEMPTS):
        record_failed_login(username)

    assert is_account_locked(username)

    # Get remaining time
    remaining = get_lockout_time_remaining(username)
    assert remaining is not None
    assert 0 < remaining <= LOCKOUT_DURATION_MINUTES * 60  # Should be in seconds


def test_clear_failed_attempts():
    """Test clearing failed login attempts."""
    username = "testuser"

    # Record some attempts
    for _ in range(3):
        record_failed_login(username)

    assert get_failed_attempt_count(username) == 3

    # Clear attempts
    clear_failed_attempts(username)
    assert get_failed_attempt_count(username) == 0
    assert not is_account_locked(username)


def test_old_attempts_cleaned_up():
    """Test that old attempts outside the window are cleaned up."""
    username = "testuser"

    # Manually add an old attempt
    old_time = datetime.utcnow() - timedelta(minutes=ATTEMPT_WINDOW_MINUTES + 5)
    _failed_attempts[username] = [old_time]

    # Record a new attempt (should trigger cleanup)
    record_failed_login(username)

    # Should only have 1 attempt (the new one)
    assert get_failed_attempt_count(username) == 1


def test_multiple_users_isolated():
    """Test that lockout tracking is isolated per user."""
    user1 = "user1"
    user2 = "user2"

    # Lock user1
    for _ in range(MAX_FAILED_ATTEMPTS):
        record_failed_login(user1)

    # user1 should be locked, user2 should not
    assert is_account_locked(user1)
    assert not is_account_locked(user2)

    # user2 should have no failed attempts
    assert get_failed_attempt_count(user2) == 0


def test_lockout_expires_after_duration():
    """Test that lockout expires after the duration."""
    username = "testuser"

    # Manually create old failed attempts that should have expired
    expired_time = datetime.utcnow() - timedelta(minutes=LOCKOUT_DURATION_MINUTES + 1)
    _failed_attempts[username] = [expired_time for _ in range(MAX_FAILED_ATTEMPTS)]

    # Check if account is locked (should clean up expired attempts)
    assert not is_account_locked(username)
    assert get_lockout_time_remaining(username) is None


def test_partial_attempts_dont_lock():
    """Test that fewer than max attempts don't lock the account."""
    username = "testuser"

    # Make fewer than MAX_FAILED_ATTEMPTS
    for _ in range(MAX_FAILED_ATTEMPTS - 2):
        record_failed_login(username)

    # Should not be locked
    assert not is_account_locked(username)
    assert get_failed_attempt_count(username) == MAX_FAILED_ATTEMPTS - 2


def test_get_failed_attempt_count_nonexistent_user():
    """Test getting attempt count for user with no attempts."""
    username = "nonexistent"
    assert get_failed_attempt_count(username) == 0


def test_clear_attempts_for_nonexistent_user():
    """Test clearing attempts for user with no recorded attempts."""
    username = "nonexistent"
    # Should not raise an error
    clear_failed_attempts(username)
    assert get_failed_attempt_count(username) == 0


def test_lockout_with_attempts_spanning_window():
    """Test lockout with attempts spread across the time window."""
    username = "testuser"

    # Add some old attempts (but within window)
    recent_time = datetime.utcnow() - timedelta(minutes=ATTEMPT_WINDOW_MINUTES - 1)
    _failed_attempts[username] = [recent_time for _ in range(2)]

    # Add more attempts to reach the limit
    for _ in range(MAX_FAILED_ATTEMPTS - 2):
        record_failed_login(username)

    # Should be locked
    assert is_account_locked(username)
    assert get_failed_attempt_count(username) == MAX_FAILED_ATTEMPTS
