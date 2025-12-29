"""Tests for authentication helpers."""

import pytest
from datetime import datetime, timedelta


def test_hash_password_returns_bytes():
    """hash_password should return a bcrypt hash."""
    from auth import hash_password

    result = hash_password("mysecretpassword")

    assert isinstance(result, str)
    assert result.startswith("$2b$")


def test_verify_password_correct():
    """verify_password should return True for correct password."""
    from auth import hash_password, verify_password

    hashed = hash_password("mysecretpassword")

    assert verify_password("mysecretpassword", hashed) is True


def test_verify_password_incorrect():
    """verify_password should return False for wrong password."""
    from auth import hash_password, verify_password

    hashed = hash_password("mysecretpassword")

    assert verify_password("wrongpassword", hashed) is False


def test_generate_session_token_length():
    """generate_session_token should return 64-char hex string."""
    from auth import generate_session_token

    token = generate_session_token()

    assert isinstance(token, str)
    assert len(token) == 64  # 32 bytes = 64 hex chars


def test_generate_session_token_unique():
    """generate_session_token should return unique tokens."""
    from auth import generate_session_token

    tokens = [generate_session_token() for _ in range(10)]

    assert len(set(tokens)) == 10


def test_get_session_expiry():
    """get_session_expiry should return datetime 7 days from now."""
    from auth import get_session_expiry

    before = datetime.utcnow()
    expiry = get_session_expiry()
    after = datetime.utcnow()

    # Should be ~7 days in future
    assert expiry > before + timedelta(days=6, hours=23)
    assert expiry < after + timedelta(days=7, hours=1)


def test_is_session_expired_false_for_future():
    """is_session_expired should return False for future timestamp."""
    from auth import is_session_expired

    future = (datetime.utcnow() + timedelta(days=1)).isoformat()

    assert is_session_expired(future) is False


def test_is_session_expired_true_for_past():
    """is_session_expired should return True for past timestamp."""
    from auth import is_session_expired

    past = (datetime.utcnow() - timedelta(days=1)).isoformat()

    assert is_session_expired(past) is True


def test_is_session_expired_true_for_none():
    """is_session_expired should return True for None."""
    from auth import is_session_expired

    assert is_session_expired(None) is True
