"""Pydantic configuration models."""

from pydantic import BaseModel

from filemaker_gateway.config.defaults import (
    DEFAULT_DATABASE_URL,
    DEFAULT_FM_DATABASE,
    DEFAULT_FM_ENABLED,
    DEFAULT_FM_HOST,
    DEFAULT_FM_ODATA_DATABASE,
    DEFAULT_FM_ODATA_ENABLED,
    DEFAULT_FM_ODATA_HOST,
    DEFAULT_FM_ODATA_PASSWORD,
    DEFAULT_FM_ODATA_PROTOCOL,
    DEFAULT_FM_ODATA_USERNAME,
    DEFAULT_FM_ODATA_VERIFY_SSL,
    DEFAULT_FM_PASSWORD,
    DEFAULT_FM_PROTOCOL,
    DEFAULT_FM_USERNAME,
    DEFAULT_FM_VERIFY_SSL,
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_OCR_ENGINE,
    DEFAULT_OCR_OLLAMA_BASE_URL,
    DEFAULT_OCR_OLLAMA_MODEL,
    DEFAULT_OCR_OLLAMA_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
)


class ProviderConfig(BaseModel):
    """Configuration for the active LLM provider."""

    name: str = "deepseek"
    api_key: str = ""
    api_base: str | None = None
    model: str | None = None


class ToolConfig(BaseModel):
    """Per-tool enable/disable flags."""

    filemaker_query: bool = True
    filemaker_record: bool = True
    filemaker_script: bool = True
    filemaker_layout: bool = True
    ocr: bool = True
    sql_query: bool = True


class GatewayConfig(BaseModel):
    """Gateway server configuration."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    api_key: str = ""
    log_level: str = DEFAULT_LOG_LEVEL
    provider: ProviderConfig = ProviderConfig()
    tools: ToolConfig = ToolConfig()


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    url: str = DEFAULT_DATABASE_URL


class FMDataAPIConfig(BaseModel):
    """FileMaker Data API connection configuration."""

    host: str = DEFAULT_FM_HOST
    database: str = DEFAULT_FM_DATABASE
    username: str = DEFAULT_FM_USERNAME
    password: str = DEFAULT_FM_PASSWORD
    protocol: str = DEFAULT_FM_PROTOCOL
    verify_ssl: bool = DEFAULT_FM_VERIFY_SSL
    enabled: bool = DEFAULT_FM_ENABLED


class FMODataConfig(BaseModel):
    """FileMaker OData v4 connection configuration."""

    host: str = DEFAULT_FM_ODATA_HOST
    database: str = DEFAULT_FM_ODATA_DATABASE
    username: str = DEFAULT_FM_ODATA_USERNAME
    password: str = DEFAULT_FM_ODATA_PASSWORD
    protocol: str = DEFAULT_FM_ODATA_PROTOCOL
    verify_ssl: bool = DEFAULT_FM_ODATA_VERIFY_SSL
    enabled: bool = DEFAULT_FM_ODATA_ENABLED


class OCROllamaConfig(BaseModel):
    """Configuration for local Ollama OCR (GLM-OCR model)."""

    base_url: str = DEFAULT_OCR_OLLAMA_BASE_URL
    model: str = DEFAULT_OCR_OLLAMA_MODEL
    timeout: float = DEFAULT_OCR_OLLAMA_TIMEOUT


class OCRConfig(BaseModel):
    """OCR engine configuration.

    engine="ollama": use local Ollama GLM-OCR via /api/generate
    engine="provider": use the main LLM provider's Vision API
    """

    engine: str = DEFAULT_OCR_ENGINE
    ollama: OCROllamaConfig = OCROllamaConfig()


class AppConfig(BaseModel):
    """Top-level application configuration."""

    gateway: GatewayConfig = GatewayConfig()
    database: DatabaseConfig = DatabaseConfig()
    fm_data_api: FMDataAPIConfig = FMDataAPIConfig()
    fm_odata: FMODataConfig = FMODataConfig()
    ocr: OCRConfig = OCRConfig()
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
