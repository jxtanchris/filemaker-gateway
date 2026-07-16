"""Tests for MediaPreprocessor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from filemaker_gateway.agent.preprocessor import (
    MediaPreprocessError,
    MediaPreprocessor,
)
from filemaker_gateway.provider.base import LLMProvider
from filemaker_gateway.tool.ocr import OCRTool
from filemaker_gateway.tool.registry import ToolRegistry


class TestMediaPreprocessor:

    @pytest.fixture
    def mock_vision_provider(self):
        """Provider that supports multimodal vision."""
        provider = MagicMock(spec=LLMProvider)
        provider.supports_vision = True
        return provider

    @pytest.fixture
    def mock_non_vision_provider(self):
        """Provider that does NOT support vision (e.g. DeepSeek)."""
        provider = MagicMock(spec=LLMProvider)
        provider.supports_vision = False
        return provider

    @pytest.fixture
    def registry_with_ocr(self):
        """ToolRegistry with a real OCRTool (provider-only, no Ollama)."""
        r = ToolRegistry()
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.get_default_model.return_value = "test-model"
        r.register(OCRTool(provider=mock_provider))
        return r

    @pytest.fixture
    def registry_without_ocr(self):
        """ToolRegistry with no OCR tool registered."""
        return ToolRegistry()

    # --- No images ---

    @pytest.mark.asyncio
    async def test_no_images_returns_plain_text(self, mock_non_vision_provider, registry_with_ocr):
        """Without images, should return the user message unchanged."""
        preprocessor = MediaPreprocessor(registry_with_ocr, mock_non_vision_provider)
        result = await preprocessor.build_user_content("Hello", [])
        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_non_image_media_appended_as_refs(self, mock_non_vision_provider, registry_with_ocr):
        """Non-image media should appear as [media: url] references."""
        preprocessor = MediaPreprocessor(registry_with_ocr, mock_non_vision_provider)
        result = await preprocessor.build_user_content("Check this", ["https://x.com/file.pdf"])
        assert "[media: https://x.com/file.pdf]" in result
        assert "Check this" in result

    # --- Vision provider ---

    @pytest.mark.asyncio
    async def test_vision_provider_returns_content_list(self, mock_vision_provider, registry_with_ocr):
        """Vision-capable provider should get image_url blocks."""
        preprocessor = MediaPreprocessor(registry_with_ocr, mock_vision_provider)
        result = await preprocessor.build_user_content(
            "What's this?",
            ["data:image/png;base64,abc123"],
        )
        assert isinstance(result, list)
        assert result[0] == {"type": "text", "text": "What's this?"}
        assert result[1]["type"] == "image_url"
        assert result[1]["image_url"]["url"] == "data:image/png;base64,abc123"

    @pytest.mark.asyncio
    async def test_vision_with_mixed_media(self, mock_vision_provider, registry_with_ocr):
        """Vision provider with mixed image + non-image media."""
        preprocessor = MediaPreprocessor(registry_with_ocr, mock_vision_provider)
        result = await preprocessor.build_user_content(
            "Check",
            [
                "data:image/jpeg;base64,xxx",
                "https://example.com/doc.pdf",
            ],
        )
        assert isinstance(result, list)
        # Should have text, image, and media ref
        assert len(result) == 3
        assert result[2]["type"] == "text"
        assert "[media:" in result[2]["text"]

    # --- No vision + OCR available ---

    @pytest.mark.asyncio
    async def test_non_vision_runs_ocr(self, mock_non_vision_provider):
        """Non-vision provider should run OCR and return text with results."""
        r = ToolRegistry()
        ocr_tool = MagicMock(spec=OCRTool)
        ocr_tool.name = "ocr"
        ocr_tool.execute = AsyncMock(return_value="识别结果：这是测试文字")
        r.register(ocr_tool)

        preprocessor = MediaPreprocessor(r, mock_non_vision_provider)
        result = await preprocessor.build_user_content(
            "识别这张发票",
            ["data:image/png;base64,abc123"],
        )
        assert isinstance(result, str)
        assert "识别这张发票" in result
        assert "OCR 识别结果" in result
        assert "识别结果：这是测试文字" in result
        ocr_tool.execute.assert_called_once_with(
            image_url="data:image/png;base64,abc123",
            ocr_type="glm",
        )

    @pytest.mark.asyncio
    async def test_ocr_empty_result(self, mock_non_vision_provider):
        """Empty OCR result should be reported gracefully."""
        r = ToolRegistry()
        ocr_tool = MagicMock(spec=OCRTool)
        ocr_tool.name = "ocr"
        ocr_tool.execute = AsyncMock(return_value="")
        r.register(ocr_tool)

        preprocessor = MediaPreprocessor(r, mock_non_vision_provider)
        result = await preprocessor.build_user_content(
            "识别",
            ["data:image/png;base64,abc123"],
        )
        assert "未能识别出文字内容" in result

    @pytest.mark.asyncio
    async def test_ocr_exception_graceful(self, mock_non_vision_provider):
        """OCR exception should be caught and reported, not crash."""
        r = ToolRegistry()
        ocr_tool = MagicMock(spec=OCRTool)
        ocr_tool.name = "ocr"
        ocr_tool.execute = AsyncMock(side_effect=Exception("Connection refused"))
        r.register(ocr_tool)

        preprocessor = MediaPreprocessor(r, mock_non_vision_provider)
        result = await preprocessor.build_user_content(
            "识别",
            ["data:image/png;base64,abc123"],
        )
        assert "OCR 识别失败" in result
        assert "Connection refused" in result

    # --- No vision + no OCR ---

    @pytest.mark.asyncio
    async def test_no_vision_no_ocr_raises_error(self, mock_non_vision_provider, registry_without_ocr):
        """Without vision and without OCR tool, should raise MediaPreprocessError."""
        preprocessor = MediaPreprocessor(registry_without_ocr, mock_non_vision_provider)
        with pytest.raises(MediaPreprocessError, match="OCR 工具未启用"):
            await preprocessor.build_user_content(
                "识别",
                ["data:image/png;base64,abc123"],
            )

    # --- Parallel OCR ---

    @pytest.mark.asyncio
    async def test_multiple_images_parallel_ocr(self, mock_non_vision_provider):
        """Multiple images should all be OCR'd (parallel execution tested via result count)."""
        r = ToolRegistry()
        ocr_tool = MagicMock(spec=OCRTool)
        ocr_tool.name = "ocr"

        async def slow_ocr(image_url, ocr_type):
            return f"Text from {image_url[-6:]}"

        ocr_tool.execute = AsyncMock(side_effect=slow_ocr)
        r.register(ocr_tool)

        preprocessor = MediaPreprocessor(r, mock_non_vision_provider)
        result = await preprocessor.build_user_content(
            "Multi",
            [
                "data:image/png;base64,img001",
                "data:image/png;base64,img002",
                "data:image/png;base64,img003",
            ],
        )
        assert "图片 1" in result
        assert "图片 2" in result
        assert "图片 3" in result
        assert "img001" in result
        assert "img002" in result
        assert "img003" in result
        assert ocr_tool.execute.call_count == 3
