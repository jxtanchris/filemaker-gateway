# OData v4 集成 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 新增 FMODataClient，通过 FileMaker OData v4 API 读写数据，替换 Data API 作为主连接方式。

**Architecture:** 新增 `fm/client_odata.py`，接口与 FMDataClient 一致。配置优先 OData → fallback Data API → stub 降级。4 个 FM Tool 零改动（只调 query.py 的 find 兼容）。

**Tech Stack:** Python 3.12+, httpx, FastAPI, Pydantic, pytest + pytest-httpx

## Global Constraints

- `fm_odata.enabled = false`（默认）时所有现有测试必须通过
- FMODataClient 方法签名与 FMDataClient 一致，Tool 层不动
- Basic Auth 每次请求，无 token 管理
- OData 操作的是 database table，不是 FM layout
- 测试使用 mock，不依赖真实 FM Server
- 遵循现有代码风格

---

### Task 1: FMODataConfig 配置模型

**Files:**
- Modify: `filemaker_gateway/config/schema.py`
- Modify: `filemaker_gateway/config/defaults.py`

**Interfaces:**
- Produces: `FMODataConfig(BaseModel)` — host, database, username, password, protocol, verify_ssl, enabled
- Produces: `AppConfig.fm_odata: FMODataConfig` field

**Steps:**

- [ ] **Step 1: 在 defaults.py 添加默认值**

```python
# filemaker_gateway/config/defaults.py 追加

DEFAULT_FM_ODATA_HOST = ""
DEFAULT_FM_ODATA_DATABASE = ""
DEFAULT_FM_ODATA_USERNAME = ""
DEFAULT_FM_ODATA_PASSWORD = ""
DEFAULT_FM_ODATA_PROTOCOL = "https"
DEFAULT_FM_ODATA_VERIFY_SSL = True
DEFAULT_FM_ODATA_ENABLED = False
```

- [ ] **Step 2: 在 schema.py 添加 FMODataConfig**

```python
# filemaker_gateway/config/schema.py

class FMODataConfig(BaseModel):
    """FileMaker OData v4 connection configuration."""

    host: str = DEFAULT_FM_ODATA_HOST
    database: str = DEFAULT_FM_ODATA_DATABASE
    username: str = DEFAULT_FM_ODATA_USERNAME
    password: str = DEFAULT_FM_ODATA_PASSWORD
    protocol: str = DEFAULT_FM_ODATA_PROTOCOL
    verify_ssl: bool = DEFAULT_FM_ODATA_VERIFY_SSL
    enabled: bool = DEFAULT_FM_ODATA_ENABLED


class AppConfig(BaseModel):
    gateway: GatewayConfig = GatewayConfig()
    database: DatabaseConfig = DatabaseConfig()
    fm_data_api: FMDataAPIConfig = FMDataAPIConfig()
    fm_odata: FMODataConfig = FMODataConfig()  # 新增
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
```

- [ ] **Step 3: 运行测试确认无破坏**

```bash
python -m pytest tests/ -v
```
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add filemaker_gateway/config/defaults.py filemaker_gateway/config/schema.py
git commit -m "feat: add FMODataConfig model with defaults"
```

---

### Task 2: FMODataClient 核心客户端

**Files:**
- Create: `filemaker_gateway/fm/client_odata.py`

**Interfaces:**
- Consumes: `FMODataConfig` from `config/schema.py`
- Consumes: `FMDataError`, `FMAuthError`, `FMNotFoundError`, `FMValidationError` from `fm/errors.py`
- Produces: `FMODataClient` with same method signatures as FMDataClient (using `table` parameter name instead of `layout`)

**Key differences from FMDataClient:**
- No token management — Basic Auth per request
- Base URL: `{protocol}://{host}/fmi/odata/v4/databases/{database}`
- `get_record(table, pk)` → `GET /tables/{table}('{pk}')`
- `find(table, filter_str)` → `GET /tables/{table}?$filter={filter_str}`
- `run_script(script_name, param)` → `POST /Script.{script_name}`
- `get_tables()` → `GET /tables`
- Container: base64 inline in field_data, not multipart

**Steps:**

- [ ] **Step 1: 写测试文件**

