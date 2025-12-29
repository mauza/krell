"""Authentication helpers for admin dashboard."""

import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional

# Session duration: 7 days
SESSION_DURATION_DAYS = 7


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_hex(32)


def get_session_expiry() -> datetime:
    """Get expiry datetime for a new session (7 days from now)."""
    return datetime.utcnow() + timedelta(days=SESSION_DURATION_DAYS)


def is_session_expired(expiry_iso: Optional[str]) -> bool:
    """Check if a session has expired."""
    if expiry_iso is None:
        return True
    try:
        expiry = datetime.fromisoformat(expiry_iso)
        return datetime.utcnow() > expiry
    except ValueError:
        return True
