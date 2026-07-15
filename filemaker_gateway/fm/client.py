"""FileMaker Data API REST client.

Wraps the FileMaker Server Data API with automatic token management,
CRUD operations, script execution, and container field support.
"""

from typing import Any

import httpx
from loguru import logger

from filemaker_gateway.config.schema import FMDataAPIConfig
from filemaker_gateway.fm.errors import (
    FMAuthError,
    FMDataError,
    FMNotFoundError,
    FMValidationError,
)

# HTTP status code -> exception mapping
_HTTP_ERROR_MAP: dict[int, type[FMDataError]] = {
    401: FMAuthError,
    404: FMNotFoundError,
    400: FMValidationError,
}

# FileMaker native error codes -> exception mapping
# (returned in HTTP 200 response body with code != 0)
_FM_CODE_MAP: dict[int, type[FMDataError]] = {
    101: FMNotFoundError,   # Record is missing
    401: FMAuthError,       # No access
    212: FMAuthError,       # Invalid account name/password
}


class FMDataClient:
    """Async HTTP client for FileMaker Data API.

    Manages authentication token lifecycle and provides
    typed methods for CRUD, find, script, and container operations.

    Usage:
        config = FMDataAPIConfig(host="...", database="...", ...)
        client = FMDataClient(config)
        records = await client.get_records("Contacts")
        await client.close()
    """

    def __init__(self, config: FMDataAPIConfig) -> None:
        self._config = config
        self._token: str | None = None
        self._base_url = (
            f"{config.protocol}://{config.host}"
            f"/fmi/data/vLatest/databases/{config.database}"
        )
        self._client = httpx.AsyncClient(
            verify=config.verify_ssl,
            timeout=httpx.Timeout(60.0),
        )

    # --- Token management ---

    async def _ensure_token(self) -> str:
        """Get a valid token, logging in if necessary.

        FileMaker Data API tokens expire after ~15 minutes.
        This method automatically re-authenticates when needed.
        """
        if self._token is not None:
            return self._token

        logger.info("Authenticating to FileMaker Data API at {}", self._config.host)
        try:
            response = await self._client.post(
                f"{self._base_url}/sessions",
                headers={"Content-Type": "application/json"},
                json={},
                auth=httpx.BasicAuth(self._config.username, self._config.password),
            )
        except httpx.TimeoutException:
            raise FMDataError(0, "Connection timed out while authenticating to FileMaker Server")
        except httpx.ConnectError as e:
            raise FMDataError(0, f"Cannot connect to FileMaker Server at {self._config.host}: {e}")

        data = response.json()

        # Check for FM errors
        self._check_errors(data, response.status_code)

        token = data.get("response", {}).get("token", "")
        if not token:
            raise FMAuthError("No token returned from FileMaker Server")

        self._token = token
        logger.debug("Authenticated successfully")
        return token

    def _invalidate_token(self) -> None:
        """Clear the cached token, forcing re-authentication on next request."""
        self._token = None

    async def _request_with_retry(self, request_fn) -> Any:
        """Execute an API request with automatic 401 retry.

        If the token expires mid-session, this catches the 401,
        re-authenticates, and retries the request once.
        """
        try:
            return await request_fn()
        except FMAuthError:
            # Token may have expired — retry once with fresh auth
            logger.debug("Auth error on API call, retrying with fresh token")
            self._invalidate_token()
            return await request_fn()

    async def _do_api_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make an API request with automatic token refresh on 401.

        Single retry: if the cached token expired (~15 min TTL),
        re-authenticates and retries once. Login itself is NOT retried.
        """
        token = await self._ensure_token()

        async def attempt():
            req_headers = kwargs.pop("headers", {})
            req_headers["Authorization"] = f"Bearer {token}"
            if "Content-Type" not in req_headers:
                req_headers["Content-Type"] = "application/json"
            return await self._client.request(method, f"{self._base_url}{path}", headers=req_headers, **kwargs)

        return await self._request_with_retry(attempt)

    def _auth_headers(self, token: str) -> dict[str, str]:
        """Build authorization headers for API requests."""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _check_errors(self, data: dict, status_code: int) -> None:
        """Raise appropriate exception from FileMaker error response.

        Checks both HTTP status codes and FileMaker-native error codes
        (which may appear in HTTP 200 response bodies).
        """
        messages = data.get("messages", [])
        if not messages:
            return

        code = int(messages[0].get("code", "0"))
        if code == 0:
            return

        message = messages[0].get("message", "Unknown error")

        # FM native error code takes precedence over HTTP status
        if code in _FM_CODE_MAP:
            raise _FM_CODE_MAP[code](message)

        # Fall back to HTTP status mapping
        exc_cls = _HTTP_ERROR_MAP.get(status_code, FMDataError)
        raise exc_cls(message) if exc_cls is not FMDataError else exc_cls(code, message)

    # --- CRUD ---

    async def get_records(
        self,
        layout: str,
        offset: int = 1,
        limit: int = 100,
        sort: list[dict[str, str]] | None = None,
    ) -> list[dict]:
        """Read records from a layout.

        Args:
            layout: FileMaker layout name (table occurrence).
            offset: 1-based starting record index.
            limit: Maximum records to return.
            sort: Optional sort criteria, e.g. [{"fieldName": "Name", "sortOrder": "ascend"}].

        Returns:
            List of record dicts with "fieldData", "recordId", "modId" keys.
        """
        params: dict[str, Any] = {"_offset": offset, "_limit": limit}
        if sort:
            params["_sort"] = sort

        logger.debug("GET records: layout={}, offset={}, limit={}", layout, offset, limit)
        response = await self._do_api_request("GET", f"/layouts/{layout}/records", params=params)
        data = response.json()
        self._check_errors(data, response.status_code)
        return data.get("response", {}).get("data", [])

    async def get_record(self, layout: str, record_id: str) -> dict:
        """Get a single record by record ID."""
        token = await self._ensure_token()
        logger.debug("GET record: layout={}, id={}", layout, record_id)
        response = await self._client.get(
            f"{self._base_url}/layouts/{layout}/records/{record_id}",
            headers=self._auth_headers(token),
        )
        data = response.json()
        self._check_errors(data, response.status_code)
        records = data.get("response", {}).get("data", [])
        if not records:
            raise FMNotFoundError(f"Record '{record_id}' not found on layout '{layout}'")
        return records[0]

    async def create_record(
        self,
        layout: str,
        field_data: dict[str, Any],
        script: str | None = None,
        script_param: str | None = None,
    ) -> dict:
        """Create a new record with the given field data.

        Returns:
            Dict with "recordId" and "modId".
        """
        token = await self._ensure_token()
        body: dict[str, Any] = {"fieldData": field_data}
        if script:
            body["script"] = script
        if script_param:
            body["script.param"] = script_param

        logger.debug("CREATE record: layout={}", layout)
        response = await self._client.post(
            f"{self._base_url}/layouts/{layout}/records",
            headers=self._auth_headers(token),
            json=body,
        )
        data = response.json()
        self._check_errors(data, response.status_code)
        return data.get("response", {})

    async def update_record(
        self,
        layout: str,
        record_id: str,
        field_data: dict[str, Any],
        mod_id: str | None = None,
    ) -> dict:
        """Update an existing record. Returns the new modId."""
        token = await self._ensure_token()
        body: dict[str, Any] = {"fieldData": field_data}
        if mod_id:
            body["modId"] = mod_id

        logger.debug("UPDATE record: layout={}, id={}", layout, record_id)
        response = await self._client.patch(
            f"{self._base_url}/layouts/{layout}/records/{record_id}",
            headers=self._auth_headers(token),
            json=body,
        )
        data = response.json()
        self._check_errors(data, response.status_code)
        return data.get("response", {})

    async def delete_record(self, layout: str, record_id: str) -> None:
        """Delete a record by ID."""
        token = await self._ensure_token()
        logger.debug("DELETE record: layout={}, id={}", layout, record_id)
        response = await self._client.delete(
            f"{self._base_url}/layouts/{layout}/records/{record_id}",
            headers=self._auth_headers(token),
        )
        if response.status_code == 204:
            return  # Some FM versions return 204 No Content
        data = response.json()
        self._check_errors(data, response.status_code)

    # --- Find ---

    async def find(
        self,
        layout: str,
        query: list[dict[str, Any]],
        sort: list[dict[str, str]] | None = None,
        offset: int = 1,
        limit: int = 100,
    ) -> list[dict]:
        """Find records matching query criteria.

        Args:
            layout: FileMaker layout name.
            query: List of field criteria dicts, e.g. [{"name": "=Alice"}].
            sort, offset, limit: Standard pagination.
        """
        token = await self._ensure_token()
        body: dict[str, Any] = {"query": query}
        if sort:
            body["sort"] = sort
        body["offset"] = offset
        body["limit"] = limit

        logger.debug("FIND records: layout={}, query={}", layout, query)
        response = await self._client.post(
            f"{self._base_url}/layouts/{layout}/_find",
            headers=self._auth_headers(token),
            json=body,
        )
        data = response.json()
        self._check_errors(data, response.status_code)
        return data.get("response", {}).get("data", [])

    # --- Scripts ---

    async def run_script(
        self,
        layout: str,
        script_name: str,
        script_param: str | None = None,
    ) -> dict:
        """Execute a FileMaker script on the given layout.

        Returns:
            Dict with "scriptResult", "scriptResult.error", etc.
        """
        token = await self._ensure_token()
        params: dict[str, str] = {}
        if script_param:
            params["script.param"] = script_param

        logger.debug("RUN script: layout={}, script={}", layout, script_name)
        response = await self._client.get(
            f"{self._base_url}/layouts/{layout}/script/{script_name}",
            headers=self._auth_headers(token),
            params=params,
        )
        data = response.json()
        self._check_errors(data, response.status_code)
        return data.get("response", {})

    # --- Metadata ---

    async def get_layouts(self) -> list[str]:
        """Get all layout names in the database."""
        token = await self._ensure_token()
        logger.debug("GET layouts")
        response = await self._client.get(
            f"{self._base_url}/layouts",
            headers=self._auth_headers(token),
        )
        data = response.json()
        self._check_errors(data, response.status_code)
        return [item["name"] for item in data.get("response", {}).get("data", [])]

    async def get_layout_metadata(self, layout: str) -> dict:
        """Get metadata for a specific layout (fields, portals, value lists)."""
        token = await self._ensure_token()
        logger.debug("GET layout metadata: {}", layout)
        response = await self._client.get(
            f"{self._base_url}/layouts/{layout}",
            headers=self._auth_headers(token),
        )
        data = response.json()
        self._check_errors(data, response.status_code)
        return data.get("response", {})

    async def get_scripts(self) -> list[str]:
        """Get all script names in the database."""
        token = await self._ensure_token()
        logger.debug("GET scripts")
        response = await self._client.get(
            f"{self._base_url}/scripts",
            headers=self._auth_headers(token),
        )
        data = response.json()
        self._check_errors(data, response.status_code)
        return [item["name"] for item in data.get("response", {}).get("data", [])]

    # --- Container ---

    async def upload_container(
        self,
        layout: str,
        record_id: str,
        field_name: str,
        file_path: str,
        repetition: int = 1,
    ) -> bool:
        """Upload a file to a container field.

        Args:
            layout: Layout name.
            record_id: Target record ID.
            field_name: Container field name.
            file_path: Path to the file to upload.
            repetition: Container field repetition number (default 1).

        Returns:
            True if upload succeeded.
        """
        token = await self._ensure_token()
        logger.debug("UPLOAD container: layout={}, record={}, field={}", layout, record_id, field_name)
        with open(file_path, "rb") as f:
            response = await self._client.post(
                f"{self._base_url}/layouts/{layout}/records/{record_id}/containers/{field_name}/{repetition}",
                headers={"Authorization": f"Bearer {token}"},
                content=f.read(),
            )
        data = response.json()
        self._check_errors(data, response.status_code)
        return True

    async def get_container_url(
        self,
        layout: str,
        record_id: str,
        field_name: str,
    ) -> str:
        """Get the download URL for a container field.

        Retrieves the record metadata and extracts the container URL.
        """
        record = await self.get_record(layout, record_id)
        url = record.get("fieldData", {}).get(field_name, "")
        if not url:
            raise FMNotFoundError(
                f"Container field '{field_name}' is empty for record '{record_id}' on layout '{layout}'"
            )
        return url

    # --- Lifecycle ---

    async def close(self) -> None:
        """Log out and release the HTTP client.

        Sends DELETE /sessions/{token} to clean up the server-side session.
        """
        if self._token:
            try:
                logger.debug("Logging out from FileMaker Data API")
                await self._client.delete(
                    f"{self._base_url}/sessions/{self._token}",
                )
            except Exception as e:
                logger.warning("Failed to log out from FileMaker Data API: {}", e)
            self._token = None

        await self._client.aclose()
        logger.debug("FMDataClient closed")
