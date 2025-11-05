"""Tests for password strength validation."""

import pytest
from pydantic import ValidationError

from putplace.models import UserCreate


def test_password_too_short():
    """Test that passwords shorter than 12 characters are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="testuser",
            email="test@example.com",
            password="Short1!"
        )

    assert "at least 12 characters" in str(exc_info.value)


def test_password_no_uppercase():
    """Test that passwords without uppercase letters are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="testuser",
            email="test@example.com",
            password="lowercase123!"
        )

    assert "uppercase letter" in str(exc_info.value)


def test_password_no_lowercase():
    """Test that passwords without lowercase letters are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="testuser",
            email="test@example.com",
            password="UPPERCASE123!"
        )

    assert "lowercase letter" in str(exc_info.value)


def test_password_no_digit():
    """Test that passwords without digits are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="testuser",
            email="test@example.com",
            password="NoDigitsHere!"
        )

    assert "digit" in str(exc_info.value)


def test_password_no_special_char():
    """Test that passwords without special characters are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="testuser",
            email="test@example.com",
            password="NoSpecial123"
        )

    assert "special character" in str(exc_info.value)


def test_password_valid_strong():
    """Test that a strong password is accepted."""
    user = UserCreate(
        username="testuser",
        email="test@example.com",
        password="StrongPass123!"
    )

    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.password == "StrongPass123!"


def test_password_valid_with_various_special_chars():
    """Test passwords with different special characters."""
    special_chars = r"!@#$%^&*(),.?\":{}|<>_-+=[]\/;'`~"

    for char in special_chars:
        user = UserCreate(
            username="testuser",
            email="test@example.com",
            password=f"ValidPass123{char}"
        )
        assert user.password == f"ValidPass123{char}"


def test_password_exactly_12_chars():
    """Test that exactly 12 character password is accepted."""
    user = UserCreate(
        username="testuser",
        email="test@example.com",
        password="ValidPass12!"  # Exactly 12 characters
    )

    assert len(user.password) == 12


def test_password_very_long():
    """Test that very long passwords are accepted."""
    long_password = "VeryLongPassword123!WithManyCharacters" * 3

    user = UserCreate(
        username="testuser",
        email="test@example.com",
        password=long_password
    )

    assert user.password == long_password


def test_password_max_length():
    """Test that password respects max length of 128."""
    # Create password longer than 128 characters
    too_long_password = "A" * 129 + "a1!"

    with pytest.raises(ValidationError):
        UserCreate(
            username="testuser",
            email="test@example.com",
            password=too_long_password
        )


def test_password_edge_case_all_requirements():
    """Test password with minimum of each requirement."""
    user = UserCreate(
        username="testuser",
        email="test@example.com",
        password="Aa1!xxxxxxxx"  # One upper, one lower, one digit, one special, rest filler
    )

    assert user.password == "Aa1!xxxxxxxx"


def test_multiple_validation_errors():
    """Test that multiple validation errors are reported."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            username="testuser",
            email="test@example.com",
            password="short"  # Too short, no uppercase, no digit, no special
        )

    # Should have at least the first error
    errors = str(exc_info.value)
    assert "12 characters" in errors


def test_username_and_email_validation_still_works():
    """Test that other validations still work with password validation."""
    # Username too short
    with pytest.raises(ValidationError):
        UserCreate(
            username="ab",  # Min length is 3
            email="test@example.com",
            password="ValidPass123!"
        )

    # Valid user
    user = UserCreate(
        username="validuser",
        email="test@example.com",
        password="ValidPass123!"
    )
    assert user.username == "validuser"
