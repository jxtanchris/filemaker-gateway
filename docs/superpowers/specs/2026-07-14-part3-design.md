# Part 3: FileMaker Data API 集成 — 设计文档

**日期**: 2026-07-14
**状态**: 已批准
**范围**: 将 AI 能力无缝接入 FileMaker，完成 FileMaker → Gateway → LLM → FM Data 完整闭环

---

## 1. 目标

Part 2 已完成 Gateway 核心引擎（AgentLoop、AgentRunner、Provider、Tool、Session），
4 个 FileMaker Tools 为 stub。Part 3 将其全部升级为真实实现：

1. **FileMaker Tools 去 stub** — 通过 FileMaker Data API 真实读写 FM 数据
2. **Insert From URL 集成** — FileMaker 端脚本模板，用户可直接使用
3. **OCR + Vision** — 图片理解与 OCR 提取（复用 LLM Vision）
4. **SQL Tool 保持 stub** — 后续再议

---

## 2. 架构

### 2.1 双向通信模型

```
方向 1: FM → Gateway (Insert From URL)
  FM Script "AI Chat"
    → Set Variable [$payload]
    → Insert From URL [POST http://127.0.0.1:8080/chat, $payload]
    → JSON 解析 → 写入结果字段

方向 2: Gateway → FM (Data API)
  AgentRunner 调用 filemaker_query tool
    → FMDataClient (httpx)
    → POST https://fm-server/fmi/data/v1/databases/MyDB/layouts/Contacts/_find
    → 返回数据 → LLM 整理 → 回复用户
```

### 2.2 与 Part 2 的关系

- **不变**: REST API 端点、AgentLoop 状态机、AgentRunner、Provider 系统、Session 管理、Tool 基类、所有现有测试
- **扩展**: Tool 实现从 stub 变为真实调用、AgentLoop._build() 支持 vision 格式
- **新增**: `fm/` 模块、`fm_scripts/` 目录

### 2.3 降级策略

`fm_data_api.enabled` 为 `false` 时（默认）：
- `FMDataClient` 不被创建（`None`）
- FM Tools 检测到 `self._fm is None`，返回友好错误
- Gateway 完全不受影响，等同于 Part 2 行为

---

## 3. 实现 Phase

### Phase 1: Data API 客户端 (`filemaker_gateway/fm/`)

新建模块，封装 FileMaker Data API REST 调用。

```
filemaker_gateway/fm/
├── __init__.py     # 导出 FMDataClient, FMDataError
├── client.py       # ~200 行，核心客户端
└── errors.py       # ~30 行，错误类型
```

**FMDataClient 接口**:

```python
class FMDataClient:
    def __init__(self, host, database, username, password, protocol="https", verify_ssl=True)
    # 内部管理 token，自动登录/过期重登

    # CRUD
    async def get_records(layout, offset, limit, sort) -> list[dict]
    async def get_record(layout, record_id) -> dict
    async def create_record(layout, field_data, script?, script_param?) -> dict
    async def update_record(layout, record_id, field_data, mod_id?) -> dict
    async def delete_record(layout, record_id) -> None

    # Query
    async def find(layout, query, sort, offset, limit) -> list[dict]

    # Script
    async def run_script(layout, script_name, script_param?) -> dict

    # Metadata
    async def get_layouts() -> list[str]
    async def get_layout_metadata(layout) -> dict
    async def get_scripts() -> list[str]

    # Container (for OCR)
    async def upload_container(layout, record_id, field_name, file_path) -> dict
    async def get_container_url(layout, record_id, field_name) -> str
```

**技术选型**:
- `httpx.AsyncClient`（与 FastAPI 生态一致）
- Token 管理: 调用前检查 token，过期时自动 `POST /sessions` 获取新 token
- 连接复用: 单个 `httpx.AsyncClient` 实例，`__init__` 创建，`close()` 释放

**错误处理** (`errors.py`):
- `FMDataError`: 基类，携带 Data API 返回的 code/message
- `FMAuthError`: 401 认证失败
- `FMNotFoundError`: 404 记录/布局不存在
- `FMValidationError`: 400 字段校验错误

**配置** (`config/schema.py` 新增):
```python
class FMDataAPIConfig(BaseModel):
    host: str = ""
    database: str = ""
    username: str = ""
    password: str = ""          # 支持 FILEMAKER_GATEWAY_FM_DATA_API_PASSWORD env var
    protocol: str = "https"
    verify_ssl: bool = True
    enabled: bool = False
```

### Phase 2: 替换 FM Tool Stub

将 4 个 FileMaker Tool 从 stub 替换为真实 Data API 调用。

**依赖注入方案**: 扩展 `ToolLoader.load()` 支持 `**tool_kwargs`。通过 `inspect.signature` 匹配参数名，
只传入 Tool 构造函数接受的参数，不接受的自动忽略。

