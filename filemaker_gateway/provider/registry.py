"""Provider registry: maps provider names to implementation classes."""

from filemaker_gateway.provider.base import LLMProvider

_registry: dict[str, type[LLMProvider]] = {}


def register_provider(name: str, provider_cls: type[LLMProvider]) -> None:
    """Register a provider implementation class."""
    _registry[name] = provider_cls


def get_provider_cls(name: str) -> type[LLMProvider] | None:
    """Get a provider implementation class by name."""
    return _registry.get(name)


def list_registered() -> list[str]:
    """List registered provider names."""
    return list(_registry.keys())
