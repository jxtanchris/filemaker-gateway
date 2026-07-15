# Part 3: FileMaker Data API 集成 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 FileMaker AI Gateway 的 5 个 stub Tool 全部升级为真实实现，通过 FileMaker Data API 读写 FM 数据，支持 OCR/Vision，并提供 FM 端脚本模板。

**Architecture:** 新建 `fm/` 模块封装 Data API REST 客户端（httpx），扩展 ToolLoader 支持依赖注入（`inspect.signature` 匹配参数名），在 main.py 装配时根据 `fm_data_api.enabled` 决定注入真实 client 还是保持 stub。

**Tech Stack:** Python 3.12+, httpx, FastAPI, Pydantic, pytest + pytest-asyncio + pytest-httpx

## Global Constraints

- `fm_data_api.enabled = false`（默认）时所有现有测试必须通过，Gateway 行为等同于 Part 2
- 所有 FM Tools 在 `fm_client=None` 时返回友好错误 `"FM Data API 未启用 (fm_data_api.enabled=false)"`
- Tool 依赖注入通过 `inspect.signature` 匹配参数名，不接受的参数自动忽略
- OCR 复用现有 Provider（LLM Vision），不引入新的 OCR 服务
- 测试使用 mock，不依赖真实 FM Server
- 遵循现有代码风格：类型标注、loguru 日志、docstring

---

### Task 1: FMDataAPIConfig 配置模型

**Files:**
- Modify: `filemaker_gateway/config/schema.py`
- Modify: `filemaker_gateway/config/defaults.py`

**Interfaces:**
- Produces: `FMDataAPIConfig` Pydantic model with fields: `host: str`, `database: str`, `username: str`, `password: str`, `protocol: str`, `verify_ssl: bool`, `enabled: bool`
- Produces: `AppConfig.fm_data_api: FMDataAPIConfig` field

- [ ] **Step 1: 在 defaults.py 添加默认值**

```python
# filemaker_gateway/config/defaults.py 追加

DEFAULT_FM_HOST = ""
DEFAULT_FM_DATABASE = ""
DEFAULT_FM_USERNAME = ""
DEFAULT_FM_PASSWORD = ""
DEFAULT_FM_PROTOCOL = "https"
DEFAULT_FM_VERIFY_SSL = True
DEFAULT_FM_ENABLED = False
```

- [ ] **Step 2: 在 schema.py 添加 FMDataAPIConfig 并扩展到 AppConfig**

```python
# filemaker_gateway/config/schema.py

from filemaker_gateway.config.defaults import (
    # ... 现有 imports 保留 ...
    DEFAULT_FM_HOST,
    DEFAULT_FM_DATABASE,
    DEFAULT_FM_USERNAME,
    DEFAULT_FM_PASSWORD,
    DEFAULT_FM_PROTOCOL,
    DEFAULT_FM_VERIFY_SSL,
    DEFAULT_FM_ENABLED,
)


class FMDataAPIConfig(BaseModel):
    """FileMaker Data API connection configuration."""

    host: str = DEFAULT_FM_HOST
    database: str = DEFAULT_FM_DATABASE
    username: str = DEFAULT_FM_USERNAME
    password: str = DEFAULT_FM_PASSWORD
    protocol: str = DEFAULT_FM_PROTOCOL
    verify_ssl: bool = DEFAULT_FM_VERIFY_SSL
    enabled: bool = DEFAULT_FM_ENABLED


class AppConfig(BaseModel):
    """Top-level application configuration."""

    gateway: GatewayConfig = GatewayConfig()
    database: DatabaseConfig = DatabaseConfig()
    fm_data_api: FMDataAPIConfig = FMDataAPIConfig()  # 新增
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
```

- [ ] **Step 3: 运行现有测试确认没有破坏**

```bash
python -m pytest tests/ -v
```
Expected: 全部 PASS（FMDataAPIConfig 有默认值，不影响现有行为）

- [ ] **Step 4: Commit**

```bash
git add filemaker_gateway/config/defaults.py filemaker_gateway/config/schema.py
git commit -m "feat: add FMDataAPIConfig model with defaults"
```

---

### Task 2: FM 错误类型模块

**Files:**
- Create: `filemaker_gateway/fm/__init__.py`
- Create: `filemaker_gateway/fm/errors.py`

**Interfaces:**
- Produces: `FMDataError(Exception)` — 基类，携带 `code: int` 和 `message: str`
- Produces: `FMAuthError(FMDataError)` — 401 认证失败
- Produces: `FMNotFoundError(FMDataError)` — 404 记录/布局不存在
- Produces: `FMValidationError(FMDataError)` — 400 字段校验错误

- [ ] **Step 1: 创建 fm 包 `__init__.py`**

```python
# filemaker_gateway/fm/__init__.py
"""FileMaker Data API client module."""

from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.fm.errors import FMAuthError, FMDataError, FMNotFoundError, FMValidationError

__all__ = [
    "FMDataClient",
    "FMDataError",
    "FMAuthError",
    "FMNotFoundError",
    "FMValidationError",
]
```

- [ ] **Step 2: 写测试（TDD）**

```python
# tests/test_fm/__init__.py  (empty)

# tests/test_fm/test_errors.py
import pytest
from filemaker_gateway.fm.errors import FMAuthError, FMDataError, FMNotFoundError, FMValidationError


def test_fm_data_error_base():
    """FMDataError should carry code and message."""
    err = FMDataError(500, "Internal Server Error")
    assert err.code == 500
    assert err.message == "Internal Server Error"
    assert str(err) == "[FMDataError 500] Internal Server Error"


def test_fm_auth_error():
    """FMAuthError should default to code 401."""
    err = FMAuthError("Invalid credentials")
    assert err.code == 401
    assert "Invalid credentials" in str(err)


def test_fm_not_found_error():
    """FMNotFoundError should default to code 404."""
    err = FMNotFoundError("Record not found")
    assert err.code == 404


def test_fm_validation_error():
    """FMValidationError should default to code 400."""
    err = FMValidationError("Field 'name' is required")
    assert err.code == 400


def test_fm_data_error_with_custom_code():
    """Should accept custom error codes."""
    err = FMDataError(999, "Custom error")
    assert err.code == 999
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest tests/test_fm/test_errors.py -v
```
Expected: FAIL — module not found

- [ ] **Step 4: 实现 errors.py**

```python
# filemaker_gateway/fm/errors.py
"""FileMaker Data API error types."""


class FMDataError(Exception):
    """Base exception for FileMaker Data API errors.

    Attributes:
        code: The FileMaker error code (e.g. 401, 404, 400).
        message: Human-readable error description.
    """

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[FMDataError {code}] {message}")


class FMAuthError(FMDataError):
    """Authentication failed (HTTP 401 / FM error 212)."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(401, message)


class FMNotFoundError(FMDataError):
    """Resource not found (HTTP 404 / FM error 101)."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(404, message)


class FMValidationError(FMDataError):
    """Field validation error (HTTP 400 / FM error 102)."""

    def __init__(self, message: str = "Validation failed") -> None:
        super().__init__(400, message)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_fm/test_errors.py -v
```
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add filemaker_gateway/fm/__init__.py filemaker_gateway/fm/errors.py tests/test_fm/
git commit -m "feat: add FMDataError exception hierarchy"
```

---

### Task 3: FMDataClient 核心客户端

**Files:**
- Create: `filemaker_gateway/fm/client.py`

**Interfaces:**
- Consumes: `FMDataError`, `FMAuthError`, `FMNotFoundError`, `FMValidationError` from `fm/errors.py`
- Consumes: `FMDataAPIConfig` from `config/schema.py`
- Produces: `FMDataClient` class with methods:
  - `__init__(self, config: FMDataAPIConfig)`
  - `async _ensure_token() -> str` — 自动登录/过期重登
  - `async get_records(layout, offset=1, limit=100, sort=None) -> list[dict]`
  - `async get_record(layout, record_id) -> dict`
  - `async create_record(layout, field_data, script=None, script_param=None) -> dict`
  - `async update_record(layout, record_id, field_data, mod_id=None) -> dict`
  - `async delete_record(layout, record_id) -> None`
  - `async find(layout, query, sort=None, offset=1, limit=100) -> list[dict]`
  - `async run_script(layout, script_name, script_param=None) -> dict`
  - `async get_layouts() -> list[str]`
  - `async get_layout_metadata(layout) -> dict`
  - `async get_scripts() -> list[str]`
  - `async upload_container(layout, record_id, field_name, file_path, repetition=1) -> dict`
  - `async get_container_url(layout, record_id, field_name) -> str`
  - `async close() -> None` — 释放 httpx client

- [ ] **Step 1: 写测试（TDD）**

```python
# tests/test_fm/test_client.py
import json
import pytest
from filemaker_gateway.config.schema import FMDataAPIConfig
from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.fm.errors import FMAuthError, FMNotFoundError


