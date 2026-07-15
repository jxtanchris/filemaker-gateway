"""Tool loader: auto-discover Tool subclasses from the tool package.

Scans the filemaker_gateway/tool/ package for Tool subclasses,
instantiates them, and registers them in a ToolRegistry.

Also supports plugin entry points under 'filemaker_gateway.tools'
for external tool packages.
"""

import importlib
import inspect
import pkgutil
from typing import Any

from loguru import logger

from filemaker_gateway.tool.base import Tool
from filemaker_gateway.tool.registry import ToolRegistry

# Modules to skip during discovery (infrastructure, not tools)
_SKIP_MODULES = {
    "base",
    "registry",
    "loader",
    "schema",
    "init",
    "__init__",
}


class ToolLoader:
    """Discovers and loads Tool implementations."""

    def __init__(self, package: Any = None) -> None:
        """Create a tool loader.

        Args:
            package: The Python package to scan. Defaults to
                filemaker_gateway.tool and its subpackages.
        """
        if package is None:
            import filemaker_gateway.tool as pkg
            package = pkg
        self._package = package
        self._path = package.__path__ if hasattr(package, "__path__") else []

    def discover(self) -> list[type[Tool]]:
        """Find all Tool subclasses in the tool package.

        Walks the package tree, imports each module, and inspects
        its namespace for Tool subclasses.
        """
        found: list[type[Tool]] = []

        for _, module_name, is_pkg in pkgutil.walk_packages(
            self._path, prefix=self._package.__name__ + "."
        ):
            base_name = module_name.rsplit(".", 1)[-1]
            if base_name in _SKIP_MODULES:
                continue

            try:
                module = importlib.import_module(module_name)
            except Exception as e:
                logger.warning("Failed to import tool module '{}': {}", module_name, e)
                continue

            # Inspect module for Tool subclasses
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Tool)
                    and attr is not Tool
                ):
                    found.append(attr)
                    logger.debug("Discovered tool: {} in {}", attr.__name__, module_name)

        return found

    def load(self, registry: ToolRegistry, **tool_kwargs: Any) -> list[str]:
        """Discover and register all tools.

        Args:
            registry: The ToolRegistry to register tools into.
            **tool_kwargs: Optional dependencies to inject into Tool constructors.
                Each kwarg is only passed to tools whose __init__ accepts it
                (matched by parameter name via inspect.signature).

        Returns:
            List of registered tool names.
        """
        tool_classes = self.discover()

        # Also load from entry points (plugin system)
        self._load_entry_points(registry)

        for tool_cls in tool_classes:
            try:
                # Match constructor parameters to available kwargs
                sig = inspect.signature(tool_cls.__init__)
                matching_kwargs = {
                    k: v for k, v in tool_kwargs.items()
                    if k in sig.parameters
                }
                instance = tool_cls(**matching_kwargs)
                registry.register(instance)
                logger.info("Loaded tool: {}", instance.name)
            except Exception as e:
                logger.warning("Failed to instantiate tool '{}': {}", tool_cls.__name__, e)

        return registry.tool_names

    def _load_entry_points(self, registry: ToolRegistry) -> None:
        """Load tools registered via entry_points."""
        try:
            # Use importlib.metadata for entry point discovery (Python 3.12+)
            from importlib.metadata import entry_points

            eps = entry_points(group="filemaker_gateway.tools")
            for ep in eps:
                try:
                    tool_cls = ep.load()
                    if issubclass(tool_cls, Tool):
                        instance = tool_cls()
                        registry.register(instance)
                        logger.info("Loaded plugin tool: {} from {}", instance.name, ep.value)
                except Exception as e:
                    logger.warning("Failed to load plugin tool '{}': {}", ep.name, e)
        except Exception:
            # importlib.metadata may not be available or entry_points not configured
            pass
