# Gateway 模式 vs FileMaker 直调 LLM API

FileMaker 具备通过 `Insert From URL` 直接调用 OpenAI 等 LLM API 的能力，但我们选择在中间加一层 Gateway。核心原因：**LLM 的 Tool Use 循环（模型反复调用工具直到得出最终答案）无法在 FileMaker 脚本中实现** — 这个多轮循环需要状态管理、工具执行、结果回传，FileMaker 的同步脚本模型无法承载。

Gateway 的职责是替 FileMaker 管理整个 Agent 循环：接收自然语言请求 → 拼 Prompt → 调 LLM → 解析 Tool Call → 执行 Tool → 喂回结果 → 重复 → 返回最终答案。FileMaker 只需发一句话，等结果即可。

**Considered Options**:
- FileMaker 直调 LLM API：简单但只能做单轮问答，无法使用工具
- 通过 MCP 让 AI Agent 直接操作 FM：适合 Part 3，但 Agent 循环逻辑仍然需要在外部运行

**Consequences**:
- 引入了一层网络延迟和运维负担
- API Key 集中管理在 Gateway，不暴露在 FM 脚本中
