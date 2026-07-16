"""Tests for OCRTool with dual-engine (Ollama + Provider) support."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from filemaker_gateway.ocr.client import OllamaOCRClient
from filemaker_gateway.provider.base import LLMProvider, LLMResponse
from filemaker_gateway.tool.ocr import OCRTool


# ---------------------------------------------------------------------------
# OllamaOCRClient unit tests
# ---------------------------------------------------------------------------

class TestOllamaOCRClient:

    def test_extract_base64_from_data_uri(self):
        """Should strip data URI prefix and return raw base64."""
        result = OllamaOCRClient.extract_base64(
            "data:image/png;base64,abc123def456"
        )
        assert result == "abc123def456"

    def test_extract_base64_passthrough_raw(self):
        """Should return raw base64 as-is."""
        result = OllamaOCRClient.extract_base64("abc123def456")
        assert result == "abc123def456"

    def test_is_data_uri_true(self):
        assert OllamaOCRClient.is_data_uri("data:image/png;base64,xxx") is True

    def test_is_data_uri_false_for_url(self):
        assert OllamaOCRClient.is_data_uri("https://example.com/img.png") is False

    def test_is_data_uri_false_for_raw_base64(self):
        assert OllamaOCRClient.is_data_uri("abc123") is False

    @pytest.mark.asyncio
    async def test_recognize_calls_ollama_api(self):
        """Should POST to /api/generate with correct payload."""
        client = OllamaOCRClient(
            base_url="http://localhost:11434",
            model="glm-ocr:latest",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "model": "glm-ocr:latest",
            "created_at": "2024-01-01T00:00:00Z",
            "response": "识别的文字内容",
            "done": True,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.recognize("abc123", mode="text")

        assert "识别的文字内容" in result
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert payload["model"] == "glm-ocr:latest"
        assert payload["images"] == ["abc123"]
        assert payload["stream"] is False
        assert "Text Recognition:" in payload["prompt"]

    @pytest.mark.asyncio
    async def test_recognize_invoice_mode(self):
        """Should use Chinese invoice prompt for invoice mode."""
        client = OllamaOCRClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '{"invoice_number": "INV-001"}',
            "done": True,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            await client.recognize("abc123", mode="invoice")

        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert "发票" in payload["prompt"]
        assert "invoice_number" in payload["prompt"]

    @pytest.mark.asyncio
    async def test_recognize_glm_mode_uses_chinese_prompt(self):
        """Should use Chinese general OCR prompt for glm mode."""
        client = OllamaOCRClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "识别结果",
            "done": True,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            await client.recognize("abc123", mode="glm")

        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert "请识别并提取" in payload["prompt"]

    @pytest.mark.asyncio
    async def test_recognize_http_error(self):
        """Should raise on HTTP error."""
        client = OllamaOCRClient()

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPError("Ollama not running")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            with pytest.raises(httpx.HTTPError, match="Ollama not running"):
                await client.recognize("abc123")

    @pytest.mark.asyncio
    async def test_recognize_empty_response(self):
        """Should return empty string for empty response."""
        client = OllamaOCRClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "", "done": True}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.recognize("abc123")

        assert result == ""

    def test_repr(self):
        client = OllamaOCRClient(base_url="http://localhost:11434", model="glm-ocr:latest")
        assert "glm-ocr:latest" in repr(client)
        assert "localhost:11434" in repr(client)


# ---------------------------------------------------------------------------
# OCRTool — dual-engine tests
# ---------------------------------------------------------------------------

class TestOCRTool:

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock(spec=LLMProvider)
        provider.chat = AsyncMock()
        provider.get_default_model.return_value = "test-model"
        return provider

    @pytest.fixture
    def mock_ollama(self):
        client = MagicMock(spec=OllamaOCRClient)
        client.recognize = AsyncMock()
        client.is_data_uri = lambda url: url.startswith("data:")
        return client

    @pytest.fixture
    def tool_provider_only(self, mock_provider):
        """Tool with provider only (backward compat)."""
        return OCRTool(provider=mock_provider)

    @pytest.fixture
    def tool_ollama_only(self, mock_ollama):
        """Tool with Ollama only."""
        return OCRTool(ollama_client=mock_ollama)

    @pytest.fixture
    def tool_both(self, mock_provider, mock_ollama):
        """Tool with both engines."""
        return OCRTool(provider=mock_provider, ollama_client=mock_ollama)

    # --- Provider-only path (backward compat) ---

    @pytest.mark.asyncio
    async def test_glm_ocr_calls_provider_with_vision(self, tool_provider_only, mock_provider):
        """Should send image to provider with OCR prompt."""
        mock_provider.chat.return_value = LLMResponse(
            content="这是一张发票，金额为 100 元",
            finish_reason="stop",
        )

        result = await tool_provider_only.execute(
            image_url="data:image/png;base64,abc123",
            ocr_type="glm",
        )

        assert "发票" in str(result)
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        last_content = messages[-1]["content"]
        assert isinstance(last_content, list)
        assert last_content[1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_invoice_ocr_uses_structured_prompt(self, tool_provider_only, mock_provider):
        """Should use invoice-specific prompt for structured extraction."""
        mock_provider.chat.return_value = LLMResponse(
            content='{"invoice_number": "INV-001", "date": "2024-01-15", "amount": 1500.00, "seller": "ABC Corp"}',
            finish_reason="stop",
        )

        result = await tool_provider_only.execute(
            image_url="data:image/png;base64,def456",
            ocr_type="invoice",
        )

        assert "INV-001" in str(result)
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        user_content = messages[1]["content"]
        assert isinstance(user_content, list)
        user_text = user_content[0]["text"]
        assert "发票" in user_text or "invoice" in user_text.lower()

    @pytest.mark.asyncio
    async def test_pdf_ocr_returns_error(self, tool_provider_only):
        """Should return error for PDF — not supported."""
        result = await tool_provider_only.execute(
            image_url="https://example.com/document.pdf",
            ocr_type="pdf",
        )
        assert "pdf" in str(result).lower()

    @pytest.mark.asyncio
    async def test_no_provider_returns_error(self):
        """Should return friendly error when neither engine is available."""
        tool = OCRTool()
        result = await tool.execute(image_url="data:image/png;base64,test")
        assert "未启用" in str(result)

    @pytest.mark.asyncio
    async def test_provider_error_propagates(self, tool_provider_only, mock_provider):
        """Should return error if provider call fails."""
        mock_provider.chat.side_effect = Exception("API rate limit")
        result = await tool_provider_only.execute(image_url="data:image/png;base64,test")
        assert "rate limit" in str(result).lower()

    @pytest.mark.asyncio
    async def test_non_data_uri_image_passed_as_is(self, tool_provider_only, mock_provider):
        """Should accept regular URLs as image_url."""
        mock_provider.chat.return_value = LLMResponse(
            content="Image text content",
            finish_reason="stop",
        )

        result = await tool_provider_only.execute(
            image_url="https://example.com/photo.jpg",
            ocr_type="glm",
        )

        assert "Image text content" in str(result)
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        last_content = messages[-1]["content"]
        assert "photo.jpg" in str(last_content)

    # --- Ollama path ---

    @pytest.mark.asyncio
    async def test_ollama_glm_ocr(self, tool_ollama_only, mock_ollama):
        """Should use Ollama for data URI images."""
        mock_ollama.recognize.return_value = "识别结果：这是一段中文文字"

        result = await tool_ollama_only.execute(
            image_url="data:image/png;base64,abc123",
            ocr_type="glm",
        )

        assert "识别结果" in str(result)
        mock_ollama.recognize.assert_called_once()
        # Verify mode mapping: "glm" → "glm" (Chinese general prompt)
        call_args = mock_ollama.recognize.call_args
        assert call_args.kwargs["mode"] == "glm"

    @pytest.mark.asyncio
    async def test_ollama_invoice_ocr(self, tool_ollama_only, mock_ollama):
        """Should use invoice mode for Ollama."""
        mock_ollama.recognize.return_value = '{"invoice_number": "INV-002"}'

        result = await tool_ollama_only.execute(
            image_url="data:image/png;base64,def456",
            ocr_type="invoice",
        )

        assert "INV-002" in str(result)
        call_args = mock_ollama.recognize.call_args
        assert call_args.kwargs["mode"] == "invoice"

    @pytest.mark.asyncio
    async def test_ollama_pdf_returns_error(self, tool_ollama_only):
        """PDF mode should return error even with Ollama."""
        result = await tool_ollama_only.execute(
            image_url="data:application/pdf;base64,xxx",
            ocr_type="pdf",
        )
        assert "pdf" in str(result).lower()

    @pytest.mark.asyncio
    async def test_ollama_error_propagates(self, tool_ollama_only, mock_ollama):
        """Should return error on Ollama failure."""
        mock_ollama.recognize.side_effect = Exception("Ollama connection refused")

        result = await tool_ollama_only.execute(
            image_url="data:image/png;base64,test",
            ocr_type="glm",
        )

        assert "Ollama" in str(result)
        assert "connection refused" in str(result)

    # --- Dual-engine preference ---

    @pytest.mark.asyncio
    async def test_prefers_ollama_for_data_uri(self, tool_both, mock_ollama, mock_provider):
        """Should use Ollama when image is data URI, even if provider is available."""
        mock_ollama.recognize.return_value = "Ollama 识别结果"

        result = await tool_both.execute(
            image_url="data:image/png;base64,abc123",
            ocr_type="glm",
        )

        assert "Ollama 识别结果" in str(result)
        mock_ollama.recognize.assert_called_once()
        mock_provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_provider_for_url(self, tool_both, mock_ollama, mock_provider):
        """Should fall back to provider when image is a URL, not data URI."""
        mock_provider.chat.return_value = LLMResponse(
            content="Provider 识别结果",
            finish_reason="stop",
        )

        result = await tool_both.execute(
            image_url="https://example.com/photo.jpg",
            ocr_type="glm",
        )

        assert "Provider 识别结果" in str(result)
        mock_ollama.recognize.assert_not_called()
        mock_provider.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_ollama_only_with_url_falls_back_error(self, tool_ollama_only, mock_ollama):
        """When only Ollama is available but image is URL, should return error."""
        # Ollama can't fetch remote URLs — and provider is None
        result = await tool_ollama_only.execute(
            image_url="https://example.com/photo.jpg",
            ocr_type="glm",
        )

        # Should not call Ollama (it can't handle URLs)
        mock_ollama.recognize.assert_not_called()
        # Should report no engine available
        assert "未启用" in str(result)
