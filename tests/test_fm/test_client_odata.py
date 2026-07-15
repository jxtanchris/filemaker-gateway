import json

import pytest
from filemaker_gateway.config.schema import FMODataConfig
from filemaker_gateway.fm.client_odata import FMODataClient
from filemaker_gateway.fm.errors import FMAuthError, FMNotFoundError


@pytest.fixture
def odata_config():
    return FMODataConfig(
        host="fm.example.com",
        database="MyDB",
        username="admin",
        password="secret",
        protocol="https",
        verify_ssl=True,
        enabled=True,
    )


@pytest.fixture
def odata_base_url(odata_config):
    c = odata_config
    return f"{c.protocol}://{c.host}/fmi/odata/v4/{c.database}"


class TestFMODataClientAuth:

    @pytest.mark.asyncio
    async def test_basic_auth_on_request(self, httpx_mock, odata_config, odata_base_url):
        """Should send Basic Auth header on every request."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/Contacts?$top=10&$skip=0",
            json={"value": []},
        )

        client = FMODataClient(odata_config)
        await client.get_records("Contacts", limit=10)

        request = httpx_mock.get_requests()[0]
        assert request.headers["Authorization"].startswith("Basic ")

    @pytest.mark.asyncio
    async def test_auth_failure_raises(self, httpx_mock, odata_config, odata_base_url):
        """Should raise FMAuthError on 401."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/Contacts?$top=10&$skip=0",
            status_code=401,
        )

        client = FMODataClient(odata_config)
        with pytest.raises(FMAuthError):
            await client.get_records("Contacts", limit=10)


class TestFMODataClientCRUD:

    @pytest.mark.asyncio
    async def test_get_records(self, httpx_mock, odata_config, odata_base_url):
        """Should GET records with $top and $skip."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/Contacts?$top=50&$skip=0",
            json={"value": [{"ID": 1, "NAME": "Alice"}]},
        )

        client = FMODataClient(odata_config)
        records = await client.get_records("Contacts", limit=50)

        assert len(records) == 1
        assert records[0]["NAME"] == "Alice"

    @pytest.mark.asyncio
    async def test_get_record_by_pk(self, httpx_mock, odata_config, odata_base_url):
        """Should GET single record by primary key."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/Contacts(42)",
            json={"ID": 42, "NAME": "Bob"},
        )

        client = FMODataClient(odata_config)
        record = await client.get_record("Contacts", "42")

        assert record["NAME"] == "Bob"

    @pytest.mark.asyncio
    async def test_create_record(self, httpx_mock, odata_config, odata_base_url):
        """Should POST to create a record."""
        httpx_mock.add_response(
            method="POST",
            url=f"{odata_base_url}/Contacts",
            json={"ID": 99, "NAME": "Charlie"},
        )

        client = FMODataClient(odata_config)
        result = await client.create_record("Contacts", {"NAME": "Charlie"})

        assert result["ID"] == 99

        post_req = httpx_mock.get_requests()[0]
        body = json.loads(post_req.content)
        assert body["NAME"] == "Charlie"

    @pytest.mark.asyncio
    async def test_update_record(self, httpx_mock, odata_config, odata_base_url):
        """Should PATCH to update a record."""
        httpx_mock.add_response(
            method="PATCH",
            url=f"{odata_base_url}/Contacts(42)",
            json={"ID": 42, "NAME": "Updated"},
        )

        client = FMODataClient(odata_config)
        result = await client.update_record("Contacts", "42", {"NAME": "Updated"})

        assert result["NAME"] == "Updated"

    @pytest.mark.asyncio
    async def test_delete_record(self, httpx_mock, odata_config, odata_base_url):
        """Should DELETE a record."""
        httpx_mock.add_response(
            method="DELETE",
            url=f"{odata_base_url}/Contacts(42)",
            status_code=204,
        )

        client = FMODataClient(odata_config)
        await client.delete_record("Contacts", "42")
        # Should not raise


