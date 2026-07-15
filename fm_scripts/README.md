# FileMaker AI Gateway — 脚本模板

本目录包含可直接在 FileMaker Script Workspace 中创建的脚本模板。

## 使用方法

1. 在 FileMaker Pro 中打开 Script Workspace（脚本工作区）
2. 按照 `.txt` 文件中的步骤逐行创建脚本
3. 根据实际布局和字段名调整脚本中的表名和字段引用
4. 修改 `$api_key` 为 Gateway 配置的实际 API Key

## 前置条件

- FileMaker AI Gateway 已启动并运行在 `http://127.0.0.1:8080`
- 如使用 AI_NL_Query，Gateway 需启用 `fm_data_api`
- 如使用 AI_OCR_Invoice，Gateway 需配置支持 Vision 的 Provider

## 脚本列表

| 脚本 | 用途 | 依赖 |
|------|------|------|
| `AI_Chat.txt` | 基础 AI 对话 | Gateway 运行即可 |
| `AI_NL_Query.txt` | 自然语言查询数据库 | fm_data_api 启用 |
| `AI_OCR_Invoice.txt` | 发票 OCR 识别 | Provider 支持 Vision |

## 配置参考

Gateway config.yaml:
```yaml
gateway:
  host: "127.0.0.1"
  port: 8080
  api_key: "filemaker-secret-key-change-me"

fm_data_api:
  enabled: true
  host: "your-fm-server.example.com"
  database: "YourDatabase"
  username: "api-user"
  password: "your-password"
```
