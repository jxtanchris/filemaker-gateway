"""FileMakerQueryTool: SELECT, ExecuteSQL, and Find operations.

Uses FMDataClient for real Data API access.
Accepts fm_client via constructor for dependency injection.
"""

import json

from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.fm.errors import FMDataError
from filemaker_gateway.tool.base import Tool, ToolResult


class FileMakerQueryTool(Tool):
    """Query FileMaker data via SELECT, ExecuteSQL, or Find."""

    def __init__(self, fm_client: FMDataClient | None = None) -> None:
        self._fm = fm_client

    @property
    def name(self) -> str:
        return "filemaker_query"

    @property
    def description(self) -> str:
        return (
            "Query FileMaker database records. "
            "Use 'select' to read records from a layout, "
            "use 'execute_sql' for raw SQL queries, "
            "use 'find' to search for records matching criteria. "
            "For 'select' and 'find', provide the layout name. "
            "For 'execute_sql', provide the SQL query string."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["select", "execute_sql", "find"],
                    "description": "The query action to perform.",
                },
                "layout": {
                    "type": "string",
                    "description": "The FileMaker layout name (for select and find actions).",
                },
                "query": {
                    "type": "string",
                    "description": "SQL query (for execute_sql) or JSON find criteria (for find).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of records to return (default: 100).",
                },
            },
            "required": ["action"],
        }

    @property
    def read_only(self) -> bool:
        return True

    async def execute(
        self,
        action: str,
        layout: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> ToolResult | str:
        if self._fm is None:
            return ToolResult.error("FM Data API 未启用 (fm_data_api.enabled=false)")

        try:
            if action == "select":
                if not layout:
                    return ToolResult.error("layout is required for 'select' action")
                records = await self._fm.get_records(layout, limit=limit)
                return json.dumps(records, ensure_ascii=False, default=str)

            elif action == "find":
                if not layout:
                    return ToolResult.error("layout/table name is required for 'find' action")

                # Compatible with both OData ($filter string) and Data API (JSON array/object)
                if query and query.strip().startswith("["):
                    # Data API: JSON array of criteria
                    try:
                        criteria = json.loads(query)
                    except json.JSONDecodeError:
                        return ToolResult.error("query must be valid JSON array for Data API find")
                elif query and query.strip().startswith("{"):
                    # JSON object — convert to OData $filter or treat as-is
                    try:
                        obj = json.loads(query)
                        filters = []
                        for k, v in obj.items():
                            if v == "*" or v == "":
                                continue  # wildcard — skip filter
                            escaped_v = str(v).replace("'", "''")
                            filters.append(f"{k} eq '{escaped_v}'")
                        criteria = " and ".join(filters) if filters else ""
                    except json.JSONDecodeError:
                        criteria = query
                else:
                    # OData: $filter string (or empty for all records)
                    criteria = query or ""

                records = await self._fm.find(layout, criteria, limit=limit)
                return json.dumps(records, ensure_ascii=False, default=str)

            elif action == "execute_sql":
                return ToolResult.error(
                    "execute_sql is not supported via FileMaker Data API. "
                    "Use 'find' or 'select' actions instead, or call a FileMaker script "
                    "that runs ExecuteSQL internally."
                )

            else:
                return ToolResult.error(f"Unknown action: '{action}'")

        except FMDataError as e:
            return ToolResult.error(f"FileMaker Data API error: {e}")
        except json.JSONDecodeError:
            return ToolResult.error("query parameter must be valid JSON for 'find' action")
        except Exception as e:
            return ToolResult.error(f"Query failed: {e}")