class TestFMODataClientFind:

    @pytest.mark.asyncio
    async def test_find_with_filter(self, httpx_mock, odata_config, odata_base_url):
        """Should use OData $filter syntax."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/Contacts?$top=100&$skip=0&$filter=NAME+eq+%27Alice%27",
            json={"value": [{"ID": 1, "NAME": "Alice"}]},
        )

        client = FMODataClient(odata_config)
        results = await client.find("Contacts", "NAME eq 'Alice'")

        assert len(results) == 1
        assert results[0]["NAME"] == "Alice"


class TestFMODataClientScript:

    @pytest.mark.asyncio
    async def test_run_script(self, httpx_mock, odata_config, odata_base_url):
        """Should POST to Script endpoint."""
        httpx_mock.add_response(
            method="POST",
            url=f"{odata_base_url}/Script.ExportPDF",
            json={"resultParameter": "OK"},
        )

        client = FMODataClient(odata_config)
        result = await client.run_script("Layout", "ExportPDF", "invoice_123")

        assert result["resultParameter"] == "OK"

        req = httpx_mock.get_requests()[0]
        body = json.loads(req.content)
        assert body["scriptParameterValue"] == "invoice_123"

    @pytest.mark.asyncio
    async def test_run_script_without_param(self, httpx_mock, odata_config, odata_base_url):
        """Should run script without parameter."""
        httpx_mock.add_response(
            method="POST",
            url=f"{odata_base_url}/Script.RefreshCache",
            json={"resultParameter": "Done"},
        )

        client = FMODataClient(odata_config)
        result = await client.run_script("RefreshCache")

        assert result["resultParameter"] == "Done"


class TestFMODataClientMetadata:

    @pytest.mark.asyncio
    async def test_get_tables(self, httpx_mock, odata_config, odata_base_url):
        """Should return table names from OData service document."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/",
            json={"value": [{"name": "CONTACT"}, {"name": "INVOICE"}]},
        )

        client = FMODataClient(odata_config)
        tables = await client.get_tables()

        assert tables == ["CONTACT", "INVOICE"]


class TestFMODataClientClose:

    @pytest.mark.asyncio
    async def test_close(self, httpx_mock, odata_config, odata_base_url):
        """Should release the HTTP client."""
        # Need a request first to create the client
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/X?$top=1&$skip=0",
            json={"value": []},
        )

        client = FMODataClient(odata_config)
        await client.get_records("X", limit=1)
        await client.close()
        # Should not raise


class TestExtractKey:
    """Tests for _extract_key — OData @id key extraction."""

    def test_numeric_key(self):
        """Should extract numeric key from @id URL."""
        assert FMODataClient._extract_key("https://.../TASK(1)") == "1"

    def test_string_key(self):
        """Should extract string key without quotes."""
        assert FMODataClient._extract_key("https://.../Customers('CUST001')") == "CUST001"

    def test_large_numeric_key(self):
        """Should handle large FileMaker internal IDs."""
        huge_id = "https://.../TASK(205176054106772774499817506246548637197843673266609178716)"
        assert FMODataClient._extract_key(huge_id) == "205176054106772774499817506246548637197843673266609178716"

    def test_empty_key(self):
        """Should return empty string when no key found."""
        assert FMODataClient._extract_key("") == ""
        assert FMODataClient._extract_key("no_parens") == ""


