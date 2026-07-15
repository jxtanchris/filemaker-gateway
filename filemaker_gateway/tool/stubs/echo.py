"""Echo tool for testing the tool system."""

from filemaker_gateway.tool.base import Tool


class EchoTool(Tool):
    """A simple echo tool for testing."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes back the input message."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message to echo."},
            },
            "required": ["message"],
        }

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, message: str = "") -> str:
        return f"Echo: {message}"
