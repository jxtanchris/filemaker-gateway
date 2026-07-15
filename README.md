# FileMaker AI Gateway

FileMaker 与 AI Agent 之间的 REST API 中间层。Gateway 作为"翻译官"，让 FileMaker 只需调用 `POST /chat`，无需知道 LLM、Prompt、Token、Tool、Memory 的存在。

## 架构

```
FileMaker ←──→ REST API ←──→ AgentLoop ←──→ AgentRunner ←──→ LLM Provider
    │                              │                │
    │  Insert From URL             │  Session       │  Tool Calls
    │  (FM → Gateway)              │  Management    │  (function calling)
    │                              │                │
    └──────────────────────────────┴────────────────┘
                   │
            FileMaker Data API (Gateway → FM)
            CRUD / Find / Script / Container
```

**双向通信**：
1. **FM → Gateway**: FileMaker 通过 `Insert From URL` 调用 `POST /chat`
2. **Gateway → FM**: Agent 通过 FileMaker Data API 读写数据、执行脚本

## 快速开始

```bash
# 1. 安装
pip install -e ".[dev]"

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入:
#   FILEMAKER_GATEWAY_PROVIDER_API_KEY=sk-your-key
#   FILEMAKER_GATEWAY_API_KEY=your-gateway-api-key

# 3. 启动 (默认 http://127.0.0.1:8080)
python -m filemaker_gateway

# 4. 验证
curl http://127.0.0.1:8080/health
```

### 启用 FileMaker Data API（可选）

编辑 `config.yaml` 或设置环境变量：

```yaml
# config.yaml
fm_data_api:
  enabled: true
  host: "your-fm-server.example.com"
  database: "YourDatabase"
  username: "api-user"
  password: ""  # 推荐用环境变量
```

```bash
export FILEMAKER_GATEWAY_FM_DATA_API_ENABLED=true
export FILEMAKER_GATEWAY_FM_DATA_API_HOST=fm.example.com
export FILEMAKER_GATEWAY_FM_DATA_API_DATABASE=MyDB
export FILEMAKER_GATEWAY_FM_DATA_API_USERNAME=admin
export FILEMAKER_GATEWAY_FM_DATA_API_PASSWORD=secret
```

> 未启用时 FM Tools 会返回友好错误 `"FM Data API 未启用 (fm_data_api.enabled=false)"`，不影响 Gateway 其他功能。

## API

### POST /chat

```bash
curl -X POST http://127.0.0.1:8080/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-gateway-api-key" \
  -d '{"session": "user-1", "message": "帮我查一下所有北京客户"}'
```

Response:
```json
{
  "answer": "查询到 3 个北京客户：张三、李四、王五",
  "thinking": null,
  "tool_calls": [
    {"name": "filemaker_query", "arguments": {"action": "find", "layout": "Contacts", "query": "[{\"city\":\"北京\"}]"}}
  ],
  "session": "user-1",
  "stop_reason": "completed"
}
```

带图片的请求（OCR / Vision）：

```json
{
  "session": "ocr-1",
  "message": "识别这张发票",
  "media": ["data:image/png;base64,iVBORw0KGgo..."]
}
```

### 其他端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查，返回服务状态和已注册工具 |
| GET | `/sessions` | 列出所有会话（支持 `?limit=50&offset=0`） |
| GET | `/sessions/{id}` | 获取会话详情和完整消息历史 |

所有 `/chat` 和 `/sessions` 端点需要 `X-API-Key` header。

## 工具

| 工具 | 说明 | 状态 |
|------|------|------|
| `filemaker_query` | SELECT / Find 查询 FM 数据 | ✅ 真实 Data API |
| `filemaker_record` | 创建 / 更新 / 删除 FM 记录 | ✅ 真实 Data API |
| `filemaker_script` | 执行 FileMaker 脚本 | ✅ 真实 Data API |
| `filemaker_layout` | 列出布局 / 查看布局元数据 | ✅ 真实 Data API |
| `ocr` | 图片识别 / 发票 OCR / PDF | ✅ LLM Vision |
| `echo` | 回显测试 | ✅ 始终可用 |
| `sql_query` | 外部数据库查询 | ⏳ Stub（后续） |

## 配置

### 环境变量

