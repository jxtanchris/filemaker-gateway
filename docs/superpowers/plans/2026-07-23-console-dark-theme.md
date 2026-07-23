# Console 深色主题视觉升级 — 实现计划

> **For agentic workers:** 使用 subagent-driven-development 按任务逐个实现。步骤使用 checkbox (`- [ ]`) 语法追踪。

**Goal:** 将 `console.html` 从浅色主题升级为深色科技感风格，纯视觉改动，不动 JS 逻辑。

**Architecture:** 单文件 HTML (`filemaker_gateway/api/console.html`)，所有 CSS/JS 内联。仅重写 `<style>` 块 + 微调少量 HTML 结构（空状态、代码块语言标签），Google Fonts 通过 CDN 引入。

**Tech Stack:** 纯 HTML/CSS/JS，Google Fonts (Inter 400/500/600 + JetBrains Mono 400)

## Global Constraints

- 纯视觉升级，不修改 JS 逻辑
- 深蓝黑底色 `#0a0e17`，青蓝色强调 `#06b6d4`
- 侧边栏玻璃拟态 `backdrop-filter: blur(20px)`
- 所有动画 ≤ 0.3s，脉冲动画 2s
- 不新增文件，不改后端

---

### Task 1: 重写 CSS 变量和全局样式

**Files:**
- Modify: `filemaker_gateway/api/console.html` — 替换 `:root` 变量块、全局 reset、body、scrollbar、选中高亮

**Interfaces:**
- Produces: CSS 变量被后续所有 CSS 规则引用；字体通过 Google Fonts CDN 加载

- [ ] **Step 1: 替换 `<head>` 内 Google Fonts 引入 + CSS 变量**

将现有的 `<style>` 块开头的 `:root` 变量替换为新配色，并在 `<meta charset>` 后添加 Google Fonts 链接。

