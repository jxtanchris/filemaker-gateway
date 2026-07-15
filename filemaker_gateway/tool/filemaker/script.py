"""FileMakerScriptTool: Execute FileMaker scripts.

Uses FMDataClient for real Data API access.
Accepts fm_client via constructor for dependency injection.
Run_script needs a layout context — uses the first available layout.
"""

import json

from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.fm.errors import FMDataError
from filemaker_gateway.tool.base import Tool, ToolResult


class FileMakerScriptTool(Tool):
    """Execute FileMaker scripts (print, export PDF, generate barcode, etc.)."""

    def __init__(self, fm_client: FMDataClient | None = None) -> None:
        self._fm = fm_client

    @property
    def name(self) -> str:
        return "filemaker_script"

    @property
    def description(self) -> str:
        return (
            "Execute a FileMaker script by name. "
            "Scripts can perform actions like printing, exporting PDFs, "
            "generating barcodes, sending emails, or running custom business logic. "
            "Pass parameters as a string (FileMaker Get(ScriptParameter) convention)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "script_name": {
                    "type": "string",
                    "description": "The name of the FileMaker script to execute.",
                },
                "parameter": {
                    "type": "string",
                    "description": "Optional parameter to pass to the script (accessible via Get(ScriptParameter)).",
                },
            },
            "required": ["script_name"],
        }

    async def execute(
        self,
        script_name: str,
        parameter: str | None = None,
    ) -> ToolResult | str:
        if self._fm is None:
            return ToolResult.error("FM Data API 未启用 (fm_data_api.enabled=false)")

        try:
            # FileMaker Data API requires a layout context for script execution.
            # We use the first available layout as context.
            layouts = await self._fm.get_layouts()
            if not layouts:
                return ToolResult.error("No layouts available to run script in context")

            result = await self._fm.run_script(layouts[0], script_name, parameter)

            # Check for script errors
            if "scriptResult.error" in result:
                return ToolResult.error(
                    f"Script '{script_name}' returned error: {result.get('scriptResult', 'Unknown error')}"
                )

            return json.dumps(result, ensure_ascii=False, default=str)

        except FMDataError as e:
            return ToolResult.error(f"FileMaker Data API error: {e}")
        except Exception as e:
            return ToolResult.error(f"Script execution failed: {e}")
