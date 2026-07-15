"""Tests for OCRTool with LLM Vision integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from filemaker_gateway.provider.base import LLMProvider, LLMResponse
from filemaker_gateway.tool.ocr import OCRTool


class TestOCRTool:

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock(spec=LLMProvider)
        provider.chat = AsyncMock()
        provider.get_default_model.return_value = "test-model"
        return provider

    @pytest.fixture
    def tool(self, mock_provider):
        return OCRTool(provider=mock_provider)

    @pytest.mark.asyncio
    async def test_glm_ocr_calls_provider_with_vision(self, tool, mock_provider):
        """Should send image to provider with OCR prompt."""
        mock_provider.chat.return_value = LLMResponse(
            content="这是一张发票，金额为 100 元",
            finish_reason="stop",
        )

        result = await tool.execute(
            image_url="data:image/png;base64,abc123",
            ocr_type="glm",
        )

        assert "发票" in str(result)
        # Verify provider was called with vision format
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        # Last message should contain the image in vision format
        last_content = messages[-1]["content"]
        assert isinstance(last_content, list)
        assert last_content[1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_invoice_ocr_uses_structured_prompt(self, tool, mock_provider):
        """Should use invoice-specific prompt for structured extraction."""
        mock_provider.chat.return_value = LLMResponse(
            content='{"invoice_number": "INV-001", "date": "2024-01-15", "amount": 1500.00, "seller": "ABC Corp"}',
            finish_reason="stop",
        )

        result = await tool.execute(
            image_url="data:image/png;base64,def456",
            ocr_type="invoice",
        )

        assert "INV-001" in str(result)
        # Verify invoice-specific prompt is in the user message
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        user_content = messages[1]["content"]
        assert isinstance(user_content, list)
        user_text = user_content[0]["text"]
        assert "发票" in user_text or "invoice" in user_text.lower()

    @pytest.mark.asyncio
    async def test_pdf_ocr_returns_error_for_multi_page(self, tool):
        """Should return error for PDF — multi-page not supported without splitting."""
        result = await tool.execute(
            image_url="https://example.com/document.pdf",
            ocr_type="pdf",
        )
        assert "pdf" in str(result).lower()

    @pytest.mark.asyncio
    async def test_no_provider_returns_error(self):
        """Should return friendly error when provider is not injected."""
        tool = OCRTool()
        result = await tool.execute(image_url="data:image/png;base64,test")
        assert "未启用" in str(result) or "not available" in str(result).lower()

    @pytest.mark.asyncio
    async def test_provider_error_propagates(self, tool, mock_provider):
        """Should return error if provider call fails."""
        mock_provider.chat.side_effect = Exception("API rate limit")
        result = await tool.execute(image_url="data:image/png;base64,test")
        assert "rate limit" in str(result).lower()

    @pytest.mark.asyncio
    async def test_non_data_uri_image_passed_as_is(self, tool, mock_provider):
        """Should accept regular URLs as image_url."""
        mock_provider.chat.return_value = LLMResponse(
            content="Image text content",
            finish_reason="stop",
        )

        result = await tool.execute(
            image_url="https://example.com/photo.jpg",
            ocr_type="glm",
        )

        assert "Image text content" in str(result)
        # URL should be passed through
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        last_content = messages[-1]["content"]
        assert "photo.jpg" in str(last_content)