在 `<meta name="viewport" ...>` 之后、`<title>` 之前插入：

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono&display=swap" rel="stylesheet">
```

替换 `:root` 块：

```css
:root {
  --bg: #0a0e17;
  --surface: #141b2d;
  --sidebar-bg: rgba(15, 20, 35, 0.88);
  --text: #e2e8f0;
  --text-secondary: #94a3b8;
  --muted: #64748b;
  --accent: #06b6d4;
  --accent-hover: #0891b2;
  --accent-glow: rgba(6, 182, 212, 0.3);
  --border: rgba(255, 255, 255, 0.06);
  --border-light: rgba(255, 255, 255, 0.1);
  --user-bubble: linear-gradient(135deg, #0ea5e9, #06b6d4);
  --user-text: #fff;
  --bot-bubble: #1a2332;
  --bot-border: rgba(6, 182, 212, 0.15);
  --bot-text: #e2e8f0;
  --error: #ef4444;
  --error-bg: rgba(239, 68, 68, 0.1);
  --tool-bg: rgba(6, 182, 212, 0.08);
  --tool-border: rgba(6, 182, 212, 0.2);
  --input-bg: #0f172a;
  --code-bg: #0c1220;
  --green: #22c55e;
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
}
```

- [ ] **Step 2: 替换全局 reset 和 body 样式**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: var(--font-sans);
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  display: flex;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
::selection { background: var(--accent-glow); color: #fff; }
a { color: var(--accent); text-decoration: underline; }
```

- [ ] **Step 3: 添加自定义滚动条样式**

在 `body` 规则之后添加：

```css
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.08); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.16); }
```

- [ ] **Step 4: 启动服务验证变量生效**

```bash
# 重启服务
kill $(lsof -ti :8080) 2>/dev/null; sleep 1
python -m filemaker_gateway &
sleep 3
curl -s http://localhost:8080/ | grep -o 'var(--bg)' | head -1
```

预期: 页面返回包含 `var(--bg)` 的新 CSS。

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/api/console.html
git commit -m "feat(console): replace CSS variables and global styles for dark theme"
```

---

### Task 2: 侧边栏视觉升级

**Files:**
- Modify: `filemaker_gateway/api/console.html` — 侧边栏相关 CSS + HTML 结构微调

**Interfaces:**
- Consumes: Task 1 的 CSS 变量
- Produces: 侧边栏样式，供页面整体使用

- [ ] **Step 1: 替换侧边栏 CSS**

将现有 sidebar 相关 CSS（`.sidebar` 到 `.badge-live`）替换为：

```css
/* Sidebar */
.sidebar {
  width: 260px; background: var(--sidebar-bg); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0;
}
.sidebar-header { padding: 20px 16px 16px; border-bottom: 1px solid var(--border); }
.sidebar-header h1 {
  font-size: 16px; font-weight: 600; background: linear-gradient(135deg, #0ea5e9, #06b6d4);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  text-shadow: 0 0 20px rgba(6, 182, 212, 0.3);
}
.sidebar-header .ver { font-size: 11px; color: var(--muted); margin-top: 4px; }
.sidebar-stats { padding: 14px 16px; font-size: 12px; color: var(--text-secondary); border-bottom: 1px solid var(--border); }
.sidebar-stats span { display: block; margin-bottom: 3px; }
.sidebar-stats .dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--green); margin-right: 6px; animation: pulse 2s ease-in-out infinite; }
.sidebar-body { flex: 1; overflow-y: auto; padding: 8px; }
.sidebar-body .section-title { font-size: 10px; text-transform: uppercase; color: var(--muted); padding: 12px 8px 6px; letter-spacing: 1px; font-weight: 500; }
.tool-item {
  display: flex; align-items: center; gap: 8px; padding: 7px 10px;
  border-radius: 8px; font-size: 13px; cursor: default; color: var(--text-secondary);
  transition: background 0.2s ease, color 0.2s ease;
}
.tool-item:hover { background: rgba(6, 182, 212, 0.08); color: var(--text); }
.tool-item .icon { font-size: 15px; }
.tool-item .badge { margin-left: auto; width: 6px; height: 6px; border-radius: 50%; background: var(--green); box-shadow: 0 0 6px rgba(34, 197, 94, 0.5); }
```

- [ ] **Step 2: 更新侧边栏 HTML 中 badge 内容**

将侧边栏中 `live` 文字 badge 改为纯圆点。找到 JS 中 `innerHTML` 的这行：

```javascript
div.innerHTML = `<span class="icon">${icons[t]||'🔧'}</span>${t}<span class="badge badge-live">live</span>`;
```

改为：

```javascript
div.innerHTML = `<span class="icon">${icons[t]||'🔧'}</span>${t}<span class="badge"></span>`;
```

- [ ] **Step 3: 更新侧边栏统计区**

将 `sidebar-stats` 中 status 行从直接文字改为用 JS 动态填充（让初始化时就有正确样式）。保持 HTML 结构不变，确认 `tool-count` span 在 JS fetch health 后被正确填充。

- [ ] **Step 4: 刷新浏览器验证侧边栏**

启动服务后打开 `http://localhost:8080/`，确认：
- 侧边栏半透明毛玻璃效果
- 标题有青色渐变 + 发光
- 绿色指示灯脉冲动画
- 工具项 hover 亮起

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/api/console.html
git commit -m "feat(console): upgrade sidebar with glassmorphism and cyan accents"
```

---

### Task 3: 顶部栏和消息气泡重设计

**Files:**
- Modify: `filemaker_gateway/api/console.html` — Header、Messages、气泡相关 CSS

**Interfaces:**
- Consumes: Task 1 CSS 变量
- Produces: 顶部栏和消息气泡样式

- [ ] **Step 1: 替换顶部栏 CSS**

将现有 `.header` 到 `.header button:hover` 替换为：

```css
/* Header */
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.header {
  padding: 14px 20px; background: var(--bg); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--text-secondary);
}
.header input {
  border: 1px solid var(--border-light); border-radius: 8px; padding: 5px 12px;
  font-size: 13px; width: 200px; outline: none; background: var(--input-bg); color: var(--text);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.header input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
.header button {
  font-size: 12px; padding: 5px 14px; border-radius: 8px; border: 1px solid var(--border-light);
  background: transparent; cursor: pointer; color: var(--text-secondary);
  transition: border-color 0.2s ease, color 0.2s ease, background 0.2s ease;
}
.header button:hover { border-color: var(--accent); color: var(--text); background: rgba(6, 182, 212, 0.05); }
```

- [ ] **Step 2: 替换消息区 CSS**

将现有 `.messages` 到 `.tool-call .tc-args` 替换为：

```css
/* Messages */
.messages { flex: 1; overflow-y: auto; padding: 24px 20px; display: flex; flex-direction: column; gap: 16px; }
.msg { max-width: 80%; animation: fadeInUp 0.3s ease-out; }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.msg.user { align-self: flex-end; }
.msg.user .bubble {
  background: var(--user-bubble); color: var(--user-text);
  border-radius: 18px 18px 4px 18px; padding: 12px 18px;
  font-size: 14px; line-height: 1.5; box-shadow: 0 4px 12px rgba(6, 182, 212, 0.25);
}
.msg.assistant { align-self: flex-start; }
.msg.assistant .bubble {
  background: var(--bot-bubble); color: var(--bot-text);
  border-radius: 18px 18px 18px 4px; padding: 14px 18px;
  font-size: 14px; line-height: 1.65; border: 1px solid var(--bot-border);
  min-width: 200px;
}
.msg.assistant .bubble p { margin-bottom: 10px; }
.msg.assistant .bubble p:last-child { margin-bottom: 0; }
.msg.assistant .bubble pre {
  background: var(--code-bg); border-radius: 10px; padding: 14px;
  font-size: 12px; overflow-x: auto; margin: 10px 0;
  border: 1px solid var(--border);
  position: relative;
}
.msg.assistant .bubble pre .lang-tag {
  position: absolute; top: 0; right: 0; font-size: 10px;
  color: var(--muted); background: rgba(255,255,255,0.04);
  padding: 2px 8px; border-radius: 0 10px 0 6px;
  font-family: var(--font-mono); text-transform: uppercase;
}
.msg.assistant .bubble code {
  font-family: var(--font-mono); font-size: 12px;
  background: rgba(255,255,255,0.06); padding: 2px 5px; border-radius: 4px;
}
.msg.assistant .bubble pre code { background: none; padding: 0; border-radius: 0; }
.msg.assistant .bubble strong { font-weight: 600; color: #f1f5f9; }

/* Tables in messages */
.msg.assistant .bubble table {
  width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px;
  border-radius: 8px; overflow: hidden; border: 1px solid var(--border);
}
.msg.assistant .bubble thead { background: rgba(6, 182, 212, 0.08); }
.msg.assistant .bubble th {
  padding: 8px 12px; text-align: left; font-weight: 600; font-size: 11px;
  color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px;
  border-bottom: 2px solid rgba(6, 182, 212, 0.2);
}
.msg.assistant .bubble td {
  padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top;
  color: var(--text-secondary);
}
.msg.assistant .bubble tr:last-child td { border-bottom: none; }
.msg.assistant .bubble tr:hover td { background: rgba(255,255,255,0.02); }

/* Lists */
.msg.assistant .bubble ul, .msg.assistant .bubble ol { margin: 8px 0; padding-left: 20px; color: var(--text-secondary); }
.msg.assistant .bubble li { margin-bottom: 4px; }
.msg.assistant .bubble li::marker { color: var(--accent); }

/* Tool calls in messages */
.tool-call {
  margin: 8px 0; padding: 10px 14px; background: var(--tool-bg);
  border: 1px solid var(--tool-border); border-radius: 8px; font-size: 12px;
}
.tool-call .tc-name { font-weight: 600; color: var(--accent); }
.tool-call .tc-args { color: var(--muted); font-family: var(--font-mono); font-size: 11px; margin-top: 2px; word-break: break-all; }

/* Typing indicator */
.typing {
  align-self: flex-start; display: flex; gap: 4px; padding: 12px 18px;
}
.typing .dot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--muted);
  animation: bounce 1.4s ease-in-out infinite;
}
.typing .dot:nth-child(2) { animation-delay: 0.2s; }
.typing .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }
```

- [ ] **Step 3: 替换思考中（typing）指示器的 JS 生成逻辑**

找到 `sendMessage()` 中创建 typing 的代码：

```javascript
const typing = document.createElement('div');
typing.className = 'typing';
typing.textContent = '思考中…';
```

改为三个跳动圆点：

```javascript
const typing = document.createElement('div');
typing.className = 'typing';
typing.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
```

- [ ] **Step 4: 服务运行中刷新浏览器验证**

确认:
- 用户气泡青色渐变 + 发光阴影
- AI 气泡深色底 + 青色边框
- 表格暗色表头
- 代码块深色背景
- typing 指示器三点跳动

- [ ] **Step 5: Commit**

```bash
git add filemaker_gateway/api/console.html
git commit -m "feat(console): redesign header, message bubbles, and typing indicator"
```

---

### Task 4: 输入区和媒体预览重设计

**Files:**
- Modify: `filemaker_gateway/api/console.html` — 输入区、发送按钮、图片按钮、媒体预览 CSS

**Interfaces:**
- Consumes: Task 1 CSS 变量
- Produces: 输入区样式

- [ ] **Step 1: 替换输入区和媒体预览 CSS**

将现有 `.input-area` 到 `.media-preview .chip button` 替换为：

```css
/* Input */
.input-area {
  padding: 14px 20px; background: var(--surface); border-top: 1px solid var(--border);
  display: flex; gap: 10px; align-items: flex-end;
}
.input-area textarea {
  flex: 1; border: 1px solid var(--border-light); border-radius: 14px; padding: 12px 16px;
  font-size: 14px; resize: none; outline: none; font-family: var(--font-sans); line-height: 1.5;
  min-height: 46px; max-height: 120px; background: var(--input-bg); color: var(--text);
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
  box-shadow: inset 0 2px 4px rgba(0,0,0,0.3);
}
.input-area textarea:focus { border-color: var(--accent); box-shadow: inset 0 2px 4px rgba(0,0,0,0.3), 0 0 0 3px var(--accent-glow); }
.input-area textarea::placeholder { color: var(--muted); }
.input-area button {
  background: linear-gradient(135deg, #0ea5e9, #06b6d4);
  color: #fff; border: none; border-radius: 14px;
  padding: 12px 22px; font-size: 14px; cursor: pointer; font-weight: 500;
  flex-shrink: 0; transition: filter 0.2s ease, transform 0.15s ease;
}
.input-area button:hover { filter: brightness(1.1); transform: translateY(-1px); }
.input-area button:disabled { opacity: 0.4; cursor: not-allowed; filter: none; transform: none; }
.input-area .media-btn {
  background: transparent; color: var(--text-secondary); border: 1px solid var(--border-light);
  border-radius: 14px; padding: 12px 14px; font-size: 18px; cursor: pointer;
  transition: border-color 0.2s ease, transform 0.3s ease, color 0.2s ease;
}
.input-area .media-btn:hover { border-color: var(--accent); color: var(--text); transform: rotate(15deg); }

/* Media preview */
.media-preview { display: flex; gap: 6px; flex-wrap: wrap; padding: 0 20px 6px; }
.media-preview .chip {
  background: var(--input-bg); border: 1px solid var(--border-light); border-radius: 8px;
  padding: 4px 10px; font-size: 11px; display: flex; align-items: center; gap: 6px;
  color: var(--text-secondary);
}
.media-preview .chip button { background: none; border: none; cursor: pointer; font-size: 14px; color: var(--muted); padding: 0; line-height: 1; }
.media-preview .chip button:hover { color: var(--error); }
```

- [ ] **Step 2: 刷新浏览器验证输入区**

确认:
- 输入框凹入内阴影
- 聚焦时青色光晕
- 发送按钮渐变 + hover 微升
- 图片按钮 hover 旋转

- [ ] **Step 3: Commit**

```bash
git add filemaker_gateway/api/console.html
git commit -m "feat(console): redesign input area with glow effects and gradient send button"
```

---

### Task 5: 弹窗、空状态、动画收尾

**Files:**
- Modify: `filemaker_gateway/api/console.html` — 弹窗 CSS、空状态 HTML、动画 keyframes

**Interfaces:**
- Consumes: Task 1-4 的所有样式
- Produces: 完成的深色主题控制台

- [ ] **Step 1: 替换弹窗 CSS**

将现有 `#sessionModal` 和内部元素的内联 style 提取为 CSS：

```css
/* Modal */
.modal-overlay {
  display: none; position: fixed; inset: 0; background: rgba(0, 0, 0, 0.65);
  z-index: 100; justify-content: center; align-items: center;
  backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
}
.modal-overlay.open { display: flex; animation: fadeIn 0.2s ease-out; }
.modal-box {
  background: var(--sidebar-bg); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
  border-radius: 16px; padding: 24px; width: 420px; max-height: 80vh; overflow-y: auto;
  border: 1px solid var(--border); box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  animation: scaleIn 0.2s ease-out;
}
@keyframes scaleIn { from { transform: scale(0.95); opacity: 0; } to { transform: scale(1); opacity: 1; } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.modal-header h3 { font-size: 15px; font-weight: 600; }
.modal-close {
  background: none; border: none; font-size: 22px; cursor: pointer; color: var(--muted);
  transition: transform 0.3s ease, color 0.2s ease; width: 32px; height: 32px;
  border-radius: 8px; display: flex; align-items: center; justify-content: center;
}
.modal-close:hover { transform: rotate(90deg); color: var(--text); background: rgba(255,255,255,0.05); }
.session-item {
  padding: 12px; border: 1px solid var(--border); border-radius: 10px; margin-bottom: 8px;
  cursor: pointer; transition: border-color 0.2s ease, background 0.2s ease;
  border-left: 3px solid transparent;
}
.session-item:hover { border-color: var(--accent); background: rgba(6, 182, 212, 0.04); border-left-color: var(--accent); }
.session-item .sess-id { font-weight: 500; font-size: 13px; color: var(--text); }
.session-item .sess-meta { font-size: 11px; color: var(--muted); margin-top: 3px; }
```

- [ ] **Step 2: 更新弹窗 HTML 结构**

将现有的 `#sessionModal` div 替换为使用新 CSS class：

```html
<!-- Session List Modal -->
<div class="modal-overlay" id="sessionModal">
  <div class="modal-box">
    <div class="modal-header">
      <h3>📋 会话列表</h3>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div id="sessionList"></div>
  </div>
</div>
```

- [ ] **Step 3: 更新弹窗相关 JS**

在 `<script>` 末尾添加 `closeModal` 函数，并更新 `loadSessions` 中的 innerHTML 使用新 class：

添加函数：

```javascript
function closeModal() {
  document.getElementById('sessionModal').classList.remove('open');
}
```

更新 `loadSessions` 中设置 modal display 的方式：

```javascript
// 将 modal.style.display = 'flex' 改为:
modal.classList.add('open');
```

并将 session 列表项的 innerHTML 改为：

```javascript
list.innerHTML = sessions.map(s => `
  <div class="session-item"
       onclick="document.getElementById('sessionId').value='${s.id}';closeModal();loadSessionDetail('${s.id}')">
    <div class="sess-id">${s.id}</div>
    <div class="sess-meta">${s.message_count} 条消息 · ${new Date(s.updated_at).toLocaleString()}</div>
  </div>
`).join('');
```

同时更新 `newSession()` 中关闭 modal 的方式（如果有的话将 `style.display='none'` 改为 `classList.remove('open')`）。

- [ ] **Step 4: 更新空状态 HTML**

将 messages 区域初始的空状态从普通 emoji 文字改为带发光效果的版本：

```html
<div class="messages" id="messages">
  <div style="text-align:center;color:var(--muted);margin-top:80px">
    <div style="font-size:56px;margin-bottom:20px;opacity:0.6">
      <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <polygon points="32,6 58,19 58,45 32,58 6,45 6,19" stroke="#06b6d4" stroke-width="1.5"
                 fill="none" opacity="0.6"/>
        <polygon points="32,14 50,23 50,41 32,50 14,41 14,23" stroke="#06b6d4" stroke-width="1"
                 fill="none" opacity="0.3"/>
      </svg>
    </div>
    <div style="font-size:16px;font-weight:500;margin-bottom:6px;color:var(--text-secondary)">FileMaker AI Gateway</div>
    <div style="font-size:13px">输入消息开始与 AI 对话</div>
  </div>
</div>
```

- [ ] **Step 5: 添加脉冲动画 keyframes**（如果尚未在 Task 2 中添加）

确认 `@keyframes pulse` 存在于 CSS 中：

```css
@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.3); opacity: 0.7; }
}
```

- [ ] **Step 6: 更新代码块渲染以支持语言标签**

更新 `renderMarkdown` 中的代码块处理，提取语言标签：

```javascript
// 将原来的:
// html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
// 替换为:
html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, function(match, lang, code) {
  var langTag = lang ? '<span class="lang-tag">' + lang + '</span>' : '';
  return '<pre>' + langTag + '<code>' + code + '</code></pre>';
});
```

- [ ] **Step 7: 最终验证 — 全功能测试**

```bash
# 检查服务在跑
curl -s http://localhost:8080/health | python -m json.tool
```

然后打开 `http://localhost:8080/`：
- 确认深色主题全局生效
- 侧边栏毛玻璃效果
- 发送一条测试消息确认聊天功能正常
- 打开会话历史弹窗确认样式正确
- 检查思考中三点动画

- [ ] **Step 8: Commit**

```bash
git add filemaker_gateway/api/console.html
git commit -m "feat(console): finish modal, empty state, animations, and code block language tags"
```

---

### Task 6: 截屏验证和最终确认

**Files:**
- 无新建/修改文件

**Interfaces:**
- Consumes: Task 5 完整页面

- [ ] **Step 1: 使用 webapp-testing 截屏**

```bash
# 确保服务在跑
python -m filemaker_gateway &
sleep 3
```

用 Playwright 打开 `http://localhost:8080/`，截取以下场景：
1. 初始页面（空状态 + 侧边栏）
2. 发送一条消息后的聊天界面
3. 会话列表弹窗

- [ ] **Step 2: 对照 spec 检查**

对比设计规格文档，逐项确认：
- [ ] 配色: 深蓝黑底 `#0a0e17`，青色强调 `#06b6d4`
- [ ] 侧边栏: 玻璃拟态 + backdrop-blur
- [ ] 用户气泡: 青色渐变 + 发光阴影
- [ ] AI 气泡: 深色底 + 青色微边框
- [ ] 输入框: 凹入内阴影 + 聚焦光晕
- [ ] 弹窗: 玻璃拟态 + scale 动画
- [ ] 思考指示器: 三点跳动
- [ ] 代码块: 深色背景 + 语言标签
- [ ] 指示灯: 绿色脉冲
- [ ] 滚动条: 自定义暗色

- [ ] **Step 3: 确认无回归**

运行后端测试确保无破坏：

```bash
python -m pytest tests/ -v
```

- [ ] **Step 4: 最终 commit（如有微调）**

```bash
git add -A && git diff --cached --stat
# 如果有改动则 commit
```
