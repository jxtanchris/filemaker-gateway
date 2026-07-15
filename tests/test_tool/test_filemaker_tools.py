"""Tests for FileMaker tool implementations."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.tool.filemaker.layout import FileMakerLayoutTool
from filemaker_gateway.tool.filemaker.query import FileMakerQueryTool
from filemaker_gateway.tool.filemaker.record import FileMakerRecordTool
from filemaker_gateway.tool.filemaker.script import FileMakerScriptTool


# --- Query Tool ---

class TestFileMakerQueryTool:

    @pytest.fixture
    def mock_fm(self):
        client = MagicMock(spec=FMDataClient)
        client.get_records = AsyncMock()
        client.find = AsyncMock()
        return client

    @pytest.fixture
    def tool(self, mock_fm):
        return FileMakerQueryTool(fm_client=mock_fm)

    @pytest.mark.asyncio
    async def test_select_returns_records(self, tool, mock_fm):
        """Should call get_records and return JSON-serialized results."""
        mock_fm.get_records.return_value = [
            {"fieldData": {"name": "Alice"}, "recordId": "1", "modId": "0"}
        ]
        result = await tool.execute(action="select", layout="Contacts", limit=10)
        parsed = json.loads(str(result))
        assert parsed[0]["fieldData"]["name"] == "Alice"
        mock_fm.get_records.assert_called_once_with("Contacts", limit=10)

    @pytest.mark.asyncio
    async def test_find_returns_matching_records(self, tool, mock_fm):
        """Should call find with parsed query."""
        mock_fm.find.return_value = [
            {"fieldData": {"name": "Bob"}, "recordId": "2", "modId": "0"}
        ]
        result = await tool.execute(action="find", layout="Contacts", query='[{"name":"Bob"}]')
        parsed = json.loads(str(result))
        assert parsed[0]["fieldData"]["name"] == "Bob"
        mock_fm.find.assert_called_once_with("Contacts", [{"name": "Bob"}], limit=100)

    @pytest.mark.asyncio
    async def test_select_without_layout_returns_error(self, tool):
        """Should return error if layout is missing for select."""
        result = await tool.execute(action="select")
        assert "layout is required" in str(result).lower()

    @pytest.mark.asyncio
    async def test_stub_when_no_fm_client(self):
        """Should return friendly error when fm_data_api is disabled."""
        tool = FileMakerQueryTool()  # No fm_client
        result = await tool.execute(action="select", layout="Contacts")
        assert "FM Data API 未启用" in str(result)

    @pytest.mark.asyncio
    async def test_fm_client_error_propagates(self, tool, mock_fm):
        """Should return error result when Data API fails."""
        mock_fm.get_records.side_effect = Exception("Connection refused")
        result = await tool.execute(action="select", layout="Contacts")
        assert "Connection refused" in str(result)


# --- Record Tool ---


class TestFileMakerRecordTool:

    @pytest.fixture
    def mock_fm(self):
        client = MagicMock(spec=FMDataClient)
        client.create_record = AsyncMock()
        client.update_record = AsyncMock()
        client.delete_record = AsyncMock()
        return client

    @pytest.fixture
    def tool(self, mock_fm):
        return FileMakerRecordTool(fm_client=mock_fm)

    @pytest.mark.asyncio
    async def test_create_record(self, tool, mock_fm):
        """Should create a record and return the new record ID."""
        mock_fm.create_record.return_value = {"recordId": "99", "modId": "0"}
        result = await tool.execute(
            action="create", layout="Contacts", field_data={"name": "Alice"}
        )
        parsed = json.loads(str(result))
        assert parsed["recordId"] == "99"
        mock_fm.create_record.assert_called_once_with("Contacts", {"name": "Alice"})

    @pytest.mark.asyncio
    async def test_update_record(self, tool, mock_fm):
        """Should update a record and return the new modId."""
        mock_fm.update_record.return_value = {"modId": "2"}
        result = await tool.execute(
            action="update", layout="Contacts", record_id="1", field_data={"name": "Bob"}
        )
        parsed = json.loads(str(result))
        assert parsed["modId"] == "2"
        mock_fm.update_record.assert_called_once_with("Contacts", "1", {"name": "Bob"}, None)

    @pytest.mark.asyncio
    async def test_delete_record(self, tool, mock_fm):
        """Should delete a record."""
        mock_fm.delete_record.return_value = None
        result = await tool.execute(action="delete", layout="Contacts", record_id="1")
        assert "deleted" in str(result).lower()
        mock_fm.delete_record.assert_called_once_with("Contacts", "1")

    @pytest.mark.asyncio
    async def test_update_without_record_id(self, tool):
        """Should return error for update without record_id."""
        result = await tool.execute(action="update", layout="Contacts", field_data={"name": "X"})
        assert "record_id is required" in str(result).lower()

    @pytest.mark.asyncio
    async def test_delete_without_record_id(self, tool):
        """Should return error for delete without record_id."""
        result = await tool.execute(action="delete", layout="Contacts")
        assert "record_id is required" in str(result).lower()

    @pytest.mark.asyncio
    async def test_stub_when_no_fm_client(self):
        """Should return friendly error when fm_data_api is disabled."""
        tool = FileMakerRecordTool()
        result = await tool.execute(action="create", layout="Contacts", field_data={"x": "y"})
        assert "FM Data API 未启用" in str(result)


# --- Script Tool ---


class TestFileMakerScriptTool:

    @pytest.fixture
    def mock_fm(self):
        client = MagicMock(spec=FMDataClient)
        client.run_script = AsyncMock()
        return client

    @pytest.fixture
    def tool(self, mock_fm):
        return FileMakerScriptTool(fm_client=mock_fm)

    @pytest.mark.asyncio
    async def test_run_script(self, tool, mock_fm):
        """Should execute a FileMaker script and return its result."""
        mock_fm.run_script.return_value = {"scriptResult": "PDF exported successfully"}
        result = await tool.execute(script_name="Export PDF", parameter="invoice_123")
        assert "PDF exported successfully" in str(result)

    @pytest.mark.asyncio
    async def test_run_script_without_parameter(self, tool, mock_fm):
        """Should run script without parameter."""
        mock_fm.run_script.return_value = {"scriptResult": "OK"}
        result = await tool.execute(script_name="Refresh Cache")
        assert "OK" in str(result)

    @pytest.mark.asyncio
    async def test_run_script_error(self, tool, mock_fm):
        """Should return error if script fails."""
        mock_fm.run_script.return_value = {"scriptResult.error": "3", "scriptResult": "Script not found"}
        result = await tool.execute(script_name="NonExistent")
        assert "error" in str(result).lower()

    @pytest.mark.asyncio
    async def test_stub_when_no_fm_client(self):
        """Should return friendly error when fm_data_api is disabled."""
        tool = FileMakerScriptTool()
        result = await tool.execute(script_name="Test Script")
        assert "FM Data API 未启用" in str(result)


# --- Layout Tool ---


class TestFileMakerLayoutTool:

    @pytest.fixture
    def mock_fm(self):
        client = MagicMock(spec=FMDataClient)
        client.get_layouts = AsyncMock()
        client.get_layout_metadata = AsyncMock()
        return client

    @pytest.fixture
    def tool(self, mock_fm):
        return FileMakerLayoutTool(fm_client=mock_fm)

    @pytest.mark.asyncio
    async def test_list_layouts(self, tool, mock_fm):
        """Should return list of layout names."""
        mock_fm.get_layouts.return_value = ["Contacts", "Invoices", "Dashboard"]
        result = await tool.execute(action="list_layouts")
        assert "Contacts" in str(result)
        assert "Invoices" in str(result)

    @pytest.mark.asyncio
    async def test_open_layout_returns_info(self, tool, mock_fm):
        """Should return layout metadata for a named layout."""
        mock_fm.get_layout_metadata.return_value = {
            "fieldMetaData": [{"name": "id", "type": "normal"}]
        }
        result = await tool.execute(action="open_layout", layout_name="Contacts")
        assert "fieldMetaData" in str(result) or "id" in str(result)

    @pytest.mark.asyncio
    async def test_open_layout_without_name(self, tool):
        """Should return error without layout_name."""
        result = await tool.execute(action="open_layout")
        assert "layout_name is required" in str(result).lower()

    @pytest.mark.asyncio
    async def test_next_previous_record_not_supported(self, tool):
        """Should return message about server-side limitation."""
        result = await tool.execute(action="next_record")
        assert "cannot" in str(result).lower() or "not supported" in str(result).lower()

    @pytest.mark.asyncio
    async def test_stub_when_no_fm_client(self):
        """Should return friendly error when fm_data_api is disabled."""
        tool = FileMakerLayoutTool()
        result = await tool.execute(action="list_layouts")
        assert "FM Data API 未启用" in str(result)
