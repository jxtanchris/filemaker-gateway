"""Configuration loader: YAML file + environment variable overrides."""

import os
from pathlib import Path

import yaml

from filemaker_gateway.config.schema import (
    AppConfig,
    DatabaseConfig,
    FMDataAPIConfig,
    FMODataConfig,
    GatewayConfig,
    OCROllamaConfig,
    OCRConfig,
    ProviderConfig,
    ToolConfig,
)

ENV_PREFIX = "FILEMAKER_GATEWAY_"


def _env(key: str, default: str | None = None) -> str | None:
    """Read an environment variable with the FILEMAKER_GATEWAY_ prefix."""
    return os.environ.get(f"{ENV_PREFIX}{key}", default)


def load_config(config_path: str | None = None) -> AppConfig:
    """Load configuration from YAML file, overridden by environment variables.

    Resolution order (last wins):
    1. Code defaults (in schema.py)
    2. config.yaml at project root
    3. FILEMAKER_GATEWAY_* environment variables

    Environment variable mapping:
        FILEMAKER_GATEWAY_PROVIDER_NAME → gateway.provider.name
        FILEMAKER_GATEWAY_PROVIDER_API_KEY → gateway.provider.api_key
        FILEMAKER_GATEWAY_PROVIDER_API_BASE → gateway.provider.api_base
        FILEMAKER_GATEWAY_PROVIDER_MODEL → gateway.provider.model
        FILEMAKER_GATEWAY_API_KEY → gateway.api_key
        FILEMAKER_GATEWAY_HOST → gateway.host
        FILEMAKER_GATEWAY_PORT → gateway.port
        FILEMAKER_GATEWAY_LOG_LEVEL → gateway.log_level
        FILEMAKER_GATEWAY_DATABASE_URL → database.url
        FILEMAKER_GATEWAY_SYSTEM_PROMPT → system_prompt
    """
    # Start with defaults
    config = AppConfig()

    # Load YAML if it exists
    if config_path is None:
        config_path = _find_config()

    if config_path and Path(config_path).exists():
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        if "gateway" in raw:
            gw = raw["gateway"]
            config.gateway = GatewayConfig(
                host=gw.get("host", config.gateway.host),
                port=gw.get("port", config.gateway.port),
                api_key=gw.get("api_key", config.gateway.api_key),
                log_level=gw.get("log_level", config.gateway.log_level),
                provider=_parse_provider(gw.get("provider", {})),
                tools=_parse_tools(gw.get("tools", {})),
            )

        if "database" in raw:
            db = raw["database"]
            config.database = DatabaseConfig(
                url=db.get("url", config.database.url),
            )

        if "fm_data_api" in raw:
            fm = raw["fm_data_api"]
            config.fm_data_api = FMDataAPIConfig(
                host=fm.get("host", config.fm_data_api.host),
                database=fm.get("database", config.fm_data_api.database),
                username=fm.get("username", config.fm_data_api.username),
                password=fm.get("password", config.fm_data_api.password),
                protocol=fm.get("protocol", config.fm_data_api.protocol),
                verify_ssl=fm.get("verify_ssl", config.fm_data_api.verify_ssl),
                enabled=fm.get("enabled", config.fm_data_api.enabled),
            )

        if "fm_odata" in raw:
            fo = raw["fm_odata"]
            config.fm_odata = FMODataConfig(
                host=fo.get("host", config.fm_odata.host),
                database=fo.get("database", config.fm_odata.database),
                username=fo.get("username", config.fm_odata.username),
                password=fo.get("password", config.fm_odata.password),
                protocol=fo.get("protocol", config.fm_odata.protocol),
                verify_ssl=fo.get("verify_ssl", config.fm_odata.verify_ssl),
                enabled=fo.get("enabled", config.fm_odata.enabled),
            )

        if "ocr" in raw:
            config.ocr = _parse_ocr(raw["ocr"])

        if "system_prompt" in raw:
            config.system_prompt = raw["system_prompt"]

    # Override with environment variables
    _apply_env_overrides(config)

    return config


