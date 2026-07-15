"""Tests for fm_odata configuration loading and env var overrides."""

import os

from filemaker_gateway.config.loader import load_config


def test_default_odata_config_disabled():
    config = load_config("nonexistent.yaml")
    assert config.fm_odata.enabled is False
    assert config.fm_odata.host == ""
    assert config.fm_odata.database == ""
    assert config.fm_odata.protocol == "https"
    assert config.fm_odata.verify_ssl is True


def test_odata_env_var_overrides():
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_HOST"] = "fm.example.com"
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_DATABASE"] = "TestDB"
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_USERNAME"] = "admin"
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_PASSWORD"] = "secret"
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_ENABLED"] = "true"

    try:
        config = load_config("nonexistent.yaml")
        assert config.fm_odata.host == "fm.example.com"
        assert config.fm_odata.database == "TestDB"
        assert config.fm_odata.username == "admin"
        assert config.fm_odata.password == "secret"
        assert config.fm_odata.enabled is True
    finally:
        for key in list(os.environ):
            if key.startswith("FILEMAKER_GATEWAY_FM_ODATA_"):
                del os.environ[key]