@pytest.fixture
def fm_config():
    return FMDataAPIConfig(
        host="fm.example.com",
        database="MyDB",
        username="admin",
        password="secret",
        protocol="https",
        verify_ssl=True,
        enabled=True,
    )


@pytest.fixture
def fm_base_url(fm_config):
    c = fm_config
    return f"{c.protocol}://{c.host}/fmi/data/vLatest/databases/{c.database}"


class TestFMDataClientAuth:

    @pytest.mark.asyncio
    async def test_login_on_first_request(self, httpx_mock, fm_config, fm_base_url):
        """Should call /sessions on first API request."""
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/sessions",
            json={"response": {"token": "test-token-123"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records?_offset=1&_limit=10",
            json={"response": {"data": [], "dataInfo": {"foundCount": 0, "returnedCount": 0, "totalRecordCount": 0}}},
        )

        client = FMDataClient(fm_config)
        records = await client.get_records("Contacts", limit=10)

        assert records == []
        # Verify login was called
        login_request = httpx_mock.get_requests(method="POST")[0]
        assert "/sessions" in str(login_request.url)

    @pytest.mark.asyncio
    async def test_login_failure_raises_auth_error(self, httpx_mock, fm_config, fm_base_url):
        """Should raise FMAuthError on 401 from /sessions."""
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/sessions",
            status_code=401,
        )

        client = FMDataClient(fm_config)
        with pytest.raises(FMAuthError):
            await client.get_records("Contacts")

    @pytest.mark.asyncio
    async def test_token_reuse_within_session(self, httpx_mock, fm_config, fm_base_url):
        """Should only login once for multiple requests."""
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/sessions",
            json={"response": {"token": "test-token"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/A/records?_offset=1&_limit=10",
            json={"response": {"data": [], "dataInfo": {"foundCount": 0, "returnedCount": 0, "totalRecordCount": 0}}},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/B/records?_offset=1&_limit=10",
            json={"response": {"data": [], "dataInfo": {"foundCount": 0, "returnedCount": 0, "totalRecordCount": 0}}},
        )

        client = FMDataClient(fm_config)
        await client.get_records("A", limit=10)
        await client.get_records("B", limit=10)

        # Only one login call
        login_calls = [r for r in httpx_mock.get_requests() if r.method == "POST"]
        assert len(login_calls) == 1


class TestFMDataClientCRUD:

    @pytest.mark.asyncio
    async def test_get_records(self, httpx_mock, fm_config, fm_base_url):
        """Should GET records from a layout."""
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records?_offset=1&_limit=50",
            json={
                "response": {
                    "data": [
                        {"fieldData": {"id": "1", "name": "Alice"}, "recordId": "1", "modId": "0"}
                    ],
                    "dataInfo": {"foundCount": 1, "returnedCount": 1, "totalRecordCount": 100},
                }
            },
        )

        client = FMDataClient(fm_config)
        records = await client.get_records("Contacts", limit=50)

        assert len(records) == 1
        assert records[0]["fieldData"]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_get_record_by_id(self, httpx_mock, fm_config, fm_base_url):
        """Should GET a single record by ID."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records/42",
            json={"response": {"data": [{"fieldData": {"name": "Bob"}, "recordId": "42", "modId": "1"}]}},
        )

        client = FMDataClient(fm_config)
        record = await client.get_record("Contacts", "42")

        assert record["fieldData"]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_get_record_not_found(self, httpx_mock, fm_config, fm_base_url):
        """Should raise FMNotFoundError on 404."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records/999",
            status_code=404,
            json={"messages": [{"code": "101", "message": "Record is missing"}], "response": {}},
        )

        client = FMDataClient(fm_config)
        with pytest.raises(FMNotFoundError):
            await client.get_record("Contacts", "999")

    @pytest.mark.asyncio
    async def test_create_record(self, httpx_mock, fm_config, fm_base_url):
        """Should POST to create a record."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/layouts/Contacts/records",
            json={"response": {"recordId": "99", "modId": "0"}, "messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        result = await client.create_record("Contacts", {"name": "Charlie"})

        assert result["recordId"] == "99"

        # Verify request body
        post_req = [r for r in httpx_mock.get_requests() if r.method == "POST" and "/records" in str(r.url)][0]
        body = json.loads(post_req.content)
        assert body["fieldData"]["name"] == "Charlie"

    @pytest.mark.asyncio
    async def test_update_record(self, httpx_mock, fm_config, fm_base_url):
        """Should PATCH to update a record."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="PATCH",
            url=f"{fm_base_url}/layouts/Contacts/records/42",
            json={"response": {"modId": "2"}, "messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        result = await client.update_record("Contacts", "42", {"name": "Updated"})

        assert result["modId"] == "2"

    @pytest.mark.asyncio
    async def test_delete_record(self, httpx_mock, fm_config, fm_base_url):
        """Should DELETE a record."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="DELETE",
            url=f"{fm_base_url}/layouts/Contacts/records/42",
            json={"messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        # Should not raise
        await client.delete_record("Contacts", "42")

    @pytest.mark.asyncio
    async def test_find_records(self, httpx_mock, fm_config, fm_base_url):
        """Should POST to _find endpoint."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/layouts/Contacts/_find",
            json={"response": {"data": [{"fieldData": {"name": "Alice"}, "recordId": "1", "modId": "0"}]}},
        )

        client = FMDataClient(fm_config)
        results = await client.find("Contacts", [{"name": "Alice"}])

        assert len(results) == 1
        assert results[0]["fieldData"]["name"] == "Alice"


class TestFMDataClientScripts:

    @pytest.mark.asyncio
    async def test_run_script(self, httpx_mock, fm_config, fm_base_url):
        """Should call script endpoint."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/script/Export%20PDF?script.param=invoice_123",
            json={"response": {"scriptResult": "OK"}, "messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        result = await client.run_script("Contacts", "Export PDF", "invoice_123")

        assert result["scriptResult"] == "OK"


class TestFMDataClientMetadata:

    @pytest.mark.asyncio
    async def test_get_layouts(self, httpx_mock, fm_config, fm_base_url):
        """Should return layout names."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts",
            json={"response": {"data": [{"name": "Contacts"}, {"name": "Invoices"}]}},
        )

        client = FMDataClient(fm_config)
        layouts = await client.get_layouts()

        assert layouts == ["Contacts", "Invoices"]


