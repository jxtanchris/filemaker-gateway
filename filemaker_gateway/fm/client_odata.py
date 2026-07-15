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
            f"/fmi/odata/v4/databases/{config.database}"
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
        url = f"{self._base_url}/tables/{quote(table, safe='')}?{qs}" if qs else f"{self._base_url}/tables/{quote(table, safe='')}"

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
            f"{self._base_url}/tables/{quote(table, safe='')}('{escaped_pk}')",
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
            f"{self._base_url}/tables/{quote(table, safe='')}",
            json=field_data,
        )
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        return response.json()

    async def update_record(
        self,
        table: str,
        record_id: str,
        field_data: dict[str, Any],
    ) -> dict:
        """Update an existing record by primary key."""
        escaped_pk = quote(record_id, safe="")
        logger.debug("OData UPDATE record: table={}, pk={}", table, escaped_pk)
        response = await self._client.patch(
            f"{self._base_url}/tables/{quote(table, safe='')}('{escaped_pk}')",
            json=field_data,
        )
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        return response.json()

    async def delete_record(self, table: str, record_id: str) -> None:
        """Delete a record by primary key."""
        escaped_pk = quote(record_id, safe="")
        logger.debug("OData DELETE record: table={}, pk={}", table, escaped_pk)
        response = await self._client.delete(
            f"{self._base_url}/tables/{quote(table, safe='')}('{escaped_pk}')",
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
        url = f"{self._base_url}/tables/{quote(table, safe='')}?{qs}" if qs else f"{self._base_url}/tables/{quote(table, safe='')}"

        logger.debug("OData FIND: table={}, filter={}", table, filter_str)
        response = await self._client.get(url)
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        data = response.json()
        return self._strip_containers(data.get("value", []))

    # --- Scripts ---

    async def run_script(
        self,
        script_name: str,
        script_param: str | None = None,
    ) -> dict:
        """Execute a FileMaker script via OData.

        POST /Script.{scriptName} with optional scriptParameterValue.
        No layout context needed (unlike Data API).
        """
        body: dict[str, Any] = {}
        if script_param is not None:
            body["scriptParameterValue"] = script_param

        logger.debug("OData RUN script: name={}", script_name)
        response = await self._client.post(
            f"{self._base_url}/Script.{script_name}",
            json=body,
        )
        if response.status_code == 404:
            raise FMNotFoundError(f"Script '{script_name}' not found")
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        return response.json()

    # --- Metadata ---

    async def get_tables(self) -> list[str]:
        """Get all table names."""
        logger.debug("OData GET tables")
        response = await self._client.get(f"{self._base_url}/tables")
        self._check_errors(self._safe_json(response) if response.status_code >= 400 else None, response.status_code)
        data = response.json()
        return [t.get("name", "") for t in data.get("value", [])]

    async def get_table_metadata(self, table: str) -> dict:
        """Get metadata for a table using $metadata."""
        logger.debug("OData GET table metadata: {}", table)
        response = await self._client.get(
            f"{self._base_url}/tables/{quote(table, safe='')}?$top=0",
        )
        if response.status_code == 404:
            raise FMNotFoundError(f"Table '{table}' not found")
        self._check_errors(None if response.status_code < 400 else self._safe_json(response), response.status_code)
        # OData returns field info in @odata.context or $metadata
        # Return first record as sample to show field structure
        return {"fields": list(response.json().get("value", []) or [])}

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
