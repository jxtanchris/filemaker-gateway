# FileMaker AI Gateway

FileMaker 与 AI Agent 之间的 REST API 中间层。Gateway 封装 LLM Tool Use 循环，让 FileMaker 只需发送自然语言请求，无需感知 Prompt、Token、Tool、Memory。

## Language

### Agent

**AgentLoop**:
编排一次对话 turn 的状态机（RESOLVE → BUILD → RUN → SAVE → RESPOND → DONE）。管 Session、Context、REST 对接，不碰 Provider 和 Tool。
_Avoid_: Orchestrator, conversation manager

**AgentRunner**:
执行 LLM Tool Calling 循环：发消息给 Provider → 收到 tool call → 执行 Tool → 把结果喂回 LLM → 重复直到得到最终答案。管 Provider 调用和 Tool 执行，不碰 Session 和 REST。
_Avoid_: Executor, agent engine

**Provider**:
LLM 后端的抽象层，兼容 OpenAI 格式的 API。支持 DeepSeek、GLM、GPT、Claude、Gemini。只负责调 LLM API，不碰 Tool 和 Session。
_Avoid_: LLM client, model adapter

**Tool**:
Agent 可以调用的能力单元。每个 Tool 有 name、description、parameters（JSON Schema）和 execute() 方法。
_Avoid_: Function, plugin, skill

**Built-in Tool**:
Python 代码定义的通用工具（如 `sql_query`、`ocr`），不依赖 FileMaker 即可运行。始终可用，即使 FM 不可达。
_Avoid_: System tool, core tool

**FM Business Tool**:
定义在 FileMaker `_tools` 表中的业务工具，对应一个 FM 脚本。Gateway 启动时从 FM 动态加载并注册。
_Avoid_: Custom tool, FM tool

**Tool Registry**:
所有可用 Tool 的集中注册表。AgentRunner 从中查找并执行 Tool。加载来源：Built-in Tools（Python 文件）+ FM Business Tools（`_tools` 表）。同名冲突时启动报错。
_Avoid_: Tool catalog, function registry

### Session

**Session**:
一次对话的上下文容器，包含消息历史、绑定的 FM 文件、元数据。持久化在 SQLite 中。
_Avoid_: Conversation, chat context

**FM File Binding**:
Session 与特定 FileMaker 数据库文件的关联。Gateway 据此知道该 Session 的 FM Business Tools 来自哪个文件。
_Avoid_: Database connection, file reference

### FileMaker 集成

**`_tools` 表**:
FileMaker 中定义业务工具的表。字段：`name`、`description`、`parameters`（JSON Schema 字符串，OpenAI function 格式）、`script_name`、`enabled`。Gateway 启动时读取此表动态注册工具。
_Avoid_: Tool definitions table, function registry

**Script Instruction**:
Gateway `POST /chat` 响应中的结构化指令，告诉 FileMaker 执行哪个脚本及参数。FileMaker 侧的 Gateway Response Handler 解析并分发执行。
_Avoid_: Command, action directive

**Gateway Response Handler**:
FileMaker 侧的统一脚本入口。解析 `POST /chat` 的 JSON 响应，按 Script Instructions 调对应业务脚本，最后把自然语言回复显示给用户。
_Avoid_: Response parser, dispatch script