class TestFMDataClientContainer:

    @pytest.mark.asyncio
    async def test_upload_container(self, httpx_mock, fm_config, fm_base_url, tmp_path):
        """Should upload a file to a container field."""
        file_path = tmp_path / "test.png"
        file_path.write_text("fake-image-data")

        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/layouts/Contacts/records/1/containers/Photo/1",
            json={"messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        result = await client.upload_container("Contacts", "1", "Photo", str(file_path))

        assert result is True

    @pytest.mark.asyncio
    async def test_get_container_url(self, httpx_mock, fm_config, fm_base_url):
        """Should return a container download URL."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        # Container URL comes from metadata
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records/1",
            json={"response": {"data": [{"fieldData": {"Photo": "https://fm.example.com/stream/abc123"}, "recordId": "1", "modId": "0"}]}},
        )

        client = FMDataClient(fm_config)
        url = await client.get_container_url("Contacts", "1", "Photo")

        assert url == "https://fm.example.com/stream/abc123"


class TestFMDataClientClose:

    @pytest.mark.asyncio
    async def test_close_logs_out(self, httpx_mock, fm_config, fm_base_url):
        """Should DELETE session on close."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="DELETE",
            url=f"{fm_base_url}/sessions/tk",
            json={"messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        # Trigger login first
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/x/records?_offset=1&_limit=1",
            json={"response": {"data": [], "dataInfo": {"foundCount": 0, "returnedCount": 0, "totalRecordCount": 0}}},
        )
        await client.get_records("x", limit=1)

        await client.close()
        # Verify DELETE /sessions/tk was called
        delete_calls = [r for r in httpx_mock.get_requests() if r.method == "DELETE"]
        assert len(delete_calls) == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_fm/test_client.py -v
```
Expected: FAIL — `FMDataClient` not defined

- [ ] **Step 3: 实现 client.py**

```python
# filemaker_gateway/fm/client.py
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

# FileMaker Data API error codes → exception mapping
_ERROR_MAP: dict[int, type[FMDataError]] = {
    401: FMAuthError,
    404: FMNotFoundError,
    400: FMValidationError,
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

    def _auth_headers(self, token: str) -> dict[str, str]:
        """Build authorization headers for API requests."""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _check_errors(self, data: dict, status_code: int) -> None:
        """Raise appropriate exception from FileMaker error response."""
        messages = data.get("messages", [])
        if not messages:
            return

        code = int(messages[0].get("code", "0"))
        if code == 0:
            return

        message = messages[0].get("message", "Unknown error")
        exc_cls = _ERROR_MAP.get(status_code, FMDataError)
        raise exc_cls(message)

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
        token = await self._ensure_token()
        params: dict[str, Any] = {"_offset": offset, "_limit": limit}
        if sort:
            params["_sort"] = sort

        logger.debug("GET records: layout={}, offset={}, limit={}", layout, offset, limit)
        response = await self._client.get(
            f"{self._base_url}/layouts/{layout}/records",
            headers=self._auth_headers(token),
            params=params,
        )
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_fm/test_client.py -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/fm/client.py tests/test_fm/test_client.py
git commit -m "feat: add FMDataClient with auto token management"
```

---

### Task 4: 配置加载器集成

**Files:**
- Modify: `filemaker_gateway/config/loader.py`
- Modify: `config.yaml`

**Interfaces:**
- Consumes: `FMDataAPIConfig` from `config/schema.py`
- Produces: `load_config()` now also populates `AppConfig.fm_data_api` from YAML and env vars
- Env var mapping: `FILEMAKER_GATEWAY_FM_DATA_API_HOST`, `_DATABASE`, `_USERNAME`, `_PASSWORD`, `_PROTOCOL`, `_VERIFY_SSL`, `_ENABLED`

- [ ] **Step 1: 写测试**

```python
# tests/test_config/test_fm_config.py
import os
from filemaker_gateway.config.loader import load_config
from filemaker_gateway.config.schema import FMDataAPIConfig


def test_default_fm_config_disabled():
    """Default config should have fm_data_api disabled with empty values."""
    config = load_config("nonexistent.yaml")
    assert config.fm_data_api.enabled is False
    assert config.fm_data_api.host == ""


def test_env_var_overrides_fm_config():
    """Environment variables should override FM config fields."""
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_HOST"] = "fm.example.com"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_DATABASE"] = "TestDB"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_USERNAME"] = "admin"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_PASSWORD"] = "secret"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_PROTOCOL"] = "http"
    os.environ["FILEMAKER_GATEWAY_FM_DATA_API_ENABLED"] = "true"

    try:
        config = load_config("nonexistent.yaml")
        assert config.fm_data_api.host == "fm.example.com"
        assert config.fm_data_api.database == "TestDB"
        assert config.fm_data_api.username == "admin"
        assert config.fm_data_api.password == "secret"
        assert config.fm_data_api.protocol == "http"
        assert config.fm_data_api.enabled is True
    finally:
        # Clean up
        for key in list(os.environ):
            if key.startswith("FILEMAKER_GATEWAY_FM_DATA_API_"):
                del os.environ[key]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_config/test_fm_config.py -v
```
Expected: FAIL — `fm_data_api` not populated from env vars

- [ ] **Step 3: 修改 loader.py**

在 `load_config()` 的 YAML 解析段（`if "database" in raw:` 之后）添加：

```python
# filemaker_gateway/config/loader.py

from filemaker_gateway.config.schema import (
    AppConfig,
    DatabaseConfig,
    FMDataAPIConfig,  # 新增 import
    GatewayConfig,
    ProviderConfig,
    ToolConfig,
)

# ... 在 load_config() 函数中，"if 'database' in raw:" 块之后添加：

        if "fm_data_api" in raw:
            fm = raw["fm_data_api"]
            config.fm_data_api = FMDataAPIConfig(
                host=fm.get("host", config.fm_data_api.host),
                database=fm.get("database", config.fm_data_api.database),
                username=fm.get("username", config.fm_data_api.username),
                password=fm.get("password", config.fm_data_api.password),
                protocol=fm.get("protocol", config.fm_data_api.protocol),
                verify_ssl=fm.get("verify_ssl", config.fm_data_api.verify_ssl),
                enabled=fm.get("enabled", config.fm_data_api.enabled),
            )
```

在 `_apply_env_overrides()` 函数末尾添加：

```python
# filemaker_gateway/config/loader.py — _apply_env_overrides() 末尾追加

    # FM Data API
    _set_if_present("FM_DATA_API_HOST", config.fm_data_api, "host")
    _set_if_present("FM_DATA_API_DATABASE", config.fm_data_api, "database")
    _set_if_present("FM_DATA_API_USERNAME", config.fm_data_api, "username")
    _set_if_present("FM_DATA_API_PASSWORD", config.fm_data_api, "password")
    _set_if_present("FM_DATA_API_PROTOCOL", config.fm_data_api, "protocol")
    _set_if_present("FM_DATA_API_VERIFY_SSL", config.fm_data_api, "verify_ssl", lambda v: v.lower() == "true")
    _set_if_present("FM_DATA_API_ENABLED", config.fm_data_api, "enabled", lambda v: v.lower() == "true")
```

- [ ] **Step 4: 更新 config.yaml**

```yaml
# config.yaml — 末尾追加

fm_data_api:
  enabled: false
  host: ""
  database: ""
  username: ""
  password: ""  # 推荐用 FILEMAKER_GATEWAY_FM_DATA_API_PASSWORD 环境变量
  protocol: "https"
  verify_ssl: true
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_config/test_fm_config.py -v
```
Expected: 2 PASS

- [ ] **Step 6: 确认回归 — 所有现有测试通过**

```bash
python -m pytest tests/ -v
```
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add filemaker_gateway/config/loader.py config.yaml tests/test_config/
git commit -m "feat: add fm_data_api config loading with env var overrides"
```

---

### Task 5: ToolLoader 依赖注入

**Files:**
- Modify: `filemaker_gateway/tool/loader.py`

**Interfaces:**
- Modifies: `ToolLoader.load(self, registry: ToolRegistry, **tool_kwargs) -> list[str]`
- Uses `inspect.signature(tool_cls.__init__)` to match parameter names
- Only passes kwargs that a Tool's `__init__` accepts; others silently ignored

- [ ] **Step 1: 在现有测试中验证新接口**

更新 `tests/test_tool/test_registry.py` 的 `test_tool_auto_discovery`：

```python
# tests/test_tool/test_registry.py — 追加测试

import inspect
from filemaker_gateway.tool.stubs.echo import EchoTool


def test_loader_with_kwargs_injection():
    """ToolLoader.load() should pass matching kwargs to Tool constructors."""
    registry = ToolRegistry()
    loader = ToolLoader()

    # EchoTool.__init__ only takes self — extra kwargs should be ignored
    names = loader.load(registry, fm_client="fake_client", provider="fake_provider")
    assert "echo" in names

    # EchoTool should still work normally
    tool = registry.get("echo")
    assert tool is not None


def test_loader_ignores_unmatched_kwargs():
    """Should not fail when passing kwargs that no tool accepts."""
    registry = ToolRegistry()
    loader = ToolLoader()
    # All current tools only accept self — these kwargs should be silently ignored
    names = loader.load(registry, unknown_kwarg=42, another_one="test")
    assert len(names) >= 6
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_tool/test_registry.py::test_loader_with_kwargs_injection -v
```
Expected: FAIL — `load()` got unexpected keyword argument

- [ ] **Step 3: 修改 ToolLoader.load()**

```python
# filemaker_gateway/tool/loader.py

import inspect  # 添加到文件顶部 imports

# ...

    def load(self, registry: ToolRegistry, **tool_kwargs: Any) -> list[str]:
        """Discover and register all tools.

        Args:
            registry: The ToolRegistry to register tools into.
            **tool_kwargs: Optional dependencies to inject into Tool constructors.
                Each kwarg is only passed to tools whose __init__ accepts it
                (matched by parameter name via inspect.signature).

        Returns:
            List of registered tool names.
        """
        tool_classes = self.discover()

        # Also load from entry points (plugin system)
        self._load_entry_points(registry)

        for tool_cls in tool_classes:
            try:
                # Match constructor parameters to available kwargs
                sig = inspect.signature(tool_cls.__init__)
                matching_kwargs = {
                    k: v for k, v in tool_kwargs.items()
                    if k in sig.parameters
                }
                instance = tool_cls(**matching_kwargs)
                registry.register(instance)
                logger.info("Loaded tool: {}", instance.name)
            except Exception as e:
                logger.warning("Failed to instantiate tool '{}': {}", tool_cls.__name__, e)

        return registry.tool_names
```

