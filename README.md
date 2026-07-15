# FileMaker AI Gateway

FileMaker 与 AI Agent 之间的 REST API 网关。

## 架构

```
FileMaker → REST API → Gateway (Python) → AgentLoop → AgentRunner → LLM Provider
```

FileMaker 只需要调用 `POST /chat`，完全不知道 LLM、Prompt、Token、Tool、Memory 的存在。

## 快速开始

```bash
# 安装
pip install -e ".[dev]"

# 配置
cp .env.example .env
# 编辑 .env，填入 API Key:
# FILEMAKER_GATEWAY_PROVIDER_API_KEY=sk-your-key

# 启动 (默认 127.0.0.1:8080)
python -m filemaker_gateway

# 测试
curl http://127.0.0.1:8080/health
```

## API

### POST /chat

Request:
```json
{"session": "abc-123", "message": "帮我读取这张发票"}
```

Response:
```json
{
  "answer": "这是一张增值税发票...",
  "thinking": null,
  "tool_calls": [{"name": "ocr", "arguments": {}, "result_summary": "识别成功"}],
  "session": "abc-123",
  "stop_reason": "completed"
}
```

认证：`X-API-Key` header

### GET /health

无需认证，返回服务状态和已注册工具列表。

### GET /sessions

列出所有会话，支持 `?limit=50&offset=0`。

### GET /sessions/{id}

获取会话详情和完整消息历史。

## 已集成工具

| 工具 | 说明 | 状态 |
|------|------|------|
| `filemaker_query` | SELECT / ExecuteSQL / Find | Stub |
| `filemaker_record` | 创建/修改/删除记录 | Stub |
| `filemaker_script` | 执行 FileMaker 脚本 | Stub |
| `filemaker_layout` | 布局导航 | Stub |
| `ocr` | 图片/发票/PDF OCR | Stub |
| `sql_query` | 外部数据库查询 | Stub |

## 支持的 LLM Provider

DeepSeek / OpenAI GPT / 智谱 GLM / Claude / Gemini / Ollama

切换 Provider：修改 `config.yaml` 中 `gateway.provider.name`，配置对应的环境变量。

## 项目结构

```
filemaker_gateway/
├── api/         REST 路由、中间件、依赖注入
├── agent/       AgentLoop (编排) + AgentRunner (LLM 循环)
├── provider/    LLM Provider 抽象
├── tool/        工具插件系统
├── session/     SQLite 会话管理
├── config/      配置管理
└── security/    认证与审计
```

参考架构：[nanobot](https://github.com/HKUDS/nanobot)