```python
# tool/loader.py
import inspect

def load(self, registry: ToolRegistry, **tool_kwargs) -> list[str]:
    for tool_cls in tool_classes:
        sig = inspect.signature(tool_cls.__init__)
        matching = {k: v for k, v in tool_kwargs.items() if k in sig.parameters}
        instance = tool_cls(**matching)
```

这样 `FileMakerQueryTool(fm_client=...)` 只收 `fm_client`，`OCRTool(provider=...)` 只收 `provider`，Intertool 各取所需。

**Tool 改动**（以 query 为例，其余同理）:

```python
class FileMakerQueryTool(Tool):
    def __init__(self, fm_client: FMDataClient | None = None):
        self._fm = fm_client

    async def execute(self, action, layout=None, query=None, limit=100):
        if self._fm is None:
            return ToolResult.error("FM Data API 未启用 (fm_data_api.enabled=false)")
        if action == "select":
            records = await self._fm.get_records(layout, limit=limit)
        elif action == "execute_sql":
            ...  # FM Data API 不支持 SQL，通过 ExecuteSQL script parameter 间接执行
        elif action == "find":
            records = await self._fm.find(layout, json.loads(query), limit=limit)
        return json.dumps(records, ensure_ascii=False, default=str)
```

**4 个 Tool 映射**:

| Tool | Data API 方法 |
|------|-------------|
| `filemaker_query` (select) | `fm_client.get_records()` |
| `filemaker_query` (find) | `fm_client.find()` |
| `filemaker_record` (create) | `fm_client.create_record()` |
| `filemaker_record` (update) | `fm_client.update_record()` |
| `filemaker_record` (delete) | `fm_client.delete_record()` |
| `filemaker_script` | `fm_client.run_script()` |
| `filemaker_layout` (list) | `fm_client.get_layouts()` |
| `filemaker_layout` (open) | 仅返回布局名（无法远程切换 FM 界面） |

**`main.py` 装配**:
```python
if config.fm.enabled:
    fm_client = FMDataClient(...)
    loader.load(registry, fm_client=fm_client)
else:
    loader.load(registry)
```

### Phase 3: FileMaker 脚本模板 (`fm_scripts/`)

提供可直接在 FM Script Workspace 中创建的脚本模板。

```
fm_scripts/
├── AI_Chat.txt              # 基础 AI 对话
├── AI_OCR_Invoice.txt       # 发票 OCR 识别
├── AI_NL_Query.txt          # 自然语言查询数据
└── README.md                # 配置说明
```

**脚本格式**: 纯文本，包含 FM Script Workspace 步骤描述 + 注释。用户照着步骤在 FM 中手动创建。

**AI_Chat.txt 核心流程**:
1. 读取 `UserInput` 字段
2. 构造 JSON: `{"session": Get(AccountName), "message": $input}`
3. `Insert From URL` POST `http://127.0.0.1:8080/chat`，带 `X-API-Key` header
4. 解析返回 JSON: `JSONGetElement($result; "answer")`
5. 写入 `AIResponse` 字段

**AI_OCR_Invoice.txt 核心流程**:
1. 从容器字段 `Base64Encode` 图片
2. 构造 media 消息: `{"session":"ocr","message":"识别这张发票","media":["data:image/png;base64,..."]}`
3. Insert From URL POST /chat
4. 解析返回的 JSON 发票字段 → 填入对应字段

### Phase 4: OCR Tool + Media Vision

**4a. AgentLoop Vision 支持** (`agent/loop.py`):

`_build()` 方法中，当 `ctx.media` 非空时构造 `content` 列表:
```python
if ctx.media:
    content = [{"type": "text", "text": ctx.user_message}]
    for url in ctx.media:
        if url.startswith("data:image"):
            content.append({"type": "image_url", "image_url": {"url": url}})
    messages.append({"role": "user", "content": content})
else:
    messages.append({"role": "user", "content": ctx.user_message})
```

**4b. OCR Tool** (`tool/ocr.py`):

OCR 走 LLM Vision：复用现有 Provider，将图片发给模型做 OCR。

```python
class OCRTool(Tool):
    def __init__(self, provider=None):
        self._provider = provider  # LLMProvider 实例
        self._model = "deepseek-chat"  # vision-capable model

    async def execute(self, image_url, ocr_type="glm"):
        # 构造 vision prompt，调用 provider.chat()
```

3 种模式:
- `glm`: 通用图片 OCR（中文+英文）
- `invoice`: 发票结构提取（发票号、日期、金额、抬头）
- `pdf`: 多页 PDF（需要先将 PDF 拆页为图片）

**Provider 依赖注入**: OCRTool 需要 Provider 实例来调用 Vision API。与 FM Tools 一样通过 `tool_kwargs` 注入。