- [ ] **Step 4: 运行新测试确认通过**

```bash
python -m pytest tests/test_tool/test_registry.py -v
```
Expected: 全部 PASS（包括新测试）

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/tool/loader.py tests/test_tool/test_registry.py
git commit -m "feat: add dependency injection to ToolLoader via inspect.signature"
```

---

### Task 6: FileMakerQueryTool 去 stub

**Files:**
- Modify: `filemaker_gateway/tool/filemaker/query.py`
- Create: `tests/test_tool/test_filemaker_tools.py`

**Interfaces:**
- Consumes: `FMDataClient` from `fm/client.py`（可选，None 时返回降级错误）
- Modifies: `FileMakerQueryTool.__init__(self, fm_client=None)` — 接受 DI
- Modifies: `FileMakerQueryTool.execute()` — select → `self._fm.get_records()`, find → `self._fm.find()`

- [ ] **Step 1: 写测试**

```python
# tests/test_tool/test_filemaker_tools.py
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.tool.filemaker.query import FileMakerQueryTool
from filemaker_gateway.tool.filemaker.record import FileMakerRecordTool
from filemaker_gateway.tool.filemaker.script import FileMakerScriptTool
from filemaker_gateway.tool.filemaker.layout import FileMakerLayoutTool


# --- Query Tool ---

class TestFileMakerQueryTool:

    @pytest.fixture
    def mock_fm(self):
        client = MagicMock(spec=FMDataClient)
        client.get_records = AsyncMock()
        client.find = AsyncMock()
        return client

    @pytest.fixture
    def tool(self, mock_fm):
        return FileMakerQueryTool(fm_client=mock_fm)

    @pytest.mark.asyncio
    async def test_select_returns_records(self, tool, mock_fm):
        """Should call get_records and return JSON-serialized results."""
        mock_fm.get_records.return_value = [
            {"fieldData": {"name": "Alice"}, "recordId": "1", "modId": "0"}
        ]
        result = await tool.execute(action="select", layout="Contacts", limit=10)
        parsed = json.loads(str(result))
        assert parsed[0]["fieldData"]["name"] == "Alice"
        mock_fm.get_records.assert_called_once_with("Contacts", limit=10)

    @pytest.mark.asyncio
    async def test_find_returns_matching_records(self, tool, mock_fm):
        """Should call find with parsed query."""
        mock_fm.find.return_value = [
            {"fieldData": {"name": "Bob"}, "recordId": "2", "modId": "0"}
        ]
        result = await tool.execute(action="find", layout="Contacts", query='[{"name":"Bob"}]')
        parsed = json.loads(str(result))
        assert parsed[0]["fieldData"]["name"] == "Bob"
        mock_fm.find.assert_called_once_with("Contacts", [{"name": "Bob"}], limit=100)

    @pytest.mark.asyncio
    async def test_select_without_layout_returns_error(self, tool):
        """Should return error if layout is missing for select."""
        result = await tool.execute(action="select")
        assert "layout is required" in str(result).lower()

    @pytest.mark.asyncio
    async def test_stub_when_no_fm_client(self):
        """Should return friendly error when fm_data_api is disabled."""
        tool = FileMakerQueryTool()  # No fm_client
        result = await tool.execute(action="select", layout="Contacts")
        assert "FM Data API 未启用" in str(result)

    @pytest.mark.asyncio
    async def test_fm_client_error_propagates(self, tool, mock_fm):
        """Should return error result when Data API fails."""
        mock_fm.get_records.side_effect = Exception("Connection refused")
        result = await tool.execute(action="select", layout="Contacts")
        assert "Connection refused" in str(result)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_tool/test_filemaker_tools.py::TestFileMakerQueryTool -v
```
Expected: FAIL — stub 返回 placeholder 而非真实数据

- [ ] **Step 3: 实现 query.py**

```python
# filemaker_gateway/tool/filemaker/query.py
"""FileMakerQueryTool: SELECT, ExecuteSQL, and Find operations."""

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
                    return ToolResult.error("layout is required for 'find' action")
                criteria = json.loads(query) if query else []
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_tool/test_filemaker_tools.py::TestFileMakerQueryTool -v
```
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/tool/filemaker/query.py tests/test_tool/test_filemaker_tools.py
git commit -m "feat: replace FileMakerQueryTool stub with real Data API implementation"
```

---

### Task 7: FileMakerRecordTool 去 stub

**Files:**
- Modify: `filemaker_gateway/tool/filemaker/record.py`
- Modify: `tests/test_tool/test_filemaker_tools.py` (追加测试)

- [ ] **Step 1: 追加测试到已有测试文件**

```python
# tests/test_tool/test_filemaker_tools.py 追加

class TestFileMakerRecordTool:

    @pytest.fixture
    def mock_fm(self):
        client = MagicMock(spec=FMDataClient)
        client.create_record = AsyncMock()
        client.update_record = AsyncMock()
        client.delete_record = AsyncMock()
        return client

    @pytest.fixture
    def tool(self, mock_fm):
        return FileMakerRecordTool(fm_client=mock_fm)

    @pytest.mark.asyncio
    async def test_create_record(self, tool, mock_fm):
        """Should create a record and return the new record ID."""
        mock_fm.create_record.return_value = {"recordId": "99", "modId": "0"}
        result = await tool.execute(
            action="create", layout="Contacts", field_data={"name": "Alice"}
        )
        parsed = json.loads(str(result))
        assert parsed["recordId"] == "99"
        mock_fm.create_record.assert_called_once_with("Contacts", {"name": "Alice"})

    @pytest.mark.asyncio
    async def test_update_record(self, tool, mock_fm):
        """Should update a record and return the new modId."""
        mock_fm.update_record.return_value = {"modId": "2"}
        result = await tool.execute(
            action="update", layout="Contacts", record_id="1", field_data={"name": "Bob"}
        )
        parsed = json.loads(str(result))
        assert parsed["modId"] == "2"
        mock_fm.update_record.assert_called_once_with("Contacts", "1", {"name": "Bob"}, None)

    @pytest.mark.asyncio
    async def test_delete_record(self, tool, mock_fm):
        """Should delete a record."""
        mock_fm.delete_record.return_value = None
        result = await tool.execute(action="delete", layout="Contacts", record_id="1")
        assert "deleted" in str(result).lower()
        mock_fm.delete_record.assert_called_once_with("Contacts", "1")

    @pytest.mark.asyncio
    async def test_update_without_record_id(self, tool):
        """Should return error for update without record_id."""
        result = await tool.execute(action="update", layout="Contacts", field_data={"name": "X"})
        assert "record_id is required" in str(result).lower()

    @pytest.mark.asyncio
    async def test_delete_without_record_id(self, tool):
        """Should return error for delete without record_id."""
        result = await tool.execute(action="delete", layout="Contacts")
        assert "record_id is required" in str(result).lower()

    @pytest.mark.asyncio
    async def test_stub_when_no_fm_client(self):
        """Should return friendly error when fm_data_api is disabled."""
        tool = FileMakerRecordTool()
        result = await tool.execute(action="create", layout="Contacts", field_data={"x": "y"})
        assert "FM Data API 未启用" in str(result)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_tool/test_filemaker_tools.py::TestFileMakerRecordTool -v
```
Expected: FAIL

- [ ] **Step 3: 实现 record.py**

```python
# filemaker_gateway/tool/filemaker/record.py
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
                result = await self._fm.update_record(layout, record_id, field_data or {})
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_tool/test_filemaker_tools.py::TestFileMakerRecordTool -v
```
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/tool/filemaker/record.py tests/test_tool/test_filemaker_tools.py
git commit -m "feat: replace FileMakerRecordTool stub with real Data API implementation"
```

---

### Task 8: FileMakerScriptTool 去 stub

**Files:**
- Modify: `filemaker_gateway/tool/filemaker/script.py`
- Modify: `tests/test_tool/test_filemaker_tools.py` (追加测试)

- [ ] **Step 1: 追加测试**

```python
# tests/test_tool/test_filemaker_tools.py 追加

