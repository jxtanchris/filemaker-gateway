"""API key authentication utilities.

The primary authentication happens in middleware.py (AuthMiddleware).
This module provides helper functions for key validation and generation.
"""

import secrets


def generate_api_key() -> str:
    """Generate a cryptographically random API key.

    Returns a 32-byte hex string (64 characters).
    """
    return secrets.token_hex(32)


def validate_api_key(provided: str, expected: str) -> bool:
    """Constant-time comparison of API keys.

    Uses secrets.compare_digest to prevent timing attacks.
    """
    if not expected or not provided:
        return False
    return secrets.compare_digest(provided, expected)
