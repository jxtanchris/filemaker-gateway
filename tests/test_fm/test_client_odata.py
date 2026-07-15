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
    return f"{c.protocol}://{c.host}/fmi/odata/v4/databases/{c.database}"


class TestFMODataClientAuth:

    @pytest.mark.asyncio
    async def test_basic_auth_on_request(self, httpx_mock, odata_config, odata_base_url):
        """Should send Basic Auth header on every request."""
        httpx_mock.add_response(
            method="GET",
            url=f"{odata_base_url}/tables/Contacts?%24top=10&%24skip=0",
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
            url=f"{odata_base_url}/tables/Contacts?%24top=10&%24skip=0",
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
            url=f"{odata_base_url}/tables/Contacts?%24top=50&%24skip=0",
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
            url=f"{odata_base_url}/tables/Contacts('42')",
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
            url=f"{odata_base_url}/tables/Contacts",
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
            url=f"{odata_base_url}/tables/Contacts('42')",
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
            url=f"{odata_base_url}/tables/Contacts('42')",
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
            url=f"{odata_base_url}/tables/Contacts?%24filter=NAME+eq+%27Alice%27&%24top=100&%24skip=0",
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
        result = await client.run_script("ExportPDF", "invoice_123")

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
            url=f"{odata_base_url}/tables",
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
            url=f"{odata_base_url}/tables/X?%24top=1&%24skip=0",
            json={"value": []},
        )

        client = FMODataClient(odata_config)
        await client.get_records("X", limit=1)
        await client.close()
        # Should not raise