class TestFileMakerScriptTool:

    @pytest.fixture
    def mock_fm(self):
        client = MagicMock(spec=FMDataClient)
        client.run_script = AsyncMock()
        return client

    @pytest.fixture
    def tool(self, mock_fm):
        return FileMakerScriptTool(fm_client=mock_fm)

    @pytest.mark.asyncio
    async def test_run_script(self, tool, mock_fm):
        """Should execute a FileMaker script and return its result."""
        mock_fm.run_script.return_value = {"scriptResult": "PDF exported successfully"}
        result = await tool.execute(script_name="Export PDF", parameter="invoice_123")
        assert "PDF exported successfully" in str(result)

    @pytest.mark.asyncio
    async def test_run_script_without_parameter(self, tool, mock_fm):
        """Should run script without parameter."""
        mock_fm.run_script.return_value = {"scriptResult": "OK"}
        result = await tool.execute(script_name="Refresh Cache")
        assert "OK" in str(result)

    @pytest.mark.asyncio
    async def test_run_script_error(self, tool, mock_fm):
        """Should return error if script fails."""
        mock_fm.run_script.return_value = {"scriptResult.error": "3", "scriptResult": "Script not found"}
        result = await tool.execute(script_name="NonExistent")
        assert "error" in str(result).lower()

    @pytest.mark.asyncio
    async def test_stub_when_no_fm_client(self):
        """Should return friendly error when fm_data_api is disabled."""
        tool = FileMakerScriptTool()
        result = await tool.execute(script_name="Test Script")
        assert "FM Data API 未启用" in str(result)
```

- [ ] **Step 2: 运行测试确认失败 → 实现 → 确认通过**

```bash
python -m pytest tests/test_tool/test_filemaker_tools.py::TestFileMakerScriptTool -v
```

- [ ] **Step 3: 实现 script.py**

```python
# filemaker_gateway/tool/filemaker/script.py
"""FileMakerScriptTool: Execute FileMaker scripts."""

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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_tool/test_filemaker_tools.py::TestFileMakerScriptTool -v
```
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/tool/filemaker/script.py tests/test_tool/test_filemaker_tools.py
git commit -m "feat: replace FileMakerScriptTool stub with real Data API implementation"
```

---

### Task 9: FileMakerLayoutTool 去 stub

**Files:**
- Modify: `filemaker_gateway/tool/filemaker/layout.py`
- Modify: `tests/test_tool/test_filemaker_tools.py` (追加测试)

- [ ] **Step 1: 追加测试**

```python
# tests/test_tool/test_filemaker_tools.py 追加

class TestFileMakerLayoutTool:

    @pytest.fixture
    def mock_fm(self):
        client = MagicMock(spec=FMDataClient)
        client.get_layouts = AsyncMock()
        client.get_layout_metadata = AsyncMock()
        return client

    @pytest.fixture
    def tool(self, mock_fm):
        return FileMakerLayoutTool(fm_client=mock_fm)

    @pytest.mark.asyncio
    async def test_list_layouts(self, tool, mock_fm):
        """Should return list of layout names."""
        mock_fm.get_layouts.return_value = ["Contacts", "Invoices", "Dashboard"]
        result = await tool.execute(action="list_layouts")
        assert "Contacts" in str(result)
        assert "Invoices" in str(result)

    @pytest.mark.asyncio
    async def test_open_layout_returns_info(self, tool, mock_fm):
        """Should return layout metadata for a named layout."""
        mock_fm.get_layout_metadata.return_value = {
            "fieldMetaData": [{"name": "id", "type": "normal"}]
        }
        result = await tool.execute(action="open_layout", layout_name="Contacts")
        assert "fieldMetaData" in str(result) or "id" in str(result)

    @pytest.mark.asyncio
    async def test_open_layout_without_name(self, tool):
        """Should return error without layout_name."""
        result = await tool.execute(action="open_layout")
        assert "layout_name is required" in str(result).lower()

    @pytest.mark.asyncio
    async def test_next_previous_record_not_supported(self, tool):
        """Should return message about server-side limitation."""
        result = await tool.execute(action="next_record")
        assert "cannot" in str(result).lower() or "not supported" in str(result).lower()

    @pytest.mark.asyncio
    async def test_stub_when_no_fm_client(self):
        """Should return friendly error when fm_data_api is disabled."""
        tool = FileMakerLayoutTool()
        result = await tool.execute(action="list_layouts")
        assert "FM Data API 未启用" in str(result)
```

- [ ] **Step 2: 运行测试确认失败 → 实现 → 确认通过**

```bash
python -m pytest tests/test_tool/test_filemaker_tools.py::TestFileMakerLayoutTool -v
```

- [ ] **Step 3: 实现 layout.py**

```python
# filemaker_gateway/tool/filemaker/layout.py
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_tool/test_filemaker_tools.py::TestFileMakerLayoutTool -v
```
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/tool/filemaker/layout.py tests/test_tool/test_filemaker_tools.py
git commit -m "feat: replace FileMakerLayoutTool stub with real Data API implementation"
```

---

### Task 10: AgentLoop Vision 支持

**Files:**
- Modify: `filemaker_gateway/agent/loop.py`
- Modify: `tests/test_agent/test_runner.py` (or create `tests/test_agent/test_loop.py`)

**Interfaces:**
- Modifies: `AgentLoop._build()` — 当 `ctx.media` 非空时，构建 vision-compatible `content` 列表格式
- Media URL 以 `data:image` 开头时作为 `image_url` 嵌入；其他 URL 作为文本引用

- [ ] **Step 1: 写测试**

```python
# tests/test_agent/test_loop.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from filemaker_gateway.agent.loop import AgentLoop, TurnContext
from filemaker_gateway.agent.runner import AgentRunner
from filemaker_gateway.session.manager import SessionManager
from filemaker_gateway.tool.registry import ToolRegistry
from filemaker_gateway.tool.stubs.echo import EchoTool


