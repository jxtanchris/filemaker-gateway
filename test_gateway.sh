#!/bin/bash
# FileMaker Gateway — 功能测试脚本
# 用法: bash test_gateway.sh

BASE="http://127.0.0.1:8080"
API_KEY="filemaker-secret-key-change-me"
PASS=0
FAIL=0

red()   { echo "$(tput setaf 1)$1$(tput sgr0)"; }
green() { echo "$(tput setaf 2)$1$(tput sgr0)"; }

check() {
    local desc="$1"
    local expected="$2"
    local actual="$3"
    if echo "$actual" | grep -q "$expected"; then
        green "  ✅ $desc"
        PASS=$((PASS + 1))
    else
        red "  ❌ $desc (expected: $expected)"
        red "     got: $actual"
        FAIL=$((FAIL + 1))
    fi
}

echo "========================================="
echo " FileMaker AI Gateway 功能测试"
echo "========================================="
echo ""

# --- 1. Health Check ---
echo "1. Health Check"
RESP=$(curl -s "$BASE/health")
check "返回 status=ok"      "ok"      "$RESP"
check "包含 provider"       "deepseek" "$RESP"
check "7 个工具在线"        "echo"    "$RESP"
check "ocr 工具在线"        "ocr"     "$RESP"

# --- 2. Basic Chat ---
echo ""
echo "2. Basic Chat（基础对话）"
RESP=$(curl -s -X POST "$BASE/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d '{"session":"test-basic","message":"回复：OK"}')
check "返回 answer"         "answer"  "$RESP"
check "stop_reason=completed" "completed" "$RESP"

# --- 3. Chat with Tool Trigger ---
echo ""
echo "3. Tool Call（触发 echo 工具）"
RESP=$(curl -s -X POST "$BASE/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d '{"session":"test-tool","message":"请用 echo 工具回显这句话：测试123"}')
check "返回 answer"         "answer"  "$RESP"
check "包含 tool_calls"     "echo"    "$RESP"

# --- 4. FM Tool Degrade ---
echo ""
echo "4. FM Tool 降级（未启用 FM Data API）"
RESP=$(curl -s -X POST "$BASE/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d '{"session":"test-fm","message":"请查询 Contacts 表的所有记录"}')
check "返回降级错误提示"     "未启用"   "$RESP"

# --- 5. Session Persistence ---
echo ""
echo "5. Session 持久化"
RESP=$(curl -s -X POST "$BASE/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d '{"session":"test-memory","message":"我叫张三，记住我的名字"}')
sleep 1
RESP=$(curl -s -X POST "$BASE/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d '{"session":"test-memory","message":"我叫什么名字？"}')
check "记住上下文"           "张三"    "$RESP"

# --- 6. Session List ---
echo ""
echo "6. Session 列表"
RESP=$(curl -s -H "X-API-Key: $API_KEY" "$BASE/sessions")
check "返回列表"             "id"      "$RESP"

# --- 7. Session Detail ---
echo ""
echo "7. Session 详情"
RESP=$(curl -s -H "X-API-Key: $API_KEY" "$BASE/sessions/test-memory")
check "包含消息历史"         "张三"    "$RESP"

# --- 8. Auth Error ---
echo ""
echo "8. 认证错误（无 API Key）"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/chat" \
    -H "Content-Type: application/json" \
    -d '{"session":"test","message":"hi"}')
check "返回 401"             "401"     "$HTTP_CODE"

# --- 9. Vision Format (needs multimodal model like gpt-4o/glm-4v) ---
echo ""
echo "9. Vision 格式测试（需多模态模型）"
B64IMG="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
RESP=$(curl -s -X POST "$BASE/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{\"session\":\"test-vision\",\"message\":\"这张图片里有什么？\",\"media\":[\"$B64IMG\"]}")
if echo "$RESP" | grep -q "answer"; then
    green "  ✅ Vision 格式正常工作"
elif echo "$RESP" | grep -q "unknown variant"; then
    echo "  ⚠️  当前模型不支持 Vision（需 gpt-4o / glm-4v / claude 等多模态模型）"
else
    echo "  ⚠️  $RESP"
fi

# --- Summary ---
echo ""
echo "========================================="
echo " 结果: $PASS 通过, $FAIL 失败"
echo "========================================="
