"""OCRTool: Extract text from images using LLM Vision."""

from filemaker_gateway.provider.base import LLMProvider
from filemaker_gateway.tool.base import Tool, ToolResult

# Prompt templates for different OCR modes
_GLM_PROMPT = "请识别并提取这张图片中的所有文字。保留原始格式和排版。"
_INVOICE_PROMPT = (
    "请从这张发票图片中提取以下结构化信息，以 JSON 格式返回：\n"
    '{\n'
    '  "invoice_number": "发票号",\n'
    '  "date": "开票日期",\n'
    '  "amount": "金额（数字）",\n'
    '  "seller": "销售方名称",\n'
    '  "buyer": "购买方名称",\n'
    '  "items": [{"name": "商品名", "quantity": 数量, "price": 单价}]\n'
    '}\n'
    "只返回 JSON，不要包含其他内容。"
)

_PDF_NOTE = (
    "PDF OCR 需要先将 PDF 拆分为单页图片。请使用外部工具（如 poppler、PyMuPDF）"
    "将 PDF 转换为图片后，再对每页调用 ocr_type='glm'。"
)


class OCRTool(Tool):
    """Extract text from images using LLM Vision (via the configured Provider)."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider
        self._model = provider.get_default_model() if provider else "deepseek-chat"

    @property
    def name(self) -> str:
        return "ocr"

    @property
    def description(self) -> str:
        return (
            "Extract text from images and documents using AI Vision. "
            "Use 'glm' for general image OCR (supports Chinese and English), "
            "use 'invoice' for structured invoice field extraction "
            "(invoice number, date, amount, seller, buyer), "
            "use 'pdf' for multi-page PDF text extraction "
            "(requires splitting PDF into single-page images first). "
            "Provide the image as a data:image/...;base64,... URL or a regular image URL."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": "string",
                    "description": "The image to OCR. Use data:image/...;base64,... format for local images, or a URL for remote images.",
                },
                "ocr_type": {
                    "type": "string",
                    "enum": ["glm", "invoice", "pdf"],
                    "description": "OCR mode: 'glm' for general text, 'invoice' for structured invoice data, 'pdf' for PDF documents.",
                },
            },
            "required": ["image_url"],
        }

    @property
    def read_only(self) -> bool:
        return True

    async def execute(
        self,
        image_url: str,
        ocr_type: str = "glm",
    ) -> ToolResult | str:
        if self._provider is None:
            return ToolResult.error(
                "OCR 未启用 (Provider 未注入，请检查配置)"
            )

        if ocr_type == "pdf":
            return ToolResult.error(_PDF_NOTE)

        # Build OCR prompt
        if ocr_type == "invoice":
            user_text = _INVOICE_PROMPT
        else:
            user_text = _GLM_PROMPT

        # Build vision-format content
        content: list[dict] = [
            {"type": "text", "text": user_text},
        ]

        # Handle both data URIs and regular URLs
        if image_url.startswith("data:image"):
            content.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })
        else:
            # Regular URL — the model may or may not support fetching it
            content.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })

        try:
            response = await self._provider.chat(
                messages=[
                    {"role": "system", "content": "你是一个精确的 OCR 和文档识别助手。"},
                    {"role": "user", "content": content},
                ],
                model=self._model,
                temperature=0.1,  # Low temperature for accuracy
                max_tokens=4096,
            )

            if response.finish_reason == "error":
                return ToolResult.error(f"OCR 识别失败: {response.content}")

            return ToolResult(response.content or "")

        except Exception as e:
            return ToolResult.error(f"OCR 处理失败: {e}")