```python
# tests/test_fm/__init__.py already exists
# tests/test_fm/test_client_odata.py

import json
import pytest
from filemaker_gateway.config.schema import FMODataConfig
from filemaker_gateway.fm.client_odata import FMODataClient
from filemaker_gateway.fm.errors import FMAuthError, FMNotFoundError


@pytest.fixture
def odata_config():
    return FMODataConfig(
        host="fm.example.com",
        database="MyDB",
        username="admin",
        password="secret",
        protocol="https",
        verify_ssl=True,
        enabled=True,
    )


@pytest.fixture
def odata_base_url(odata_config):
    c = odata_config
    return f"{c.protocol}://{c.host}/fmi/odata/v4/databases/{c.database}"


class TestFMODataClientAuth:

    @pytest.mark.asyncio
    async def test_basic_auth_on_request(self, httpx_mock, odata_config, odata_base_url):
        """Should send Basic Auth header on every request."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/tables/Contacts?%24top=10&%24skip=0",
            json={"value": []},
        )

        client = FMODataClient(odata_config)
        await client.get_records("Contacts", limit=10)

        request = httpx_mock.get_requests()[0]
        assert request.headers["Authorization"].startswith("Basic ")

    @pytest.mark.asyncio
    async def test_auth_failure_raises(self, httpx_mock, odata_config, odata_base_url):
        """Should raise FMAuthError on 401."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/tables/Contacts?%24top=10&%24skip=0",
            status_code=401,
        )

        client = FMODataClient(odata_config)
        with pytest.raises(FMAuthError):
            await client.get_records("Contacts", limit=10)


class TestFMODataClientCRUD:

    @pytest.mark.asyncio
    async def test_get_records(self, httpx_mock, odata_config, odata_base_url):
        """Should GET records with $top and $skip."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/tables/Contacts?%24top=50&%24skip=0",
            json={"value": [{"ID": 1, "NAME": "Alice"}]},
        )

        client = FMODataClient(odata_config)
        records = await client.get_records("Contacts", limit=50)

        assert len(records) == 1
        assert records[0]["NAME"] == "Alice"

    @pytest.mark.asyncio
    async def test_get_record_by_pk(self, httpx_mock, odata_config, odata_base_url):
        """Should GET single record by primary key."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/tables/Contacts('42')",
            json={"ID": 42, "NAME": "Bob"},
        )

        client = FMODataClient(odata_config)
        record = await client.get_record("Contacts", "42")

        assert record["NAME"] == "Bob"

    @pytest.mark.asyncio
    async def test_create_record(self, httpx_mock, odata_config, odata_base_url):
        """Should POST to create a record."""
        httpx_mock.add_response(
            method="POST",
            url=f"{odata_base_url}/tables/Contacts",
            json={"ID": 99, "NAME": "Charlie"},
        )

        client = FMODataClient(odata_config)
        result = await client.create_record("Contacts", {"NAME": "Charlie"})

        assert result["ID"] == 99

        post_req = httpx_mock.get_requests()[0]
        body = json.loads(post_req.content)
        assert body["NAME"] == "Charlie"

    @pytest.mark.asyncio
    async def test_update_record(self, httpx_mock, odata_config, odata_base_url):
        """Should PATCH to update a record."""
        httpx_mock.add_response(
            method="PATCH",
            url=f"{odata_base_url}/tables/Contacts('42')",
            json={"ID": 42, "NAME": "Updated"},
        )

        client = FMODataClient(odata_config)
        result = await client.update_record("Contacts", "42", {"NAME": "Updated"})

        assert result["NAME"] == "Updated"

    @pytest.mark.asyncio
    async def test_delete_record(self, httpx_mock, odata_config, odata_base_url):
        """Should DELETE a record."""
        httpx_mock.add_response(
            method="DELETE",
            url=f"{odata_base_url}/tables/Contacts('42')",
            status_code=204,
        )

        client = FMODataClient(odata_config)
        await client.delete_record("Contacts", "42")
        # Should not raise


class TestFMODataClientFind:

    @pytest.mark.asyncio
    async def test_find_with_filter(self, httpx_mock, odata_config, odata_base_url):
        """Should use OData $filter syntax."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/tables/Contacts?%24filter=NAME+eq+%27Alice%27&%24top=100&%24skip=0",
            json={"value": [{"ID": 1, "NAME": "Alice"}]},
        )

        client = FMODataClient(odata_config)
        results = await client.find("Contacts", "NAME eq 'Alice'")

        assert len(results) == 1
        assert results[0]["NAME"] == "Alice"


class TestFMODataClientScript:

    @pytest.mark.asyncio
    async def test_run_script(self, httpx_mock, odata_config, odata_base_url):
        """Should POST to Script endpoint."""
        httpx_mock.add_response(
            method="POST",
            url=f"{odata_base_url}/Script.ExportPDF",
            json={"resultParameter": "OK"},
        )

        client = FMODataClient(odata_config)
        result = await client.run_script("ExportPDF", "invoice_123")

        assert result["resultParameter"] == "OK"

        req = httpx_mock.get_requests()[0]
        body = json.loads(req.content)
        assert body["scriptParameterValue"] == "invoice_123"

    @pytest.mark.asyncio
    async def test_run_script_without_param(self, httpx_mock, odata_config, odata_base_url):
        """Should run script without parameter."""
        httpx_mock.add_response(
            method="POST",
            url=f"{odata_base_url}/Script.RefreshCache",
            json={"resultParameter": "Done"},
        )

        client = FMODataClient(odata_config)
        result = await client.run_script("RefreshCache")

        assert result["resultParameter"] == "Done"


class TestFMODataClientMetadata:

    @pytest.mark.asyncio
    async def test_get_tables(self, httpx_mock, odata_config, odata_base_url):
        """Should return table names from OData service document."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/tables",
            json={"value": [{"name": "CONTACT"}, {"name": "INVOICE"}]},
        )

        client = FMODataClient(odata_config)
        tables = await client.get_tables()

        assert tables == ["CONTACT", "INVOICE"]


class TestFMODataClientClose:

    @pytest.mark.asyncio
    async def test_close(self, httpx_mock, odata_config, odata_base_url):
        """Should release the HTTP client."""
        # Need a request first to create the client
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/tables/X?%24top=1&%24skip=0",
            json={"value": []},
        )

        client = FMODataClient(odata_config)
        await client.get_records("X", limit=1)
        await client.close()
        # Should not raise
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_fm/test_client_odata.py -v
```
Expected: FAIL — FMODataClient not defined

