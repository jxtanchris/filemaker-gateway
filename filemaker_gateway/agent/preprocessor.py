"""MediaPreprocessor: transforms images to text before messages reach the LLM.

Keeps AgentLoop._build() free of direct Tool and Provider access.
When images are attached and the provider doesn't support vision,
routes them through the OCR tool automatically.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from filemaker_gateway.provider.base import LLMProvider
    from filemaker_gateway.tool.registry import ToolRegistry


class MediaPreprocessError(Exception):
    """Image preprocessing failed. Carries a user-readable error message."""


class MediaPreprocessor:
    """Preprocess media attachments before the LLM sees them.

    Three paths:
    - No images → return plain text unchanged.
    - Provider supports vision → return a content list with image_url blocks.
    - Provider does NOT support vision → OCR each image, return text with
      OCR results appended.

    Usage:
        preprocessor = MediaPreprocessor(tool_registry, provider)
        content = await preprocessor.build_user_content("描述这张图", media)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        provider: LLMProvider,
    ) -> None:
        self._tool_registry = tool_registry
        self._provider = provider

    async def build_user_content(
        self,
        user_message: str,
        media: list[str],
    ) -> str | list[dict[str, Any]]:
        """Build the user message content, processing images as needed.

        Args:
            user_message: The user's text message.
            media: List of media URLs/attachments (data URIs or regular URLs).

        Returns:
            Either a plain string (no images / OCR processed) or a list of
            content-part dicts (vision path with image_url blocks).

        Raises:
            MediaPreprocessError: When images need OCR but no OCR tool is
                registered and the provider doesn't support vision.
        """
        image_media = [m for m in media if m.startswith("data:image")]
        other_media = [m for m in media if not m.startswith("data:image")]

        # --- No images: plain text ---
        if not image_media:
            return _build_plain_text(user_message, other_media)

        # --- Provider supports vision: image_url blocks ---
        if self._provider.supports_vision:
            return _build_vision_content(user_message, image_media, other_media)

        # --- Provider does NOT support vision: pre-process via OCR ---
        ocr_tool = self._tool_registry.get("ocr")
        if ocr_tool is None:
            raise MediaPreprocessError(
                "图片上传失败：当前 AI 模型不支持直接识别图片，且 OCR 工具未启用。"
                "请在 config.yaml 中启用 ocr.engine=ollama。"
            )

        logger.info(
            "Pre-processing {} image(s) via OCR (provider={} lacks vision support)",
            len(image_media),
            type(self._provider).__name__,
        )

        ocr_texts = await _run_ocr_parallel(ocr_tool, image_media)
        return _build_ocr_text(user_message, other_media, ocr_texts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_plain_text(user_message: str, other_media: list[str]) -> str:
    """Build plain-text user content. Non-image media become [media: url] refs."""
    if not other_media:
        return user_message
    media_str = "\n".join(f"[media: {url}]" for url in other_media)
    return f"{media_str}\n{user_message}"


def _build_vision_content(
    user_message: str,
    image_media: list[str],
    other_media: list[str],
) -> list[dict[str, Any]]:
    """Build a vision-format content list with image_url blocks."""
    content: list[dict[str, Any]] = [
        {"type": "text", "text": user_message},
    ]
    for url in image_media:
        content.append({
            "type": "image_url",
            "image_url": {"url": url},
        })
    if other_media:
        refs = "\n".join(f"[media: {url}]" for url in other_media)
        content.append({"type": "text", "text": refs})
    return content


def _build_ocr_text(
    user_message: str,
    other_media: list[str],
    ocr_texts: list[str],
) -> str:
    """Build a plain-text message with OCR results appended."""
    parts = [user_message]
    if other_media:
        parts.append("\n".join(f"[media: {url}]" for url in other_media))
    parts.append("\n---\n" + "\n\n".join(ocr_texts))
    return "\n".join(parts)


async def _run_ocr_parallel(ocr_tool: Any, image_media: list[str]) -> list[str]:
    """Run OCR on all images in parallel and return labeled results."""

    async def _ocr_one(index: int, url: str) -> str:
        try:
            result = await ocr_tool.execute(image_url=url, ocr_type="glm")
            text = str(result)
            if text:
                logger.debug("OCR image {}: {} chars", index + 1, len(text))
                return f"[图片 {index + 1} 的 OCR 识别结果]\n{text}"
            return f"[图片 {index + 1}] OCR 未能识别出文字内容"
        except Exception as e:
            logger.warning("OCR failed for image {}: {}", index + 1, e)
            return f"[图片 {index + 1}] OCR 识别失败: {e}"

    tasks = [_ocr_one(i, url) for i, url in enumerate(image_media)]
    return list(await asyncio.gather(*tasks))
