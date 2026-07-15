# POST /chat 响应同时返回自然语言和 FileMaker 脚本指令

大多数 Chat API 只返回自然语言文本。我们的 `POST /chat` 响应不仅包含 AI 的文本回复，还附带一个结构化的 Script Instructions 数组，告诉 FileMaker "接下来要执行哪些脚本"。

**为什么不是纯文本**：Agent 在 Tool Use 循环中可能发现需要 FileMaker 侧执行操作（如刷新布局、更新字段、触发工作流）。如果只返回文本，FileMaker 无法自动化这些后续操作——用户看到文字后还得手动操作。

Gateway 响应格式：`reply`（给用户看的自然语言） + `instructions`（给 FM 脚本消费的结构化指令数组）。FileMaker 的 Gateway Response Handler 解析指令、依次执行对应 FM 脚本、最后展示 reply。

**Considered Options**:
- 纯文本响应：简单但 FileMaker 无法自动化后续操作
- Gateway 直调 FM 脚本（通过 MCP/Data API）：Gateway 包办一切，但引入双向依赖——FM 调 Gateway、Gateway 又回调 FM
- 文本 + 指令分离：FileMaker 拿到结果后自行分发，单向依赖，职责清晰

**Consequences**:
- API 响应格式比纯文本 Chat API 复杂，但 FileMaker 的脚本化架构天然适配指令分发模型
- Gateway 不反向调 FM，保持单向依赖：FM → Gateway