- [ ] **Step 3: 实现 client_odata.py**

```python
# filemaker_gateway/fm/client_odata.py
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
        params = {"$top": limit, "$skip": skip}
        if sort and len(sort) > 0:
            orderby = ",".join(
                f"{s['fieldName']} {s.get('sortOrder', 'asc')}" for s in sort
            )
            params["$orderby"] = orderby

        logger.debug("OData GET records: table={}, limit={}, skip={}", table, limit, skip)
        response = await self._client.get(
            f"{self._base_url}/tables/{quote(table, safe='')}",
            params=params,
        )
        self._check_errors(response.json() if response.status_code >= 400 else None, response.status_code)
        data = response.json()
        return data.get("value", [])

    async def get_record(self, table: str, record_id: str) -> dict:
        """Get a single record by primary key."""
        escaped_pk = quote(record_id, safe="")
        logger.debug("OData GET record: table={}, pk={}", table, escaped_pk)
        response = await self._client.get(
            f"{self._base_url}/tables/{quote(table, safe='')}('{escaped_pk}')",
        )
        if response.status_code == 404:
            raise FMNotFoundError(f"Record '{record_id}' not found in table '{table}'")
        self._check_errors(None if response.status_code < 400 else response.json(), response.status_code)
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
        self._check_errors(response.json() if response.status_code >= 400 else None, response.status_code)
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
        self._check_errors(response.json() if response.status_code >= 400 else None, response.status_code)
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
        self._check_errors(response.json() if response.status_code >= 400 else None, response.status_code)

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
        params = {"$top": limit, "$skip": skip}
        if filter_str:
            params["$filter"] = filter_str
        if sort:
            orderby = ",".join(
                f"{s['fieldName']} {s.get('sortOrder', 'asc')}" for s in sort
            )
            params["$orderby"] = orderby

        logger.debug("OData FIND: table={}, filter={}", table, filter_str)
        response = await self._client.get(
            f"{self._base_url}/tables/{quote(table, safe='')}",
            params=params,
        )
        self._check_errors(response.json() if response.status_code >= 400 else None, response.status_code)
        data = response.json()
        return data.get("value", [])

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
        self._check_errors(response.json() if response.status_code >= 400 else None, response.status_code)
        return response.json()

    # --- Metadata ---

    async def get_tables(self) -> list[str]:
        """Get all table names."""
        logger.debug("OData GET tables")
        response = await self._client.get(f"{self._base_url}/tables")
        self._check_errors(response.json() if response.status_code >= 400 else None, response.status_code)
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
        self._check_errors(None if response.status_code < 400 else response.json(), response.status_code)
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_fm/test_client_odata.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/fm/client_odata.py tests/test_fm/test_client_odata.py
git commit -m "feat: add FMODataClient for FileMaker OData v4 API"
```

