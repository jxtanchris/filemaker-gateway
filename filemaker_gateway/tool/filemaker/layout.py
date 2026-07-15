"""FileMakerLayoutTool: Navigate layouts and windows."""

import json

from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.fm.errors import FMDataError
from filemaker_gateway.tool.base import Tool, ToolResult


class FileMakerLayoutTool(Tool):
    """Navigate FileMaker layouts: list layouts, get layout metadata."""

    def __init__(self, fm_client: FMDataClient | None = None) -> None:
        self._fm = fm_client

    @property
    def name(self) -> str:
        return "filemaker_layout"

    @property
    def description(self) -> str:
        return (
            "Navigate within FileMaker. "
            "Use 'list_layouts' to get available layout names, "
            "use 'open_layout' to get metadata about a specific layout. "
            "Note: 'next_record' and 'previous_record' are not available "
            "via the Data API (they require a client-side FileMaker session)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list_layouts",
                        "open_layout",
                        "next_record",
                        "previous_record",
                    ],
                    "description": "The navigation action to perform.",
                },
                "layout_name": {
                    "type": "string",
                    "description": "The layout name (required for open_layout).",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        layout_name: str | None = None,
    ) -> ToolResult | str:
        if self._fm is None:
            return ToolResult.error("FM Data API 未启用 (fm_data_api.enabled=false)")

        try:
            if action == "list_layouts":
                layouts = await self._fm.get_layouts()
                return json.dumps(layouts, ensure_ascii=False)

            elif action == "open_layout":
                if not layout_name:
                    return ToolResult.error("layout_name is required for 'open_layout'")
                metadata = await self._fm.get_layout_metadata(layout_name)
                return json.dumps(metadata, ensure_ascii=False, default=str)

            elif action in ("next_record", "previous_record"):
                return ToolResult.error(
                    f"'{action}' is not supported via FileMaker Data API. "
                    "Record navigation requires a client-side FileMaker session."
                )

            else:
                return ToolResult.error(f"Unknown action: '{action}'")

        except FMDataError as e:
            return ToolResult.error(f"FileMaker Data API error: {e}")
        except Exception as e:
            return ToolResult.error(f"Layout operation failed: {e}")