`main.py`:
```python
loader.load(registry, fm_client=fm_client, provider=provider)
```

### Phase 5: 配置整合 + 端到端

**config.yaml 新增**:
```yaml
fm_data_api:
  enabled: false              # 默认关闭
  host: ""
  database: ""
  username: ""
  password: ""                # 推荐用环境变量
  protocol: "https"
  verify_ssl: true
```

**环境变量映射** (`config/loader.py`):
- `FILEMAKER_GATEWAY_FM_DATA_API_HOST` → `fm_data_api.host`
- `FILEMAKER_GATEWAY_FM_DATA_API_DATABASE` → `fm_data_api.database`
- `FILEMAKER_GATEWAY_FM_DATA_API_USERNAME` → `fm_data_api.username`
- `FILEMAKER_GATEWAY_FM_DATA_API_PASSWORD` → `fm_data_api.password`

---

## 4. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `filemaker_gateway/fm/__init__.py` | 新建 | 导出 FMDataClient, FMDataError |
| `filemaker_gateway/fm/client.py` | 新建 | Data API 客户端 (~200行) |
| `filemaker_gateway/fm/errors.py` | 新建 | 错误类型 (~30行) |
| `filemaker_gateway/config/schema.py` | 修改 | 新增 FMDataAPIConfig |
| `filemaker_gateway/config/loader.py` | 修改 | 加载 fm_data_api 配置 + env var 映射 |
| `config.yaml` | 修改 | 新增 fm_data_api 段 |
| `filemaker_gateway/main.py` | 修改 | 初始化 FMDataClient，注入 Tools |
| `filemaker_gateway/api/deps.py` | 修改 | 注入 fm_client/provider 给 Tool 构造 |
| `filemaker_gateway/tool/loader.py` | 修改 | `load()` 支持 `**tool_kwargs` |
| `filemaker_gateway/tool/filemaker/query.py` | 修改 | stub → Data API 实现 |
| `filemaker_gateway/tool/filemaker/record.py` | 修改 | stub → Data API 实现 |
| `filemaker_gateway/tool/filemaker/script.py` | 修改 | stub → Data API 实现 |
| `filemaker_gateway/tool/filemaker/layout.py` | 修改 | stub → Data API 实现 |
| `filemaker_gateway/tool/ocr.py` | 修改 | stub → LLM Vision 实现 |
| `filemaker_gateway/agent/loop.py` | 修改 | `_build()` 支持 vision media 格式 |
| `fm_scripts/AI_Chat.txt` | 新建 | FM 对话脚本 |
| `fm_scripts/AI_OCR_Invoice.txt` | 新建 | FM OCR 脚本 |
| `fm_scripts/AI_NL_Query.txt` | 新建 | FM 自然语言查询脚本 |
| `fm_scripts/README.md` | 新建 | 使用说明 |

---

## 5. 测试策略

### Phase 1 测试
- `tests/test_fm/test_client.py`: mock httpx 响应，验证 CRUD/auth/find 逻辑
- `tests/test_fm/test_errors.py`: 验证各错误码映射

### Phase 2 测试
- 更新 `tests/test_tool/test_registry.py`: 验证 `tool_kwargs` 注入
- 新增 `tests/test_tool/test_filemaker_tools.py`: mock FMDataClient，验证每个 action 的路由

### Phase 3 验证
- 手动在 FM 中创建脚本，用真实 FM Server 验证
- curl 模拟 Insert From URL 请求

### Phase 4 测试
- `tests/test_tool/test_ocr.py`: mock provider.chat() 返回 OCR 结果
- `tests/test_agent/test_loop.py`: 验证 media → vision content 转换

### Phase 5 测试
- `tests/test_config/test_fm_config.py`: 验证配置加载 + env var 覆盖
- 端到端: curl POST /chat → AgentLoop → Tool → mock Data API → 响应

### 兼容性保证
- 所有 Part 2 测试在 `fm_data_api.enabled = false` 时必须通过
- CI 不依赖真实 FM Server

---

## 6. 实现顺序

```
Phase 1 (fm/client.py) → Phase 2 (4 FM Tools) → Phase 3 (FM 脚本) → Phase 4 (OCR+Vision) → Phase 5 (整合)
```

每个 Phase 独立可测，不阻塞后续。

---

## 7. 风险与注意事项

1. **Data API token 过期**: 默认 15 分钟，`FMDataClient` 内部自动管理重建
2. **FM Server 网络不可达**: Tool 返回 `ToolResult.error()`，不会被 LLM 消费为正常数据
3. **Vision 模型选择**: DeepSeek v4-pro 支持 vision，需验证 base64 图片大小限制
4. **Insert From URL 超时**: FileMaker 默认 60s，Agent 可能执行多轮 tool call 超过此时间，需注意