---

### Task 3: 配置加载 + config.yaml

**Files:**
- Modify: `filemaker_gateway/config/loader.py`
- Modify: `config.yaml`
- Create: `tests/test_config/test_odata_config.py`

**Steps:**

- [ ] **Step 1: 在 loader.py 添加 fm_odata 解析**

在 `load_config()` 的 YAML 解析段（fm_data_api 之后）添加：

```python
if "fm_odata" in raw:
    fo = raw["fm_odata"]
    config.fm_odata = FMODataConfig(
        host=fo.get("host", config.fm_odata.host),
        database=fo.get("database", config.fm_odata.database),
        username=fo.get("username", config.fm_odata.username),
        password=fo.get("password", config.fm_odata.password),
        protocol=fo.get("protocol", config.fm_odata.protocol),
        verify_ssl=fo.get("verify_ssl", config.fm_odata.verify_ssl),
        enabled=fo.get("enabled", config.fm_odata.enabled),
    )
```

在 `_apply_env_overrides()` 末尾添加：

```python
# FM OData
_set_if_present("FM_ODATA_HOST", config.fm_odata, "host")
_set_if_present("FM_ODATA_DATABASE", config.fm_odata, "database")
_set_if_present("FM_ODATA_USERNAME", config.fm_odata, "username")
_set_if_present("FM_ODATA_PASSWORD", config.fm_odata, "password")
_set_if_present("FM_ODATA_PROTOCOL", config.fm_odata, "protocol")
_set_if_present("FM_ODATA_VERIFY_SSL", config.fm_odata, "verify_ssl", lambda v: v.lower() == "true")
_set_if_present("FM_ODATA_ENABLED", config.fm_odata, "enabled", lambda v: v.lower() == "true")
```

- [ ] **Step 2: 更新 config.yaml**

```yaml
fm_odata:
  enabled: false
  host: ""
  database: ""
  username: ""
  password: ""
  protocol: "https"
  verify_ssl: true
```

- [ ] **Step 3: 写配置测试**

```python
# tests/test_config/test_odata_config.py
import os
from filemaker_gateway.config.loader import load_config


def test_default_odata_config_disabled():
    config = load_config("nonexistent.yaml")
    assert config.fm_odata.enabled is False
    assert config.fm_odata.host == ""


def test_odata_env_var_overrides():
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_HOST"] = "fm.example.com"
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_DATABASE"] = "TestDB"
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_USERNAME"] = "admin"
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_PASSWORD"] = "secret"
    os.environ["FILEMAKER_GATEWAY_FM_ODATA_ENABLED"] = "true"

    try:
        config = load_config("nonexistent.yaml")
        assert config.fm_odata.host == "fm.example.com"
        assert config.fm_odata.database == "TestDB"
        assert config.fm_odata.enabled is True
    finally:
        for key in list(os.environ):
            if key.startswith("FILEMAKER_GATEWAY_FM_ODATA_"):
                del os.environ[key]
```

- [ ] **Step 4: 运行测试**

```bash
python -m pytest tests/ -v
```
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/config/loader.py config.yaml tests/test_config/
git commit -m "feat: add fm_odata config loading with env var overrides"
```

---

### Task 4: query.py find 兼容 OData

**Files:**
- Modify: `filemaker_gateway/tool/filemaker/query.py`

**Change:** `find` action 同时支持 OData `$filter` 字符串和 Data API JSON array。

- [ ] **Step 1: 修改 query.py 的 find action**

```python
# filemaker_gateway/tool/filemaker/query.py — execute() 中 find 部分

