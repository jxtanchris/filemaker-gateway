"""OllamaOCRClient: lightweight client for GLM-OCR via Ollama /api/generate.

GLM-OCR is a specialized ~0.9B OCR model that uses Ollama's native
API endpoint, NOT the OpenAI-compatible /v1/chat/completions.
"""

from __future__ import annotations

import base64
import re
from typing import Any

import httpx
from loguru import logger


# GLM-OCR prompt templates for different recognition modes
_GLM_OCR_PROMPTS: dict[str, str] = {
    "text": "Text Recognition:",
    "table": "Table Recognition:",
    "formula": "Formula Recognition:",
    "figure": "Figure Recognition:",
}

# Used when ocr_type="invoice" — GLM-OCR needs a Chinese prompt for structured extraction
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

# General Chinese OCR prompt
_GLM_PROMPT = "请识别并提取这张图片中的所有文字。保留原始格式和排版。"


class OllamaOCRClient:
    """Call Ollama's GLM-OCR model via the native /api/generate endpoint.

    Usage:
        client = OllamaOCRClient(base_url="http://localhost:11434", model="glm-ocr:latest")
        text = await client.recognize(image_base64="...", mode="text")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "glm-ocr:latest",
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def recognize(
        self,
        image_base64: str,
        mode: str = "text",
    ) -> str:
        """Recognize text from a base64-encoded image using GLM-OCR.

        Args:
            image_base64: Raw base64-encoded image bytes (no data URI prefix).
            mode: Recognition mode — "text", "table", "formula", "figure",
                  "invoice", or "glm" (general Chinese OCR).

        Returns:
            The recognized text from the image.

        Raises:
            httpx.HTTPError: On network/HTTP failures.
            ValueError: On unexpected response format.
        """
        prompt = self._build_prompt(mode)
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
        }

        logger.debug(
            "Ollama OCR request: model={}, mode={}, image_bytes={}",
            self._model,
            mode,
            len(image_base64),
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        result = data.get("response", "")
        if not result:
            logger.warning("Ollama OCR returned empty response: {}", data)
            return ""

        logger.debug("Ollama OCR result: {} chars", len(result))
        return result.strip()

    @staticmethod
    def extract_base64(image_url: str) -> str:
        """Extract raw base64 from a data URI or return as-is if already raw.

        Args:
            image_url: Either a data URI (data:image/png;base64,xxx)
                       or raw base64 string.

        Returns:
            Raw base64 string without the data URI prefix.
        """
        if image_url.startswith("data:"):
            # data:image/png;base64,xxx → xxx
            match = re.search(r"base64,(.+)$", image_url, re.IGNORECASE)
            if match:
                return match.group(1)
            # data:image/png,xxx (no base64 encoding)
            comma_idx = image_url.find(",")
            if comma_idx != -1:
                raw = image_url[comma_idx + 1:]
                # If not base64-encoded, encode it
                try:
                    base64.b64decode(raw)
                    return raw
                except Exception:
                    return base64.b64encode(raw.encode()).decode()
        return image_url

    @staticmethod
    def is_data_uri(image_url: str) -> bool:
        """Check if the image URL is a data URI (suitable for Ollama OCR)."""
        return image_url.startswith("data:")

    def _build_prompt(self, mode: str) -> str:
        """Build the GLM-OCR prompt for the given recognition mode."""
        if mode in ("glm", "general"):
            return _GLM_PROMPT
        if mode == "invoice":
            return _INVOICE_PROMPT
        if mode in _GLM_OCR_PROMPTS:
            return _GLM_OCR_PROMPTS[mode]
        # Fallback: use the mode string directly as prompt
        logger.debug("Unknown OCR mode '{}', using as literal prompt", mode)
        return mode

    def __repr__(self) -> str:
        return f"OllamaOCRClient(base_url={self._base_url!r}, model={self._model!r})"