class TestAgentLoopVision:

    @pytest.fixture
    def mock_runner(self):
        runner = MagicMock(spec=AgentRunner)
        runner.run = AsyncMock()
        return runner

    @pytest.fixture
    def mock_provider(self):
        from filemaker_gateway.provider.base import LLMProvider
        return MagicMock(spec=LLMProvider)

    @pytest.fixture
    def tool_registry(self):
        r = ToolRegistry()
        r.register(EchoTool())
        return r

    @pytest.fixture
    def mock_session_manager(self):
        sm = MagicMock(spec=SessionManager)
        sm.get_or_create_session = AsyncMock()
        sm.get_history_for_context = AsyncMock(return_value=[])
        sm.save_turn_messages = AsyncMock()
        return sm

    @pytest.mark.asyncio
    async def test_build_without_media_uses_string_content(
        self, mock_session_manager, tool_registry, mock_provider, mock_runner
    ):
        """Without media, _build should create a plain string content message."""
        loop = AgentLoop(
            session_manager=mock_session_manager,
            tool_registry=tool_registry,
            provider=mock_provider,
            runner=mock_runner,
            system_prompt="Test prompt",
        )
        ctx = TurnContext(session_key="s1", user_message="Hello", media=[])
        from sqlalchemy.ext.asyncio import AsyncSession
        mock_db = MagicMock(spec=AsyncSession)

        await loop._resolve(ctx, mock_db)
        await loop._build(ctx)

        user_msg = ctx.initial_messages[-1]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], str)
        assert user_msg["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_build_with_image_media_uses_vision_format(
        self, mock_session_manager, tool_registry, mock_provider, mock_runner
    ):
        """With base64 image media, _build should use vision content list."""
        loop = AgentLoop(
            session_manager=mock_session_manager,
            tool_registry=tool_registry,
            provider=mock_provider,
            runner=mock_runner,
            system_prompt="Test prompt",
        )
        ctx = TurnContext(
            session_key="s1",
            user_message="What's in this image?",
            media=["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="],
        )
        from sqlalchemy.ext.asyncio import AsyncSession
        mock_db = MagicMock(spec=AsyncSession)

        await loop._resolve(ctx, mock_db)
        await loop._build(ctx)

        user_msg = ctx.initial_messages[-1]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], list)
        # First part should be the text
        assert user_msg["content"][0] == {"type": "text", "text": "What's in this image?"}
        # Second part should be the image
        assert user_msg["content"][1]["type"] == "image_url"
        assert "base64" in user_msg["content"][1]["image_url"]["url"]

    @pytest.mark.asyncio
    async def test_build_with_non_image_media_uses_text_format(
        self, mock_session_manager, tool_registry, mock_provider, mock_runner
    ):
        """Non-data-URI media URLs should be appended as text references."""
        loop = AgentLoop(
            session_manager=mock_session_manager,
            tool_registry=tool_registry,
            provider=mock_provider,
            runner=mock_runner,
            system_prompt="Test prompt",
        )
        ctx = TurnContext(
            session_key="s1",
            user_message="Analyze this",
            media=["https://example.com/document.pdf"],
        )
        from sqlalchemy.ext.asyncio import AsyncSession
        mock_db = MagicMock(spec=AsyncSession)

        await loop._resolve(ctx, mock_db)
        await loop._build(ctx)

        user_msg = ctx.initial_messages[-1]
        # Non-image URLs are appended as text markers (backward compatible)
        assert "https://example.com/document.pdf" in str(user_msg["content"])

    @pytest.mark.asyncio
    async def test_build_with_mixed_media(
        self, mock_session_manager, tool_registry, mock_provider, mock_runner
    ):
        """Mix of image and non-image media should use vision format for images."""
        loop = AgentLoop(
            session_manager=mock_session_manager,
            tool_registry=tool_registry,
            provider=mock_provider,
            runner=mock_runner,
            system_prompt="Test prompt",
        )
        ctx = TurnContext(
            session_key="s1",
            user_message="Check these",
            media=[
                "data:image/jpeg;base64,/9j/4AAQ==",
                "https://example.com/file.pdf",
            ],
        )
        from sqlalchemy.ext.asyncio import AsyncSession
        mock_db = MagicMock(spec=AsyncSession)

        await loop._resolve(ctx, mock_db)
        await loop._build(ctx)

        user_msg = ctx.initial_messages[-1]
        # Should use vision list format because at least one image is present
        assert isinstance(user_msg["content"], list)
        # First: text
        assert user_msg["content"][0]["type"] == "text"
        # Second: image
        assert user_msg["content"][1]["type"] == "image_url"
        # Third: text reference for non-image URL
        assert user_msg["content"][2]["type"] == "text"
        assert "file.pdf" in user_msg["content"][2]["text"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_agent/test_loop.py -v
```
Expected: FAIL — vision format not applied

- [ ] **Step 3: 修改 AgentLoop._build()**

```python
# filemaker_gateway/agent/loop.py — 替换 _build() 方法中的当前用户消息构建逻辑

    async def _build(self, ctx: TurnContext) -> TurnState:
        """Build the initial_messages list for the runner."""
        messages: list[dict[str, Any]] = []

        # System prompt
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})

        # History (previous turns)
        messages.extend(ctx.history)

        # Current user message — support vision format when images are attached
        image_media = [m for m in ctx.media if m.startswith("data:image")]
        other_media = [m for m in ctx.media if not m.startswith("data:image")]

        if image_media:
            # Build vision-compatible content list
            content: list[dict[str, Any]] = [
                {"type": "text", "text": ctx.user_message}
            ]
            for url in image_media:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })
            # Non-image URLs are included as text references
            if other_media:
                refs = "\n".join(f"[media: {url}]" for url in other_media)
                content.append({"type": "text", "text": refs})

            messages.append({"role": "user", "content": content})
        else:
            # Plain text format (backward compatible)
            user_content = ctx.user_message
            if other_media:
                media_str = "\n".join(f"[media: {url}]" for url in other_media)
                user_content = f"{media_str}\n{user_content}"
            messages.append({"role": "user", "content": user_content})

        ctx.initial_messages = messages
        logger.debug("Built {} initial messages", len(messages))
        return TurnState.RUN
```

- [ ] **Step 4: 运行全部测试确认通过**

```bash
python -m pytest tests/test_agent/ -v
```
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/agent/loop.py tests/test_agent/test_loop.py
git commit -m "feat: add vision media support to AgentLoop._build()"
```

---

### Task 11: OCRTool 去 stub（LLM Vision）

**Files:**
- Modify: `filemaker_gateway/tool/ocr.py`
- Create: `tests/test_tool/test_ocr.py`

**Interfaces:**
- Consumes: `LLMProvider` from `provider/base.py`（可选，None 时返回降级错误）
- Modifies: `OCRTool.__init__(self, provider=None)` — 接受 DI
- Modifies: `OCRTool.execute()` — 构造 vision prompt → `self._provider.chat()` → 返回 OCR 结果

- [ ] **Step 1: 写测试**

```python
# tests/test_tool/test_ocr.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from filemaker_gateway.provider.base import LLMProvider, LLMResponse
from filemaker_gateway.tool.ocr import OCRTool


class TestOCRTool:

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock(spec=LLMProvider)
        provider.chat = AsyncMock()
        provider.get_default_model.return_value = "test-model"
        return provider

    @pytest.fixture
    def tool(self, mock_provider):
        return OCRTool(provider=mock_provider)

    @pytest.mark.asyncio
    async def test_glm_ocr_calls_provider_with_vision(self, tool, mock_provider):
        """Should send image to provider with OCR prompt."""
        mock_provider.chat.return_value = LLMResponse(
            content="这是一张发票，金额为 100 元",
            finish_reason="stop",
        )

        result = await tool.execute(
            image_url="data:image/png;base64,abc123",
            ocr_type="glm",
        )

        assert "发票" in str(result)
        # Verify provider was called with vision format
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        # Last message should contain the image in vision format
        last_content = messages[-1]["content"]
        assert isinstance(last_content, list)
        assert last_content[1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_invoice_ocr_uses_structured_prompt(self, tool, mock_provider):
        """Should use invoice-specific prompt for structured extraction."""
        mock_provider.chat.return_value = LLMResponse(
            content='{"invoice_number": "INV-001", "date": "2024-01-15", "amount": 1500.00, "seller": "ABC Corp"}',
            finish_reason="stop",
        )

        result = await tool.execute(
            image_url="data:image/png;base64,def456",
            ocr_type="invoice",
        )

        assert "INV-001" in str(result)
        # Verify invoice-specific prompt is in the system message
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        system_content = messages[0]["content"]
        assert "发票" in system_content or "invoice" in system_content.lower()

    @pytest.mark.asyncio
    async def test_pdf_ocr_returns_error_for_multi_page(self, tool):
        """Should return error for PDF — multi-page not supported without splitting."""
        result = await tool.execute(
            image_url="https://example.com/document.pdf",
            ocr_type="pdf",
        )
        assert "pdf" in str(result).lower()

    @pytest.mark.asyncio
    async def test_no_provider_returns_error(self):
        """Should return friendly error when provider is not injected."""
        tool = OCRTool()
        result = await tool.execute(image_url="data:image/png;base64,test")
        assert "未启用" in str(result) or "not available" in str(result).lower()

    @pytest.mark.asyncio
    async def test_provider_error_propagates(self, tool, mock_provider):
        """Should return error if provider call fails."""
        mock_provider.chat.side_effect = Exception("API rate limit")
        result = await tool.execute(image_url="data:image/png;base64,test")
        assert "rate limit" in str(result).lower()

    @pytest.mark.asyncio
    async def test_non_data_uri_image_passed_as_is(self, tool, mock_provider):
        """Should accept regular URLs as image_url."""
        mock_provider.chat.return_value = LLMResponse(
            content="Image text content",
            finish_reason="stop",
        )

        result = await tool.execute(
            image_url="https://example.com/photo.jpg",
            ocr_type="glm",
        )

        assert "Image text content" in str(result)
        # URL should be passed through
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        last_content = messages[-1]["content"]
        assert "photo.jpg" in str(last_content)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_tool/test_ocr.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 ocr.py**

```python
# filemaker_gateway/tool/ocr.py
"""OCRTool: Extract text from images using LLM Vision."""

from filemaker_gateway.provider.base import LLMProvider
from filemaker_gateway.tool.base import Tool, ToolResult

# Prompt templates for different OCR modes
_GLM_PROMPT = "请识别并提取这张图片中的所有文字。保留原始格式和排版。"
_INVOICE_PROMPT = (
    "请从这张发票图片中提取以下结构化信息，以 JSON 格式返回：\n"
    '{\n'
    '  "invoice_number": "发票号",\n'
    '  "date": "开票日期",\n'
    '  "amount": "金额（数字）",\n'
    '  "seller": "销售方名称",\n'
    '  "buyer": "购买方名称",\n'
    '  "items": [{"name": "商品名", "quantity": 数量, "price": 单价}]\n'
    '}\n'
    "只返回 JSON，不要包含其他内容。"
)

