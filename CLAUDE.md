# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

FileMaker AI Gateway — FileMaker 与 AI Agent 之间的 REST API 中间层。Gateway 作为"翻译官"，让 FileMaker 只需调用 `POST /chat`，无需知道 LLM、Prompt、Token、Tool、Memory 的存在。

架构：`FileMaker → REST API → AgentLoop → AgentRunner → Provider (LLM)`

参考项目: [nanobot](https://github.com/HKUDS/nanobot)，采用其核心 Agent 模式。

## 启动命令

```bash
# 安装依赖
pip install -e ".[dev]"

# 复制配置文件并填入 API Key
cp .env.example .env
# 编辑 .env: FILEMAKER_GATEWAY_PROVIDER_API_KEY=sk-xxx

# 启动服务
python -m filemaker_gateway

# 运行测试
python -m pytest tests/ -v
```

## 核心架构

### 分层设计（最重要）

```
api/       → REST 层，只处理 HTTP 请求/响应
agent/     → AgentLoop (turn 编排) + AgentRunner (LLM 工具循环)
provider/  → LLM 后端抽象，支持 DeepSeek/GLM/GPT/Claude/Gemini
tool/      → 工具插件系统，自动发现
session/   → SQLite 会话管理
config/    → YAML + 环境变量配置
security/  → API Key 认证 + 审计
```

### 关键分离原则

- **AgentLoop** (`agent/loop.py`): 管 Session、Context、REST 对接。**不碰 Provider 和 Tool**
- **AgentRunner** (`agent/runner.py`): 管 Provider 调用、Tool 执行。**不碰 Session 和 REST**
- **Provider**: 管 LLM API 调用。**不碰 Tool 和 Session**
- **Tool**: 管具体能力实现。**不碰 LLM 和 Session**
- **SessionManager**: 管 SQLite 持久化。**不碰 Provider、Tool、Runner**

### 状态机

AgentLoop 处理每个 turn 的状态机：`RESOLVE → BUILD → RUN → SAVE → RESPOND → DONE`

### Tool 系统

- 基类: `tool/base.py` — `Tool` ABC + `ToolResult`
- 注册: `tool/registry.py` — `ToolRegistry`
- 发现: `tool/loader.py` — `ToolLoader` 自动扫描 `tool/` 包下所有 `Tool` 子类
- 新增 Tool: 在 `tool/` 目录下创建文件，继承 `Tool` 实现 `name/description/parameters/execute()`，重启即可自动加载

### Provider 系统

- `provider/specs.py` 定义已知 Provider 元数据
- `provider/openai_compat.py` 兼容所有 OpenAI 格式的 API
- 新增 Provider: 在 `specs.py` 添加 `ProviderSpec`，无需改其他代码
- 配置通过 `config.yaml` 的 `gateway.provider.name` 切换

## 关键文件

| 文件 | 作用 |
|------|------|
| `filemaker_gateway/main.py` | FastAPI 应用工厂，装配所有组件 |
| `filemaker_gateway/agent/loop.py` | AgentLoop 状态机 |
| `filemaker_gateway/agent/runner.py` | AgentRunner LLM 工具循环 |
| `filemaker_gateway/api/router.py` | REST 路由定义 |
| `filemaker_gateway/tool/base.py` | Tool 基类和 ToolResult |
| `filemaker_gateway/provider/openai_compat.py` | OpenAI 兼容 Provider |
| `filemaker_gateway/session/manager.py` | Session 业务逻辑 |
| `config.yaml` | 默认配置文件 |

## Part 2 vs Part 3 边界

Part 2 (当前)：
- Gateway 独立运行，REST API 可用
- 所有 Tool 可被 Agent 调用
- FileMaker 4 个 Tool 是 stub（占位返回）
- Session 持久化到 SQLite

Part 3 (未来)：
- FileMaker Tools 通过 proofkit-mcp 真正操作 FM 数据
- FileMaker `Insert From URL` 集成
- 容器字段上传 + OCR
- AI 工作流

## 测试

```bash
# 全部测试
python -m pytest tests/ -v

# 单独模块
python -m pytest tests/test_agent/ -v
python -m pytest tests/test_tool/ -v
```

测试使用 mock provider，不需要真实 API key。

## Agent skills

### Issue tracker

Issues 托管在 GitHub Issues，使用 `gh` CLI 操作。详见 `docs/agents/issue-tracker.md`。

### Triage labels

使用五个规范 triage 标签：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。详见 `docs/agents/triage-labels.md`。

### Domain docs

Single-context 布局：根目录 `CONTEXT.md` + `docs/adr/`。详见 `docs/agents/domain.md`。
