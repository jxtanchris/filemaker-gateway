# FM 驱动工具注册——工具定义存在 FileMaker 表中

传统的 Agent 框架在代码中定义 Tool（Python 子类），但我们选择让 FileMaker 拥有工具定义的"主权"。FM Business Tools 的定义存在 FileMaker 的 `_tools` 表中，Gateway 启动时动态拉取并注册。

**为什么不在代码里定义**：Gateway 是通用中间层，FileMaker 管理员应该能自行增删改业务工具而不需要改 Gateway 代码、重新部署。

`_tools` 表使用 OpenAI function calling 格式（`name`、`description`、`parameters` JSON Schema），与 LLM 协议直接对齐，Gateway 零转换。

**Considered Options**:
- Python 代码定义所有工具：部署需改 Gateway 代码，FM 管理员无法自助
- YAML 配置文件：比 Python 好但仍需文件管理，不如 FM 表直观
- FM 表驱动：FM 管理员用熟悉的界面管理工具，动态生效

**Consequences**:
- Gateway 启动依赖 FM 可达（降级方案：Built-in Tools 始终可用，FM 工具拉不到时打 warning）
- 工具缓存至 SQLite，FM 不可达时用缓存恢复
- 同名工具冲突（Built-in vs FM Business）启动时报错，强制改名