_PDF_NOTE = (
    "PDF OCR 需要先将 PDF 拆分为单页图片。请使用外部工具（如 poppler、PyMuPDF）"
    "将 PDF 转换为图片后，再对每页调用 ocr_type='glm'。"
)


class OCRTool(Tool):
    """Extract text from images using LLM Vision (via the configured Provider)."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider
        self._model = "deepseek-chat"

    @property
    def name(self) -> str:
        return "ocr"

    @property
    def description(self) -> str:
        return (
            "Extract text from images and documents using AI Vision. "
            "Use 'glm' for general image OCR (supports Chinese and English), "
            "use 'invoice' for structured invoice field extraction "
            "(invoice number, date, amount, seller, buyer), "
            "use 'pdf' for multi-page PDF text extraction "
            "(requires splitting PDF into single-page images first). "
            "Provide the image as a data:image/...;base64,... URL or a regular image URL."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": "string",
                    "description": "The image to OCR. Use data:image/...;base64,... format for local images, or a URL for remote images.",
                },
                "ocr_type": {
                    "type": "string",
                    "enum": ["glm", "invoice", "pdf"],
                    "description": "OCR mode: 'glm' for general text, 'invoice' for structured invoice data, 'pdf' for PDF documents.",
                },
            },
            "required": ["image_url"],
        }

    @property
    def read_only(self) -> bool:
        return True

    async def execute(
        self,
        image_url: str,
        ocr_type: str = "glm",
    ) -> ToolResult | str:
        if self._provider is None:
            return ToolResult.error(
                "OCR 未启用 (Provider 未注入，请检查配置)"
            )

        if ocr_type == "pdf":
            return ToolResult.error(_PDF_NOTE)

        # Build OCR prompt
        if ocr_type == "invoice":
            user_text = _INVOICE_PROMPT
        else:
            user_text = _GLM_PROMPT

        # Build vision-format content
        content: list[dict] = [
            {"type": "text", "text": user_text},
        ]

        # Handle both data URIs and regular URLs
        if image_url.startswith("data:image"):
            content.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })
        else:
            # Regular URL — the model may or may not support fetching it
            content.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })

        try:
            response = await self._provider.chat(
                messages=[
                    {"role": "system", "content": "你是一个精确的 OCR 和文档识别助手。"},
                    {"role": "user", "content": content},
                ],
                model=self._model,
                temperature=0.1,  # Low temperature for accuracy
                max_tokens=4096,
            )

            if response.finish_reason == "error":
                return ToolResult.error(f"OCR 识别失败: {response.content}")

            return ToolResult(response.content or "")

        except Exception as e:
            return ToolResult.error(f"OCR 处理失败: {e}")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_tool/test_ocr.py -v
```
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/tool/ocr.py tests/test_tool/test_ocr.py
git commit -m "feat: replace OCRTool stub with LLM Vision implementation"
```

---

### Task 12: main.py 装配 FMDataClient + Provider DI

**Files:**
- Modify: `filemaker_gateway/main.py`

**Interfaces:**
- Consumes: `FMDataClient` from `fm/client.py`, `FMDataAPIConfig` from `config/schema.py`
- Modifies: `create_app()` lifespan — 当 `config.fm_data_api.enabled` 时创建 FMDataClient 并注入到 Tools 和 shutdown 逻辑

- [ ] **Step 1: 修改 main.py**

```python
# filemaker_gateway/main.py

"""FastAPI application factory and startup wiring."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from filemaker_gateway.api.deps import init_dependencies
from filemaker_gateway.api.middleware import AuthMiddleware, RequestLoggingMiddleware
from filemaker_gateway.api.router import create_router
from filemaker_gateway.config.schema import AppConfig
from filemaker_gateway.fm.client import FMDataClient  # 新增
from filemaker_gateway.provider.factory import make_provider
from filemaker_gateway.session.database import close_database, create_tables, init_database
from filemaker_gateway.tool.loader import ToolLoader
from filemaker_gateway.tool.registry import ToolRegistry


