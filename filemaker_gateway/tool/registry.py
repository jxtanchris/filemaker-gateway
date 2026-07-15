"""Tool registry: register, discover, and execute tools."""

from typing import Any

from loguru import logger

from filemaker_gateway.tool.base import Tool, ToolResult


class ToolRegistry:
    """Registry of available tools for the agent.

    Tools are registered by name and can be retrieved
    for execution or schema export.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance. Overwrites existing tool with same name."""
        if tool.name in self._tools:
            logger.warning(
                "Tool '{}' is being overwritten by a new registration", tool.name
            )
        self._tools[tool.name] = tool
        logger.debug("Registered tool: {}", tool.name)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get OpenAI function definitions for all registered tools."""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with the given arguments.

        Returns:
            The tool's output as a string, or an error message.
        """
        tool = self.get(name)
        if tool is None:
            msg = f"Unknown tool: '{name}'. Available: {self.tool_names}"
            logger.warning(msg)
            return str(ToolResult.error(msg))

        # Validate parameters
        errors = tool.validate_params(arguments)
        if errors:
            msg = f"Tool '{name}' parameter validation failed: {'; '.join(errors)}"
            logger.warning(msg)
            return str(ToolResult.error(msg))

        try:
            logger.info("Executing tool '{}' with args: {}", name, arguments)
            result = await tool.execute(**arguments)

            # Normalize result to string
            if isinstance(result, ToolResult):
                return str(result)
            return str(result)

        except Exception as e:
            msg = f"Tool '{name}' execution failed: {e}"
            logger.exception(msg)
            return str(ToolResult.error(msg))

    @property
    def tool_names(self) -> list[str]:
        """List of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