class TestNormalizeRecords:
    """Tests for _normalize_records — binary data placeholder replacement."""

    def test_strips_jpeg_prefix(self):
        """Should replace JPEG base64 with [binary data]."""
        records = [{"photo": "/9j/4AAQSkZJRg...", "name": "test"}]
        result = FMODataClient._normalize_records(records)
        assert result[0]["photo"] == "[binary data]"
        assert result[0]["name"] == "test"

    def test_strips_png_prefix(self):
        """Should replace PNG base64 with [binary data]."""
        records = [{"image": "iVBORw0KGgo..."}]
        result = FMODataClient._normalize_records(records)
        assert result[0]["image"] == "[binary data]"

    def test_strips_gif_prefix(self):
        """Should replace GIF base64 with [binary data]."""
        records = [{"image": "R0lGODlh..."}]
        result = FMODataClient._normalize_records(records)
        assert result[0]["image"] == "[binary data]"

    def test_strips_pdf_prefix(self):
        """Should replace PDF base64 with [binary data]."""
        records = [{"file": "JVBERi0x..."}]
        result = FMODataClient._normalize_records(records)
        assert result[0]["file"] == "[binary data]"

    def test_preserves_non_binary_strings(self):
        """Should keep normal text fields unchanged."""
        records = [{"name": "Alice", "email": "alice@example.com"}]
        result = FMODataClient._normalize_records(records)
        assert result[0]["name"] == "Alice"
        assert result[0]["email"] == "alice@example.com"

    def test_preserves_numbers(self):
        """Should keep numeric fields unchanged."""
        records = [{"id": 42, "price": 9.99}]
        result = FMODataClient._normalize_records(records)
        assert result[0]["id"] == 42
        assert result[0]["price"] == 9.99

    def test_mixed_binary_and_text(self):
        """Should strip binaries while keeping text in same record."""
        records = [{"id": 1, "photo": "/9j/xxx", "name": "Bob"}]
        result = FMODataClient._normalize_records(records)
        assert result[0]["photo"] == "[binary data]"
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Bob"


class TestBuildQuery:
    """Tests for _build_query — OData query string without $ encoding."""

    def test_basic_params(self):
        """Should join params with & and keep literal $ signs."""
        qs = FMODataClient._build_query(**{"$top": 10, "$skip": 0})
        assert qs == "$top=10&$skip=0"

    def test_skips_none_values(self):
        """Should omit params with None value."""
        qs = FMODataClient._build_query(**{"$top": 10, "$orderby": None})
        assert qs == "$top=10"

    def test_skips_empty_string(self):
        """Should omit params with empty string value."""
        qs = FMODataClient._build_query(**{"$top": 10, "$filter": ""})
        assert qs == "$top=10"

    def test_keeps_filter_with_value(self):
        """Should include $filter when it has a value."""
        qs = FMODataClient._build_query(**{"$top": 100, "$filter": "NAME eq 'Alice'"})
        assert "$top=100" in qs
        assert "$filter=NAME eq 'Alice'" in qs

    def test_all_params_present(self):
        """Should include all non-empty params in order."""
        qs = FMODataClient._build_query(
            **{"$top": 50, "$skip": 10, "$filter": "x eq 1", "$orderby": "id asc"}
        )
        assert qs == "$top=50&$skip=10&$filter=x eq 1&$orderby=id asc"


class TestODataClientInternals:
    """Integration tests for _normalize_records, _build_query, and _safe_json
    via the public client API."""

    @pytest.mark.asyncio
    async def test_normalize_records_integration(self, httpx_mock, odata_config, odata_base_url):
        """Should strip binary container data in get_records response."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/Contacts?$top=10&$skip=0",
            json={"value": [
                {"ID": 1, "photo": "/9j/4AAQSkZJRg...", "name": "Alice"},
                {"ID": 2, "photo": "iVBORw0KGgo...", "name": "Bob"},
            ]},
        )
        client = FMODataClient(odata_config)
        records = await client.get_records("Contacts", limit=10)
        assert records[0]["photo"] == "[binary data]"
        assert records[1]["photo"] == "[binary data]"
        assert records[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_normalize_records_in_find(self, httpx_mock, odata_config, odata_base_url):
        """Should strip binary container data in find response."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/Contacts?$top=100&$skip=0&$filter=NAME+eq+%27Alice%27",
            json={"value": [{"ID": 1, "photo": "/9j/xxx", "name": "Alice"}]},
        )
        client = FMODataClient(odata_config)
        records = await client.find("Contacts", "NAME eq 'Alice'")
        assert records[0]["photo"] == "[binary data]"

    @pytest.mark.asyncio
    async def test_get_record_strips_container(self, httpx_mock, odata_config, odata_base_url):
        """get_record should NOT strip — returns raw for container download."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/Contacts(1)",
            json={"ID": 1, "photo": "/9j/xxx", "name": "Alice"},
        )
        client = FMODataClient(odata_config)
        record = await client.get_record("Contacts", "1")
        # get_record returns raw data — _normalize_records not applied
        assert record["photo"] == "/9j/xxx"