def create_app(config: AppConfig) -> FastAPI:
    """Create and wire the FastAPI application.

    Assembly order:
    1. Database → 2. Tools → 3. Provider → 4. AgentLoop → 5. API
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup and shutdown lifecycle."""
        # --- Startup ---
        logger.info("Starting FileMaker AI Gateway v0.1.0")

        # 1. Database
        init_database(config.database.url)
        await create_tables()
        logger.info("Database initialized: {}", config.database.url)

        # 2. Provider
        provider = make_provider(config.gateway.provider)
        logger.info("Provider ready: {}", config.gateway.provider.name)

        # 3. FM Data API client (optional)
        fm_client: FMDataClient | None = None
        if config.fm_data_api.enabled:
            fm_client = FMDataClient(config.fm_data_api)
            logger.info(
                "FM Data API client created: {}://{}/{}",
                config.fm_data_api.protocol,
                config.fm_data_api.host,
                config.fm_data_api.database,
            )
        else:
            logger.info("FM Data API disabled — FM Tools will return stub errors")

        # 4. Tools (with dependency injection)
        tool_registry = ToolRegistry()
        loader = ToolLoader()
        tool_kwargs: dict = {}
        if fm_client is not None:
            tool_kwargs["fm_client"] = fm_client
        tool_kwargs["provider"] = provider  # for OCRTool
        names = loader.load(tool_registry, **tool_kwargs)
        logger.info("Loaded {} tools: {}", len(names), names)

        # 5. Wire dependencies for API
        init_dependencies(config, tool_registry, provider)
        logger.info("Dependencies wired")

        yield

        # --- Shutdown ---
        if fm_client is not None:
            await fm_client.close()
            logger.info("FM Data API client closed")
        await close_database()
        logger.info("Gateway shut down")

    app = FastAPI(
        title="FileMaker AI Gateway",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(RequestLoggingMiddleware)
    if config.gateway.api_key:
        app.add_middleware(AuthMiddleware, api_key=config.gateway.api_key)

    # Routes
    router = create_router(config)
    app.include_router(router)

    return app
```

- [ ] **Step 2: 确认回归 — 所有现有测试通过**

```bash
python -m pytest tests/ -v
```
Expected: 全部 PASS（`fm_data_api.enabled=false` 时 FM Tools 返回 stub 错误，其他不变）

- [ ] **Step 3: Commit**

```bash
git add filemaker_gateway/main.py
git commit -m "feat: wire FMDataClient and provider DI into app startup"
```

---

### Task 13: FileMaker 脚本模板

**Files:**
- Create: `fm_scripts/AI_Chat.txt`
- Create: `fm_scripts/AI_NL_Query.txt`
- Create: `fm_scripts/AI_OCR_Invoice.txt`
- Create: `fm_scripts/README.md`

- [ ] **Step 1: 创建 AI_Chat.txt**

```
FileMaker Script: AI Chat
========================
用途: 基础 AI 对话 — 用户输入文本，AI 回复，结果写回字段

前提条件:
  1. Gateway 运行在 http://127.0.0.1:8080
  2. 布局上有以下字段:
     - UserInput (Text) — 用户输入
     - AIResponse (Text) — AI 回复
     - GatewayURL (Text, 计算字段) = "http://127.0.0.1:8080/chat"

脚本步骤:
  1. Set Variable [$input; Value: MyTable::UserInput]
  2. Set Variable [$payload; Value: JSONSetElement("{}";
       ["session"; Get(AccountName); JSONString];
       ["message"; $input; JSONString]
     )]
  3. Set Variable [$api_key; Value: "filemaker-secret-key-change-me"]
  4. Insert From URL [
       Select; With dialog: Off; Target: $result;
       $payload;
       cURL options: "--header \"X-API-Key: " & $api_key & "\" --header \"Content-Type: application/json\"";
       MyTable::GatewayURL
     ]
  5. Set Variable [$answer; Value: JSONGetElement($result; "answer")]
  6. Set Field [MyTable::AIResponse; $answer]
  7. Exit Script [Text Result: $answer]

注意:
  - Insert From URL 超时默认 60s，复杂查询可能不足
  - $result 是完整的 JSON 响应: {"answer":"...", "session":"...", "tool_calls":[...], "stop_reason":"..."}
  - session 参数用 Get(AccountName) 确保每个用户独立会话
```

- [ ] **Step 2: 创建 AI_NL_Query.txt**

```
FileMaker Script: AI Natural Language Query
============================================
用途: 用户用自然语言查询数据库，AI 自动执行 filemaker_query tool 并返回结果

前提条件:
  1. Gateway 运行并已启用 fm_data_api
  2. 布局上字段:
     - QueryInput (Text) — 用户的自然语言查询
     - QueryResult (Text) — AI 整理后的查询结果

脚本步骤:
  1. Set Variable [$input; Value: MyTable::QueryInput]
  2. Set Variable [$payload; Value: JSONSetElement("{}";
       ["session"; "nl_query_" & Get(AccountName); JSONString];
       ["message"; "查询数据库：" & $input; JSONString]
     )]
  3. Set Variable [$api_key; Value: "filemaker-secret-key-change-me"]
  4. Insert From URL [
       Select; With dialog: Off; Target: $result;
       $payload;
       cURL options: "--header \"X-API-Key: " & $api_key & "\" --header \"Content-Type: application/json\"";
       "http://127.0.0.1:8080/chat"
     ]
  5. Set Variable [$answer; Value: JSONGetElement($result; "answer")]
  6. Set Field [MyTable::QueryResult; $answer]
  7. Exit Script [Text Result: $answer]

示例查询:
  - "找出所有北京客户，按创建日期降序排列"
  - "上个月新增了多少条记录？"
  - "把张三的电话号码更新为 13800138000"
```

- [ ] **Step 3: 创建 AI_OCR_Invoice.txt**

```
FileMaker Script: AI OCR Invoice
=================================
用途: 对容器字段中的发票图片进行 OCR 识别，提取结构化数据写入字段

前提条件:
  1. Gateway 运行并已配置 Provider (支持 Vision 的模型)
  2. 布局上有以下字段:
     - InvoiceImage (Container) — 发票图片
     - InvoiceNumber (Text) — 发票号
     - InvoiceDate (Date) — 开票日期
     - InvoiceAmount (Number) — 金额
     - InvoiceSeller (Text) — 销售方
     - OCRResult (Text) — 原始 OCR 结果 (JSON)

脚本步骤:
  1. If [IsEmpty(MyTable::InvoiceImage)]
  2.   Exit Script [Text Result: "Error: No image in container field"]
  3. End If
  4. # 将容器字段内容转为 Base64
  5. Set Variable [$base64; Value: Base64Encode(MyTable::InvoiceImage)]
  6. Set Variable [$image_url; Value: "data:image/png;base64," & $base64]
  7. # 构造带 media 的请求
  8. Set Variable [$payload; Value: JSONSetElement("{}";
       ["session"; "ocr_invoice_" & Get(AccountName); JSONString];
       ["message"; "识别这张发票"; JSONString];
       ["media"; JSONSetElement("[]";
         [0; $image_url; JSONString]
       ); JSONArray]
     )]
  9. Set Variable [$api_key; Value: "filemaker-secret-key-change-me"]
  10. Insert From URL [
        Select; With dialog: Off; Target: $result;
        $payload;
        cURL options: "--header \"X-API-Key: " & $api_key & "\" --header \"Content-Type: application/json\"";
        "http://127.0.0.1:8080/chat"
      ]
  11. # 解析 OCR 结果
  12. Set Variable [$raw_answer; Value: JSONGetElement($result; "answer")]
  13. Set Field [MyTable::OCRResult; $raw_answer]
  14. # 如果 AI 返回了 JSON，解析各字段
  15. Set Variable [$inv_num; Value: JSONGetElement($raw_answer; "invoice_number")]
  16. If [not IsEmpty($inv_num)]
  17.   Set Field [MyTable::InvoiceNumber; $inv_num]
  18.   Set Field [MyTable::InvoiceDate; JSONGetElement($raw_answer; "date")]
  19.   Set Field [MyTable::InvoiceAmount; JSONGetElement($raw_answer; "amount")]
  20.   Set Field [MyTable::InvoiceSeller; JSONGetElement($raw_answer; "seller")]
  21. End If
  22. Exit Script [Text Result: $raw_answer]

注意:
  - 容器字段中的图片格式建议为 PNG 或 JPEG
  - AI 可能需要几秒处理 OCR，注意 Insert From URL 超时
  - 如果 AI 未返回结构化 JSON，OCRResult 将包含非结构化的识别文字
```

- [ ] **Step 4: 创建 README.md**

```markdown
# FileMaker AI Gateway — 脚本模板

本目录包含可直接在 FileMaker Script Workspace 中创建的脚本模板。

## 使用方法

1. 在 FileMaker Pro 中打开 Script Workspace（脚本工作区）
2. 按照 `.txt` 文件中的步骤逐行创建脚本
3. 根据实际布局和字段名调整脚本中的表名和字段引用
4. 修改 `$api_key` 为 Gateway 配置的实际 API Key

## 前置条件

- FileMaker AI Gateway 已启动并运行在 `http://127.0.0.1:8080`
- 如使用 AI_NL_Query，Gateway 需启用 `fm_data_api`
- 如使用 AI_OCR_Invoice，Gateway 需配置支持 Vision 的 Provider

## 脚本列表

| 脚本 | 用途 | 依赖 |
|------|------|------|
| `AI_Chat.txt` | 基础 AI 对话 | Gateway 运行即可 |
| `AI_NL_Query.txt` | 自然语言查询数据库 | fm_data_api 启用 |
| `AI_OCR_Invoice.txt` | 发票 OCR 识别 | Provider 支持 Vision |

## 配置参考

Gateway config.yaml:
```yaml
gateway:
  host: "127.0.0.1"
  port: 8080
  api_key: "filemaker-secret-key-change-me"

fm_data_api:
  enabled: true
  host: "your-fm-server.example.com"
  database: "YourDatabase"
  username: "api-user"
  password: "your-password"
```
```

- [ ] **Step 5: Commit**

```bash
git add fm_scripts/
git commit -m "feat: add FileMaker script templates for AI Chat, NL Query, and OCR Invoice"
```

---

## 最终验证

- [ ] **运行全部测试**

```bash
python -m pytest tests/ -v
```
Expected: 全部 PASS

- [ ] **确认 fm_data_api.enabled=false 时兼容**

```bash
python -m pytest tests/test_agent/ tests/test_api/ tests/test_session/ -v
```
Expected: 全部 PASS（Part 2 行为不变）

- [ ] **启动服务验证**

```bash
python -m filemaker_gateway
```
Expected: Gateway 正常启动，日志显示 "FM Data API disabled — FM Tools will return stub errors"

---

## 文件变更总览

| 文件 | 操作 |
|------|------|
| `filemaker_gateway/config/defaults.py` | 修改 — 新增 FM 默认值 |
| `filemaker_gateway/config/schema.py` | 修改 — 新增 FMDataAPIConfig |
| `filemaker_gateway/config/loader.py` | 修改 — 加载 fm_data_api + env vars |
| `config.yaml` | 修改 — 新增 fm_data_api 段 |
| `filemaker_gateway/fm/__init__.py` | **新建** — 导出 FMDataClient, errors |
| `filemaker_gateway/fm/errors.py` | **新建** — FM 错误类型 |
| `filemaker_gateway/fm/client.py` | **新建** — Data API 客户端 |
| `filemaker_gateway/tool/loader.py` | 修改 — DI 支持 |
| `filemaker_gateway/tool/filemaker/query.py` | 修改 — stub → 真实实现 |
| `filemaker_gateway/tool/filemaker/record.py` | 修改 — stub → 真实实现 |
| `filemaker_gateway/tool/filemaker/script.py` | 修改 — stub → 真实实现 |
| `filemaker_gateway/tool/filemaker/layout.py` | 修改 — stub → 真实实现 |
| `filemaker_gateway/tool/ocr.py` | 修改 — stub → LLM Vision |
| `filemaker_gateway/agent/loop.py` | 修改 — vision media 支持 |
| `filemaker_gateway/main.py` | 修改 — FMDataClient 装配 + Provider DI |
| `fm_scripts/AI_Chat.txt` | **新建** — FM 对话脚本 |
| `fm_scripts/AI_NL_Query.txt` | **新建** — 自然语言查询脚本 |
| `fm_scripts/AI_OCR_Invoice.txt` | **新建** — 发票 OCR 脚本 |
| `fm_scripts/README.md` | **新建** — 使用说明 |
| `tests/test_fm/__init__.py` | **新建** |
| `tests/test_fm/test_errors.py` | **新建** |
| `tests/test_fm/test_client.py` | **新建** |
| `tests/test_config/test_fm_config.py` | **新建** |
| `tests/test_tool/test_filemaker_tools.py` | **新建** |
| `tests/test_tool/test_ocr.py` | **新建** |
| `tests/test_agent/test_loop.py` | **新建** |
