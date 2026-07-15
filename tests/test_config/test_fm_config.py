import os
from filemaker_gateway.config.loader import load_config
from filemaker_gateway.config.schema import FMDataAPIConfig


def test_default_fm_config_disabled():
    """Default config should have fm_data_api disabled with empty values."""
    config = load_config("nonexistent.yaml")
    assert config.fm_data_api.enabled is False
    assert config.fm_data_api.host == ""


def test_env_var_overrides_fm_config():
    """Environment variables should override FM config fields."""
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_HOST"] = "fm.example.com"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_DATABASE"] = "TestDB"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_USERNAME"] = "admin"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_PASSWORD"] = "secret"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_PROTOCOL"] = "http"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_ENABLED"] = "true"

    try:
        config = load_config("nonexistent.yaml")
        assert config.fm_data_api.host == "fm.example.com"
        assert config.fm_data_api.database == "TestDB"
        assert config.fm_data_api.username == "admin"
        assert config.fm_data_api.password == "secret"
        assert config.fm_data_api.protocol == "http"
        assert config.fm_data_api.enabled is True
    finally:
        # Clean up
        for key in list(os.environ):
            if key.startswith("FILEMAKER_GATEWAY_FM_DATA_API_"):
                del os.environ[key]