所有配置可通过 `FILEMAKER_GATEWAY_*` 前缀的环境变量覆盖：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `FILEMAKER_GATEWAY_HOST` | 监听地址 | `127.0.0.1` |
| `FILEMAKER_GATEWAY_PORT` | 监听端口 | `8080` |
| `FILEMAKER_GATEWAY_API_KEY` | API 认证密钥 | — |
| `FILEMAKER_GATEWAY_PROVIDER_NAME` | LLM Provider | `deepseek` |
| `FILEMAKER_GATEWAY_PROVIDER_API_KEY` | LLM API Key | — |
| `FILEMAKER_GATEWAY_PROVIDER_MODEL` | 模型名称 | `deepseek-v4-pro` |
| `FILEMAKER_GATEWAY_PROVIDER_API_BASE` | API 地址（可选） | — |
| `FILEMAKER_GATEWAY_DATABASE_URL` | SQLite 路径 | `sqlite+aiosqlite:///./data/sessions.db` |
| `FILEMAKER_GATEWAY_FM_DATA_API_ENABLED` | 启用 FM Data API | `false` |
| `FILEMAKER_GATEWAY_FM_DATA_API_HOST` | FM Server 地址 | — |
| `FILEMAKER_GATEWAY_FM_DATA_API_DATABASE` | FM 数据库名 | — |
| `FILEMAKER_GATEWAY_FM_DATA_API_USERNAME` | FM 用户名 | — |
| `FILEMAKER_GATEWAY_FM_DATA_API_PASSWORD` | FM 密码 | — |

完整配置见 `config.yaml`。

### Provider 切换

支持所有 OpenAI 兼容 API：DeepSeek、OpenAI GPT、智谱 GLM、Claude、Gemini、Ollama 等。

```yaml
# config.yaml
gateway:
  provider:
    name: "openai"          # 或 deepseek / glm / claude / gemini / ollama
    model: "gpt-4o"
    api_key: ""             # 推荐用环境变量
    api_base: ""            # 可选，自定义 API 地址
```

## FileMaker 集成

`fm_scripts/` 目录提供了可直接在 FileMaker Script Workspace 中创建的脚本模板：

| 脚本 | 用途 | 依赖 |
|------|------|------|
| `AI_Chat.txt` | 基础 AI 对话 | Gateway 运行即可 |
| `AI_NL_Query.txt` | 自然语言查询数据库 | fm_data_api 启用 |
| `AI_OCR_Invoice.txt` | 发票 OCR 识别 + 结构化提取 | Provider 支持 Vision |

使用方法见 `fm_scripts/README.md`。

## 项目结构

```
filemaker_gateway/
├── api/            REST 路由、中间件、请求/响应模型
├── agent/          AgentLoop（编排状态机）+ AgentRunner（LLM 工具循环）
├── provider/       LLM Provider 抽象（OpenAI 兼容）
├── tool/           工具插件系统（自动发现、依赖注入）
│   └── filemaker/   FileMaker Data API 工具
├── fm/             FileMaker Data API 客户端（httpx, token 管理）
├── session/        SQLite 会话持久化
├── config/         配置管理（YAML + 环境变量）
├── security/       API Key 认证 + 审计
└── main.py         应用工厂 + 启动装配

fm_scripts/         FileMaker 脚本模板
docs/               设计文档 + 实现计划
tests/              测试（78 个, pytest + pytest-httpx）
```

## 状态机

AgentLoop 每个 turn 经过 6 个状态：

```
RESOLVE → BUILD → RUN → SAVE → RESPOND → DONE
```

- **RESOLVE**: 查找或创建会话，加载历史
- **BUILD**: 组装 messages（含 system prompt、历史、vision media）
- **RUN**: 委托 AgentRunner 执行 LLM 工具循环
- **SAVE**: 持久化本轮消息到 SQLite
- **RESPOND**: 构建 API 响应
- **DONE**: 返回

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
python -m pytest tests/ -v

# 单独模块
python -m pytest tests/test_fm/ -v
python -m pytest tests/test_tool/ -v
python -m pytest tests/test_agent/ -v

# 启动（开发模式）
python -m filemaker_gateway
```

测试使用 mock provider，不需要真实 API key，不需要真实 FM Server。

## 参考

- 架构灵感：[nanobot](https://github.com/HKUDS/nanobot)
- LLM API：OpenAI Chat Completions 格式
- FileMaker 集成：FileMaker Data API + Insert From URL
