"""Provider factory: create a provider instance from configuration."""

import os

from loguru import logger

from filemaker_gateway.config.schema import ProviderConfig
from filemaker_gateway.provider.base import LLMProvider
from filemaker_gateway.provider.openai_compat import OpenAICompatProvider
from filemaker_gateway.provider.registry import register_provider
from filemaker_gateway.provider.specs import get_spec


# Register known providers
register_provider("openai_compat", OpenAICompatProvider)


def make_provider(config: ProviderConfig) -> LLMProvider:
    """Create a provider instance from configuration.

    Resolution order for API key:
    1. config.api_key (from YAML or FILEMAKER_GATEWAY_PROVIDER_API_KEY env var)
    2. Provider-specific env var (e.g., DEEPSEEK_API_KEY, OPENAI_API_KEY)

    Resolution order for API base:
    1. config.api_base (from YAML or FILEMAKER_GATEWAY_PROVIDER_API_BASE env var)
    2. Provider spec's default_api_base
    """
    spec = get_spec(config.name)

    # Resolve API key
    api_key = config.api_key
    if not api_key and spec:
        api_key = os.environ.get(spec.env_key, "")

    # Resolve API base
    api_base = config.api_base
    if not api_base and spec:
        api_base = spec.default_api_base

    # Resolve model
    model = config.model
    if not model and spec:
        model = spec.default_model

    # Resolve backend
    backend = "openai_compat"
    if spec:
        backend = spec.backend

    if backend == "openai_compat":
        provider = OpenAICompatProvider(
            api_key=api_key,
            api_base=api_base,
            default_model=model or "gpt-4o",
        )
        logger.info(
            "Created provider: {} (model={}, base={})",
            config.name,
            model,
            api_base,
        )
        return provider

    # Future: add anthropic, etc.
    raise ValueError(f"Unsupported provider backend: '{backend}' for provider '{config.name}'")
