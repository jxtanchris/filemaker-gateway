# OData 集成 — 设计文档

**日期**: 2026-07-15
**状态**: 设计中
**范围**: 新增 FMODataClient，支持 FileMaker OData v4 协议

---

## 1. 目标

在不改变 4 个 FM Tool 和 AgentLoop 的前提下，新增 OData v4 客户端作为 FMDataClient 的替代方案。用户通过配置选择 OData 或 Data API。

## 2. 背景

FileMaker 2024/2025 的 OData v4 (4.01 intermediate conformance) 已完整支持：

- CRUD 操作
- `$filter` 查询
- 脚本执行（`POST /Script.scriptName`）
- 容器字段上传（base64 内联）

相比 Data API，OData 不需要 token 管理（每次请求 Basic Auth），查询语法更标准（`$filter`），且 Claris 明确承诺长期支持。

## 3. 架构

```
Gateway → Tool (不变)
              │
              ▼ fm_client (接口一致)
         ┌────┴────┐
         │         │
    FMODataClient  FMDataClient (保留不动)
    (新增)         (已有)
```

- Tool 层零改动，接收 `fm_client` 不看底层实现
- `main.py` 装配时按配置选择客户端
- 两个客户端提供相同的方法签名

## 4. 与 Data API 的核心差异

| | Data API | OData v4 |
|---|---|---|
| 认证 | Token (POST /sessions → Bearer) | Basic Auth (每次请求) |
| Endpoint | `/fmi/data/vLatest/databases/{db}/layouts/{layout}/...` | `/fmi/odata/v4/databases/{db}/tables/{table}` |
| 查询 | POST `/_find` + JSON query | GET `?$filter=NAME eq 'xxx'` |
| 脚本 | `GET /layouts/{layout}/script/{name}` | `POST /Script.{name}` |
| 容器 | multipart file upload | base64 内联在 field_data 中 |
| 术语 | layout | table |

## 5. FMODATAClient 接口

```python
class FMODataClient:
    def __init__(self, config: FMODataConfig) -> None
    async def close(self) -> None

    # CRUD — 与 FMDataClient 相同签名
    async def get_records(table, offset=1, limit=100, sort=None) -> list[dict]
    async def get_record(table, primary_key_value) -> dict
    async def create_record(table, field_data) -> dict
    async def update_record(table, primary_key_value, field_data) -> dict
    async def delete_record(table, primary_key_value) -> None

    # Find — OData $filter 语法
    async def find(table, filter_str, sort=None, offset=1, limit=100) -> list[dict]

    # Script — 不需要 layout 参数
    async def run_script(script_name, script_param=None) -> dict

    # Metadata
    async def get_tables() -> list[str]
    async def get_table_metadata(table) -> dict

    # Container — base64
    async def upload_container(table, pk, field, base64_data) -> bool
    async def get_container_url(table, pk, field) -> str
```

## 6. 配置

### config.yaml

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

### 环境变量

```
FILEMAKER_GATEWAY_FM_ODATA_ENABLED=true
FILEMAKER_GATEWAY_FM_ODATA_HOST=1.13.141.154
FILEMAKER_GATEWAY_FM_ODATA_DATABASE=DataAPI_Transactions
FILEMAKER_GATEWAY_FM_ODATA_USERNAME=rest
FILEMAKER_GATEWAY_FM_ODATA_PASSWORD=rest
FILEMAKER_GATEWAY_FM_ODATA_PROTOCOL=https
FILEMAKER_GATEWAY_FM_ODATA_VERIFY_SSL=false
```

### 装配 (main.py)

```python
fm_client = None
if config.fm_odata.enabled:
    fm_client = FMODataClient(config.fm_odata)
elif config.fm_data_api.enabled:
    fm_client = FMDataClient(config.fm_data_api)
# else: fm_client = None → FM Tools 返回降级错误
```

## 7. Tool 层兼容

4 个 FM Tool 不改代码。仅 `filemaker_query` 的 `find` action 需同时兼容两种格式：

```python
# query.py — find action
if action == "find":
    # OData: filter_str 直接是 "$filter" 字符串
    if self._fm is FMODataClient or isinstance(query, str) and not query.startswith("["):
        records = await self._fm.find(layout, query or "", limit=limit)
    else:
        # Data API: JSON array
        criteria = json.loads(query) if query else []
        records = await self._fm.find(layout, criteria, limit=limit)
```

LLM 会在系统提示中知道当前使用的协议，自动选择正确的查询格式。

## 8. OData API 映射

| 操作 | OData 请求 |
|------|-----------|
| 列出表 | `GET /tables` |
| 表元数据 | `GET /tables/{name}` |
| 读取记录 | `GET /tables/{name}?$top=100&$skip=0` |
| 获取单条 | `GET /tables/{name}('{pk}')` |
| 创建记录 | `POST /tables/{name}` + `{"field": "value", ...}` |
| 更新记录 | `PATCH /tables/{name}('{pk}')` |
| 删除记录 | `DELETE /tables/{name}('{pk}')` |
| 查找 | `GET /tables/{name}?$filter=NAME eq 'xxx'&$top=100` |
| 执行脚本 | `POST /Script.{scriptName}` + `{"scriptParameterValue": "..."}` |
| 容器上传 | `POST /tables/{name}` + `{"field": "<base64>"}` |
| 容器下载 | `GET /tables/{name}('{pk}')?$select=Field` → base64 解码 |

## 9. 测试策略

- `tests/test_fm/test_client_odata.py` — mock httpx，验证 CRUD/find/script/container
- `tests/test_fm/test_odata_errors.py` — 错误码映射
- `tests/test_config/test_odata_config.py` — 配置加载 + env var
- 现有 78 个测试必须通过（默认 `fm_odata.enabled=false`）

## 10. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `filemaker_gateway/fm/client_odata.py` | **新建** | OData 客户端 (~250 行) |
| `filemaker_gateway/config/schema.py` | 修改 | 新增 FMODataConfig |
| `filemaker_gateway/config/defaults.py` | 修改 | 新增 OData 默认值 |
| `filemaker_gateway/config/loader.py` | 修改 | 加载 fm_odata + env vars |
| `config.yaml` | 修改 | 新增 fm_odata 段 |
| `filemaker_gateway/main.py` | 修改 | 优先 OData，fallback Data API |
| `filemaker_gateway/tool/filemaker/query.py` | 修改 | find 兼容 OData $filter |
| `tests/test_fm/test_client_odata.py` | **新建** | OData 客户端测试 |
| `tests/test_config/test_odata_config.py` | **新建** | OData 配置测试 |

## 11. 风险

1. **OData 表名 vs FM 布局名**：OData 操作的是基础表，不是布局。如果 FM 文件中的表名和布局名不同，LLM 需要知道表名。解决方案：系统提示中列出可用表名。
2. **Basic Auth 明文传输**：必须 HTTPS。本方案强制 `protocol: "https"` 默认值。
3. **脚本参数格式**：OData 要求 `{"scriptParameterValue": "..."}`，与 Data API 的 URL 参数不同。
