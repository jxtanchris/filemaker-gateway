"""FileMaker OData v4 REST client.

Wraps the FileMaker Server OData API with Basic Auth,
CRUD operations, script execution, and container support.
No token management needed — Basic Auth per request.
"""

from typing import Any
from urllib.parse import quote

import httpx
from loguru import logger

from filemaker_gateway.config.schema import FMODataConfig
from filemaker_gateway.fm.errors import (
    FMAuthError,
    FMDataError,
    FMNotFoundError,
    FMValidationError,
)

_HTTP_ERROR_MAP: dict[int, type[FMDataError]] = {
    401: FMAuthError,
    404: FMNotFoundError,
    400: FMValidationError,
}


class FMODataClient:
    """Async HTTP client for FileMaker OData v4 API.

    Uses Basic Auth on every request (no token lifecycle).
    Provides the same interface as FMDataClient for Tool compatibility.
    """

    def __init__(self, config: FMODataConfig) -> None:
        self._config = config
        self._base_url = (
            f"{config.protocol}://{config.host}"
            f"/fmi/odata/v4/{config.database}"
        )
        self._auth = httpx.BasicAuth(config.username, config.password)
        self._client = httpx.AsyncClient(
            auth=self._auth,
            verify=config.verify_ssl,
            timeout=httpx.Timeout(60.0),
        )

    # Binary content prefixes to detect container field data
    _BINARY_PREFIXES = ("/9j/", "iVBOR", "R0lGOD", "JVBERi0", "SUkqAA")

    @staticmethod
    def _strip_containers(records: list[dict]) -> list[dict]:
        """Replace base64 container data with [binary data] to keep responses small."""
        result = []
        for r in records:
            cleaned = {}
            for k, v in r.items():
                if isinstance(v, str) and any(v.startswith(p) for p in FMODataClient._BINARY_PREFIXES):
                    cleaned[k] = "[binary data]"
                else:
                    cleaned[k] = v
            result.append(cleaned)
        return result

    def _check_errors(self, data: dict | None, status_code: int) -> None:
        """Raise appropriate exception from HTTP status."""
        if status_code < 400:
            return
        message = ""
        if data and "error" in data:
            message = data["error"].get("message", "")
        exc_cls = _HTTP_ERROR_MAP.get(status_code, FMDataError)
        if exc_cls is FMDataError:
            raise exc_cls(status_code, message or f"HTTP {status_code}")
        else:
            raise exc_cls(message or f"HTTP {status_code}")

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict | None:
        """Safely parse JSON from response, returning None on failure."""
        try:
            return response.json()
        except Exception:
            return None

    @staticmethod
    def _build_query(**kwargs) -> str:
        """Build OData query string WITHOUT encoding $ signs.

        httpx encodes $top to %24top which FileMaker Server rejects.
        We construct the query string manually to preserve literal $ chars.
        """
        parts = []
        for k, v in kwargs.items():
            if v is not None and v != "":
                parts.append(f"{k}={v}")
        return "&".join(parts)

    # --- CRUD ---

    async def get_records(
        self,
        table: str,
        offset: int = 1,
        limit: int = 100,
        sort: list[dict[str, str]] | None = None,
    ) -> list[dict]:
        """Read records from a table using OData $top/$skip."""
        skip = offset - 1
        orderby = None
        if sort and len(sort) > 0:
            orderby = ",".join(
                f"{s['fieldName']} {s.get('sortOrder', 'asc')}" for s in sort
            )

        qs = self._build_query(**{"$top": limit, "$skip": skip, "$orderby": orderby})
        url = f"{self._base_url}/{quote(table, safe='')}?{qs}" if qs else f"{self._base_url}/{quote(table, safe='')}"

        logger.debug("OData GET records: table={}, limit={}, skip={}", table, limit, skip)
        response = await self._client.get(url)
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        data = response.json()
        return self._strip_containers(data.get("value", []))

    async def get_record(self, table: str, record_id: str) -> dict:
        """Get a single record by primary key."""
        escaped_pk = quote(record_id, safe="")
        logger.debug("OData GET record: table={}, pk={}", table, escaped_pk)
        response = await self._client.get(
            f"{self._base_url}/{quote(table, safe='')}('{escaped_pk}')",
        )
        if response.status_code == 404:
            raise FMNotFoundError(f"Record '{record_id}' not found in table '{table}'")
        self._check_errors(None if response.status_code < 400 else self._safe_json(response), response.status_code)
        return response.json()

    async def create_record(
        self,
        table: str,
        field_data: dict[str, Any],
    ) -> dict:
        """Create a new record. Container fields accept base64 strings."""
        logger.debug("OData CREATE record: table={}", table)
        response = await self._client.post(
            f"{self._base_url}/{quote(table, safe='')}",
            json=field_data,
        )
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        return response.json()

    async def update_record(
        self,
        table: str,
        record_id: str,
        field_data: dict[str, Any],
        mod_id: str | None = None,  # ignored — OData has no modId concept
    ) -> dict:
        """Update an existing record by primary key."""
        escaped_pk = quote(record_id, safe="")
        logger.debug("OData UPDATE record: table={}, pk={}", table, escaped_pk)
        response = await self._client.patch(
            f"{self._base_url}/{quote(table, safe='')}('{escaped_pk}')",
            json=field_data,
        )
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        return response.json()

    async def delete_record(self, table: str, record_id: str) -> None:
        """Delete a record by primary key."""
        escaped_pk = quote(record_id, safe="")
        logger.debug("OData DELETE record: table={}, pk={}", table, escaped_pk)
        response = await self._client.delete(
            f"{self._base_url}/{quote(table, safe='')}('{escaped_pk}')",
        )
        if response.status_code == 204:
            return
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)

    # --- Find ---

    async def find(
        self,
        table: str,
        filter_str: str = "",
        sort: list[dict[str, str]] | None = None,
        offset: int = 1,
        limit: int = 100,
    ) -> list[dict]:
        """Find records using OData $filter."""
        skip = offset - 1
        orderby = None
        if sort:
            orderby = ",".join(
                f"{s['fieldName']} {s.get('sortOrder', 'asc')}" for s in sort
            )

        qs = self._build_query(**{
            "$top": limit, "$skip": skip,
            "$filter": filter_str or None,
            "$orderby": orderby,
        })
        url = f"{self._base_url}/{quote(table, safe='')}?{qs}" if qs else f"{self._base_url}/{quote(table, safe='')}"

        logger.debug("OData FIND: table={}, filter={}", table, filter_str)
        response = await self._client.get(url)
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        data = response.json()
        return self._strip_containers(data.get("value", []))

    # --- Scripts ---

    async def run_script(
        self,
        layout: str,
        script_name: str | None = None,
        script_param: str | None = None,
    ) -> dict:
        """Execute a FileMaker script.

        Compatible with Data API calling convention:
        run_script(layout, script_name, script_param).

        OData does not require a layout context — the `layout` parameter
        is accepted for compatibility but ignored. Scripts are called via
        POST /Script.{scriptName}.

        Also supports old OData style: run_script(name, param).
        """
        # Detect calling convention
        if script_name is None:
            # OData style: run_script(name, param_or_none)
            name = layout
            param = script_param
        else:
            # Data API style: run_script(layout, name, param)
            name = script_name
            param = script_param

        body: dict[str, Any] = {}
        if param is not None:
            body["scriptParameterValue"] = param

        logger.debug("OData RUN script: name={}", name)
        response = await self._client.post(
            f"{self._base_url}/Script.{name}",
            json=body,
        )
        if response.status_code == 404:
            raise FMNotFoundError(f"Script '{name}' not found")
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        return response.json()

    # --- Metadata ---

    async def get_tables(self) -> list[str]:
        """Get all table names."""
        logger.debug("OData GET tables")
        response = await self._client.get(f"{self._base_url}/")
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        data = response.json()
        return [t.get("name", "") for t in data.get("value", [])]

    async def get_table_metadata(self, table: str) -> dict:
        """Get metadata for a table using $metadata."""
        logger.debug("OData GET table metadata: {}", table)
        response = await self._client.get(
            f"{self._base_url}/{quote(table, safe='')}?$top=0",
        )
        if response.status_code == 404:
            raise FMNotFoundError(f"Table '{table}' not found")
        self._check_errors(None if response.status_code < 400 else self._safe_json(response), response.status_code)
        # OData returns field info in @odata.context or $metadata
        # Return first record as sample to show field structure
        return {"fields": list(response.json().get("value", []) or [])}

    # --- Layout compatibility (OData uses tables, not layouts) ---

    async def get_layouts(self) -> list[str]:
        """Get all table names (layout-compatible alias for get_tables)."""
        return await self.get_tables()

    async def get_layout_metadata(self, layout: str) -> dict:
        """Get metadata for a table (layout-compatible alias).

        OData returns field info differently than Data API.
        We fetch a zero-row query to discover field names, then wrap in
        a Data-API-compatible format.
        """
        # Try $top=0 to get field info from @odata.context
        logger.debug("OData GET layout metadata: {}", layout)
        response = await self._client.get(
            f"{self._base_url}/{quote(layout, safe='')}?$top=0",
        )
        if response.status_code == 404:
            raise FMNotFoundError(f"Table '{layout}' not found")
        self._check_errors(
            self._safe_json(response) if response.status_code >= 400 else None,
            response.status_code,
        )
        data = response.json()
        # Try to infer fields from the first record (with $top=1)
        sample_resp = await self._client.get(
            f"{self._base_url}/{quote(layout, safe='')}?$top=1",
        )
        sample = sample_resp.json()
        fields = []
        if sample.get("value"):
            for k, v in sample["value"][0].items():
                if not k.startswith("@") and not k.endswith("_pk"):
                    fields.append({
                        "name": k,
                        "type": type(v).__name__,
                        "displayType": "editText",
                        "result": str(type(v).__name__),
                    })
        return {"fieldMetaData": fields}

    # --- Container ---

    async def upload_container(
        self,
        table: str,
        record_id: str,
        field_name: str,
        base64_data: str,
    ) -> bool:
        """Upload to container field via base64-encoded value in PATCH."""
        await self.update_record(table, record_id, {field_name: base64_data})
        return True

    async def get_container_url(
        self,
        table: str,
        record_id: str,
        field_name: str,
    ) -> str:
        """Get container field content (returns base64 string)."""
        record = await self.get_record(table, record_id)
        value = record.get(field_name, "")
        if not value:
            raise FMNotFoundError(f"Container field '{field_name}' is empty")
        return f"data:;base64,{value}"

    # --- Lifecycle ---

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.aclose()
        logger.debug("FMODataClient closed")
