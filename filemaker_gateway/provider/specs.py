"""ProviderSpec entries for supported LLM providers.

Following nanobot's pattern: each provider has a spec
with name, backend type, default API base, and default model.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    """Metadata for a registered LLM provider."""

    name: str                  # Short key: "deepseek", "openai", "glm", etc.
    backend: str               # "openai_compat" or "anthropic"
    env_key: str               # Environment variable for API key
    default_api_base: str      # Default API endpoint
    default_model: str         # Default model name
    display_name: str          # Human-readable name
    supports_vision: bool = False  # Whether the provider natively supports image_url in messages


# Registry of known providers
PROVIDER_SPECS: list[ProviderSpec] = [
    ProviderSpec(
        name="deepseek",
        backend="openai_compat",
        env_key="DEEPSEEK_API_KEY",
        default_api_base="https://api.deepseek.com",
        default_model="deepseek-chat",
        display_name="DeepSeek",
    ),
    ProviderSpec(
        name="openai",
        backend="openai_compat",
        env_key="OPENAI_API_KEY",
        default_api_base="https://api.openai.com/v1",
        default_model="gpt-4o",
        display_name="OpenAI GPT",
        supports_vision=True,
    ),
    ProviderSpec(
        name="glm",
        backend="openai_compat",
        env_key="GLM_API_KEY",
        default_api_base="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4-flash",
        display_name="智谱 GLM",
        supports_vision=True,
    ),
    ProviderSpec(
        name="claude",
        backend="anthropic",
        env_key="ANTHROPIC_API_KEY",
        default_api_base="https://api.anthropic.com",
        default_model="claude-sonnet-4-20250514",
        display_name="Anthropic Claude",
        supports_vision=True,
    ),
    ProviderSpec(
        name="gemini",
        backend="openai_compat",
        env_key="GEMINI_API_KEY",
        default_api_base="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.0-flash",
        display_name="Google Gemini",
        supports_vision=True,
    ),
    ProviderSpec(
        name="ollama",
        backend="openai_compat",
        env_key="OLLAMA_API_KEY",
        default_api_base="http://localhost:11434/v1",
        default_model="llama3",
        display_name="Ollama (Local)",
    ),
]


def get_spec(name: str) -> ProviderSpec | None:
    """Look up a provider spec by name."""
    for spec in PROVIDER_SPECS:
        if spec.name == name:
            return spec
    return None


def list_specs() -> list[ProviderSpec]:
    """List all registered provider specs."""
    return list(PROVIDER_SPECS)
