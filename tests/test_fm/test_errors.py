import pytest
from filemaker_gateway.fm.errors import FMAuthError, FMDataError, FMNotFoundError, FMValidationError


def test_fm_data_error_base():
    """FMDataError should carry code and message."""
    err = FMDataError(500, "Internal Server Error")
    assert err.code == 500
    assert err.message == "Internal Server Error"
    assert str(err) == "[FMDataError 500] Internal Server Error"


def test_fm_auth_error():
    """FMAuthError should default to code 401."""
    err = FMAuthError("Invalid credentials")
    assert err.code == 401
    assert "Invalid credentials" in str(err)


def test_fm_not_found_error():
    """FMNotFoundError should default to code 404."""
    err = FMNotFoundError("Record not found")
    assert err.code == 404


def test_fm_validation_error():
    """FMValidationError should default to code 400."""
    err = FMValidationError("Field 'name' is required")
    assert err.code == 400


def test_fm_data_error_with_custom_code():
    """Should accept custom error codes."""
    err = FMDataError(999, "Custom error")
    assert err.code == 999