def _find_config() -> str | None:
    """Find config.yaml in common locations."""
    candidates = [
        "config.yaml",
        "config.yml",
        os.path.expanduser("~/.filemaker_gateway/config.yaml"),
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return "config.yaml"  # default, may not exist


def _parse_provider(raw: dict) -> ProviderConfig:
    """Parse provider config from YAML dict."""
    return ProviderConfig(
        name=raw.get("name", "deepseek"),
        api_key=raw.get("api_key", ""),
        api_base=raw.get("api_base"),
        model=raw.get("model"),
    )


def _parse_tools(raw: dict) -> ToolConfig:
    """Parse tool config from YAML dict."""
    return ToolConfig(
        filemaker_query=raw.get("filemaker_query", True),
        filemaker_record=raw.get("filemaker_record", True),
        filemaker_script=raw.get("filemaker_script", True),
        filemaker_layout=raw.get("filemaker_layout", True),
        ocr=raw.get("ocr", True),
        sql_query=raw.get("sql_query", True),
    )


def _parse_ocr(raw: dict) -> OCRConfig:
    """Parse OCR config from YAML dict."""
    ollama_raw = raw.get("ollama", {})
    return OCRConfig(
        engine=raw.get("engine", "provider"),
        ollama=OCROllamaConfig(
            base_url=ollama_raw.get("base_url", "http://localhost:11434"),
            model=ollama_raw.get("model", "glm-ocr:latest"),
            timeout=ollama_raw.get("timeout", 120.0),
        ),
    )


def _apply_env_overrides(config: AppConfig) -> None:
    """Apply environment variable overrides to the config."""

    def _set_if_present(env_key: str, obj: object, attr: str, coerce=None) -> None:
        val = _env(env_key)
        if val is not None:
            if coerce:
                val = coerce(val)
            setattr(obj, attr, val)

    # Gateway
    _set_if_present("HOST", config.gateway, "host")
    _set_if_present("PORT", config.gateway, "port", int)
    _set_if_present("API_KEY", config.gateway, "api_key")
    _set_if_present("LOG_LEVEL", config.gateway, "log_level")

    # Provider
    _set_if_present("PROVIDER_NAME", config.gateway.provider, "name")
    _set_if_present("PROVIDER_API_KEY", config.gateway.provider, "api_key")
    _set_if_present("PROVIDER_API_BASE", config.gateway.provider, "api_base")
    _set_if_present("PROVIDER_MODEL", config.gateway.provider, "model")

    # Database
    _set_if_present("DATABASE_URL", config.database, "url")

    # System prompt
    _set_if_present("SYSTEM_PROMPT", config, "system_prompt")

    # FM Data API
    _set_if_present("FM_DATA_API_HOST", config.fm_data_api, "host")
    _set_if_present("FM_DATA_API_DATABASE", config.fm_data_api, "database")
    _set_if_present("FM_DATA_API_USERNAME", config.fm_data_api, "username")
    _set_if_present("FM_DATA_API_PASSWORD", config.fm_data_api, "password")
    _set_if_present("FM_DATA_API_PROTOCOL", config.fm_data_api, "protocol")
    _set_if_present("FM_DATA_API_VERIFY_SSL", config.fm_data_api, "verify_ssl", lambda v: v.lower() == "true")
    _set_if_present("FM_DATA_API_ENABLED", config.fm_data_api, "enabled", lambda v: v.lower() == "true")

    # FM OData
    _set_if_present("FM_ODATA_HOST", config.fm_odata, "host")
    _set_if_present("FM_ODATA_DATABASE", config.fm_odata, "database")
    _set_if_present("FM_ODATA_USERNAME", config.fm_odata, "username")
    _set_if_present("FM_ODATA_PASSWORD", config.fm_odata, "password")
    _set_if_present("FM_ODATA_PROTOCOL", config.fm_odata, "protocol")
    _set_if_present("FM_ODATA_VERIFY_SSL", config.fm_odata, "verify_ssl", lambda v: v.lower() == "true")
    _set_if_present("FM_ODATA_ENABLED", config.fm_odata, "enabled", lambda v: v.lower() == "true")

    # OCR
    _set_if_present("OCR_ENGINE", config.ocr, "engine")
    _set_if_present("OCR_OLLAMA_BASE_URL", config.ocr.ollama, "base_url")
    _set_if_present("OCR_OLLAMA_MODEL", config.ocr.ollama, "model")
    _set_if_present("OCR_OLLAMA_TIMEOUT", config.ocr.ollama, "timeout", float)
