"""Tool abstract base class and ToolResult.

Adapted from nanobot's agent/tools/base.py pattern:
- Tool: ABC with name, description, parameters, execute()
- ToolResult: string subclass with is_error flag
- to_schema(): OpenAI function-calling format
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any


class ToolResult(str):
    """String-compatible tool output with structured error status.

    Usage:
        return ToolResult(json.dumps(data))
        return ToolResult.error("Something went wrong")
    """

    def __new__(cls, content: str, *, is_error: bool = False) -> "ToolResult":
        instance = super().__new__(cls, content)
        instance.is_error = is_error  # type: ignore[attr-defined]
        return instance

    @classmethod
    def error(cls, content: str) -> "ToolResult":
        """Shorthand for creating an error result."""
        return cls(content, is_error=True)


class Tool(ABC):
    """Base class for all agent tools.

    Each tool must provide:
    - name: unique identifier used in LLM function calls
    - description: what the tool does (goes into system prompt context)
    - parameters: JSON Schema for tool arguments
    - execute(): the actual implementation

    Optional:
    - read_only: True if the tool has no side effects (default False)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier, e.g. 'ocr', 'filemaker_query'."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the tool does."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema describing the tool's parameters."""
        ...

    @property
    def read_only(self) -> bool:
        """Whether this tool is side-effect free."""
        return False

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with the given parameters.

        Returns:
            A string (or ToolResult) with the tool output.
            Use ToolResult.error() to signal failures.
        """
        ...

    def to_schema(self) -> dict[str, Any]:
        """Export as OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate parameters against the tool's JSON Schema.

        Returns a list of error messages (empty if valid).
        """
        errors: list[str] = []
        schema = self.parameters

        if schema.get("type") != "object":
            return errors  # Skip validation for non-object schemas

        required: list[str] = schema.get("required", [])
        properties: dict[str, dict] = schema.get("properties", {})

        # Check required fields
        for field in required:
            if field not in params:
                errors.append(f"Missing required parameter: '{field}'")

        # Check types of provided fields
        for key, value in params.items():
            if key not in properties:
                continue  # Allow extra fields, LLM may hallucinate
            prop = properties[key]
            expected_type = prop.get("type", "string")

            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"Parameter '{key}' should be a string")
            elif expected_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"Parameter '{key}' should be a number")
            elif expected_type == "integer" and not isinstance(value, int):
                errors.append(f"Parameter '{key}' should be an integer")
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"Parameter '{key}' should be a boolean")
            elif expected_type == "array" and not isinstance(value, list):
                errors.append(f"Parameter '{key}' should be an array")
            elif expected_type == "object" and not isinstance(value, dict):
                errors.append(f"Parameter '{key}' should be an object")

        return errors