elif action == "find":
    if not layout:
        return ToolResult.error("layout/table name is required for 'find' action")

    # Compatible with both OData ($filter string) and Data API (JSON array)
    if query and query.strip().startswith("["):
        # Data API: JSON array of criteria
        try:
            criteria = json.loads(query)
        except json.JSONDecodeError:
            return ToolResult.error("query must be valid JSON array for Data API find")
    else:
        # OData: $filter string (or empty for all records)
        criteria = query or ""

    records = await self._fm.find(layout, criteria, limit=limit)
    return json.dumps(records, ensure_ascii=False, default=str)
```

- [ ] **Step 2: 运行测试确认无破坏**

```bash
python -m pytest tests/test_tool/test_filemaker_tools.py -v
```
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add filemaker_gateway/tool/filemaker/query.py
git commit -m "feat: query find action compatible with OData $filter strings"
```

---

### Task 5: main.py 装配（OData → Data API → stub）

**Files:**
- Modify: `filemaker_gateway/main.py`

**Change:** 优先创建 FMODataClient，fallback FMDataClient，否则 None。

- [ ] **Step 1: 修改 main.py lifespan**

替换当前 FMDataClient 创建逻辑：

```python
# filemaker_gateway/main.py — lifespan 中替换 FMDataClient 创建部分

from filemaker_gateway.fm.client_odata import FMODataClient  # 新增 import

# 3. FM client — OData first, then Data API, else stub
fm_client = None
if config.fm_odata.enabled:
    fm_client = FMODataClient(config.fm_odata)
    logger.info(
        "FM OData client created: {}://{}/{}",
        config.fm_odata.protocol,
        config.fm_odata.host,
        config.fm_odata.database,
    )
elif config.fm_data_api.enabled:
    fm_client = FMDataClient(config.fm_data_api)
    logger.info(
        "FM Data API client created: {}://{}/{}",
        config.fm_data_api.protocol,
        config.fm_data_api.host,
        config.fm_data_api.database,
    )
else:
    logger.info("FM API disabled — FM Tools will return stub errors")
```

- [ ] **Step 2: 运行全部测试**

```bash
python -m pytest tests/ -v
```
Expected: 全部 PASS（默认 fm_odata.enabled=false, fm_data_api.enabled=false）

- [ ] **Step 3: Commit**

```bash
git add filemaker_gateway/main.py
git commit -m "feat: wire OData client with Data API fallback in app startup"
```

---

## 最终验证

- [ ] **运行全部测试**

```bash
python -m pytest tests/ -v
```

- [ ] **启动 Gateway 测试 OData 连接**

```bash
# 在 .env 中配置 OData:
# FILEMAKER_GATEWAY_FM_ODATA_ENABLED=true
# FILEMAKER_GATEWAY_FM_ODATA_HOST=1.13.141.154
# FILEMAKER_GATEWAY_FM_ODATA_DATABASE=DataAPI_Transactions
# FILEMAKER_GATEWAY_FM_ODATA_USERNAME=rest
# FILEMAKER_GATEWAY_FM_ODATA_PASSWORD=rest
# FILEMAKER_GATEWAY_FM_ODATA_VERIFY_SSL=false

python -m filemaker_gateway &
curl -s -X POST http://127.0.0.1:8080/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: filemaker-secret-key-change-me" \
  -d '{"session":"odata-test","message":"列出 project 表的前 3 条记录"}'
```

## 文件变更总览

| 文件 | 操作 | 说明 |
|------|------|------|
| `filemaker_gateway/config/defaults.py` | 修改 | 新增 7 个 OData 默认值 |
| `filemaker_gateway/config/schema.py` | 修改 | 新增 FMODataConfig |
| `filemaker_gateway/fm/client_odata.py` | **新建** | OData 客户端 (~200 行) |
| `filemaker_gateway/config/loader.py` | 修改 | 加载 fm_odata + env vars |
| `config.yaml` | 修改 | 新增 fm_odata 段 |
| `filemaker_gateway/tool/filemaker/query.py` | 修改 | find 兼容 OData |
| `filemaker_gateway/main.py` | 修改 | OData → Data API fallback |
| `tests/test_fm/test_client_odata.py` | **新建** | OData 客户端测试 |
| `tests/test_config/test_odata_config.py` | **新建** | OData 配置测试 |
