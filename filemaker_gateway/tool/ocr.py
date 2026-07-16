"""OCRTool: Extract text from images using local Ollama GLM-OCR or LLM Vision."""

from __future__ import annotations

from typing import TYPE_CHECKING

from filemaker_gateway.tool.base import Tool, ToolResult

if TYPE_CHECKING:
    from filemaker_gateway.ocr.client import OllamaOCRClient
    from filemaker_gateway.provider.base import LLMProvider

# Prompt templates for LLM Vision provider mode
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
    """Extract text from images using local Ollama GLM-OCR or LLM Vision.

    Dual-engine design:
    - When ollama_client is available and image is a data URI,
      use local Ollama GLM-OCR (fast, free, specialized).
    - Otherwise fall back to the main LLM provider's Vision API.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        ollama_client: OllamaOCRClient | None = None,
    ) -> None:
        self._provider = provider
        self._ollama = ollama_client
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
        if ocr_type == "pdf":
            return ToolResult.error(_PDF_NOTE)

        # --- Engine 1: Local Ollama GLM-OCR (preferred) ---
        if self._ollama is not None and self._ollama.is_data_uri(image_url):
            return await self._execute_ollama(image_url, ocr_type)

        # --- Engine 2: Main LLM Provider Vision API (fallback) ---
        if self._provider is not None:
            return await self._execute_provider(image_url, ocr_type)

        return ToolResult.error(
            "OCR 未启用 (没有可用的 OCR 引擎，请检查配置)"
        )

    async def _execute_ollama(
        self,
        image_url: str,
        ocr_type: str,
    ) -> ToolResult | str:
        """Execute OCR via local Ollama GLM-OCR."""
        from filemaker_gateway.ocr.client import OllamaOCRClient

        try:
            image_base64 = OllamaOCRClient.extract_base64(image_url)
            # Map tool ocr_type to GLM-OCR mode
            if ocr_type == "invoice":
                mode = "invoice"
            else:
                mode = "glm"  # "glm" maps to Chinese general prompt in client

            result = await self._ollama.recognize(image_base64, mode=mode)
            return ToolResult(result)

        except Exception as e:
            return ToolResult.error(f"Ollama OCR 失败: {e}")

    async def _execute_provider(
        self,
        image_url: str,
        ocr_type: str,
    ) -> ToolResult | str:
        """Execute OCR via the main LLM provider's Vision API."""
        # Build OCR prompt
        if ocr_type == "invoice":
            user_text = _INVOICE_PROMPT
        else:
            user_text = _GLM_PROMPT

        # Build vision-format content
        content: list[dict] = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]

        try:
            response = await self._provider.chat(  # type: ignore[union-attr]
                messages=[
                    {"role": "system", "content": "你是一个精确的 OCR 和文档识别助手。"},
                    {"role": "user", "content": content},
                ],
                model=self._model,
                temperature=0.1,
                max_tokens=4096,
            )

            if response.finish_reason == "error":
                return ToolResult.error(f"OCR 识别失败: {response.content}")

            return ToolResult(response.content or "")

        except Exception as e:
            return ToolResult.error(f"OCR 处理失败: {e}")
