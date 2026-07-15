"""FileMakerRecordTool: Create, update, and delete records."""

import json

from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.fm.errors import FMDataError
from filemaker_gateway.tool.base import Tool, ToolResult


class FileMakerRecordTool(Tool):
    """Create, update, or delete records in FileMaker."""

    def __init__(self, fm_client: FMDataClient | None = None) -> None:
        self._fm = fm_client

    @property
    def name(self) -> str:
        return "filemaker_record"

    @property
    def description(self) -> str:
        return (
            "Create, update, or delete records in a FileMaker database. "
            "Use 'create' to add a new record with field data, "
            "use 'update' to modify an existing record by record ID, "
            "use 'delete' to remove a record by record ID. "
            "IMPORTANT: Always confirm with the user before updating or deleting."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "delete"],
                    "description": "The record operation to perform.",
                },
                "layout": {
                    "type": "string",
                    "description": "The FileMaker layout to operate on.",
                },
                "record_id": {
                    "type": "string",
                    "description": "The record ID (required for update and delete).",
                },
                "field_data": {
                    "type": "object",
                    "description": "Key-value pairs of field names and values (for create and update).",
                },
            },
            "required": ["action", "layout"],
        }

    async def execute(
        self,
        action: str,
        layout: str,
        record_id: str | None = None,
        field_data: dict | None = None,
    ) -> ToolResult | str:
        if self._fm is None:
            return ToolResult.error("FM Data API 未启用 (fm_data_api.enabled=false)")

        if action in ("update", "delete") and not record_id:
            return ToolResult.error(f"record_id is required for '{action}' action")

        try:
            if action == "create":
                result = await self._fm.create_record(layout, field_data or {})
                return json.dumps(result, ensure_ascii=False)

            elif action == "update":
                result = await self._fm.update_record(layout, record_id, field_data or {}, None)
                return json.dumps(result, ensure_ascii=False)

            elif action == "delete":
                await self._fm.delete_record(layout, record_id)
                return ToolResult(f"Record '{record_id}' deleted from '{layout}'")

            else:
                return ToolResult.error(f"Unknown action: '{action}'")

        except FMDataError as e:
            return ToolResult.error(f"FileMaker Data API error: {e}")
        except Exception as e:
            return ToolResult.error(f"Record operation failed: {e}")
