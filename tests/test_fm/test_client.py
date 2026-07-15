import json
import pytest
from filemaker_gateway.config.schema import FMDataAPIConfig
from filemaker_gateway.fm.client import FMDataClient
from filemaker_gateway.fm.errors import FMAuthError, FMNotFoundError


@pytest.fixture
def fm_config():
    return FMDataAPIConfig(
        host="fm.example.com",
        database="MyDB",
        username="admin",
        password="secret",
        protocol="https",
        verify_ssl=True,
        enabled=True,
    )


@pytest.fixture
def fm_base_url(fm_config):
    c = fm_config
    return f"{c.protocol}://{c.host}/fmi/data/vLatest/databases/{c.database}"


class TestFMDataClientAuth:

    @pytest.mark.asyncio
    async def test_login_on_first_request(self, httpx_mock, fm_config, fm_base_url):
        """Should call /sessions on first API request."""
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/sessions",
            json={"response": {"token": "test-token-123"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records?_offset=1&_limit=10",
            json={"response": {"data": [], "dataInfo": {"foundCount": 0, "returnedCount": 0, "totalRecordCount": 0}}},
        )

        client = FMDataClient(fm_config)
        records = await client.get_records("Contacts", limit=10)

        assert records == []
        # Verify login was called
        login_request = httpx_mock.get_requests(method="POST")[0]
        assert "/sessions" in str(login_request.url)

    @pytest.mark.asyncio
    async def test_login_failure_raises_auth_error(self, httpx_mock, fm_config, fm_base_url):
        """Should raise FMAuthError on 401 from /sessions."""
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/sessions",
            status_code=401,
            json={"messages": [{"code": "212", "message": "Authentication failed"}], "response": {}},
        )

        client = FMDataClient(fm_config)
        with pytest.raises(FMAuthError):
            await client.get_records("Contacts")

    @pytest.mark.asyncio
    async def test_token_reuse_within_session(self, httpx_mock, fm_config, fm_base_url):
        """Should only login once for multiple requests."""
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/sessions",
            json={"response": {"token": "test-token"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/A/records?_offset=1&_limit=10",
            json={"response": {"data": [], "dataInfo": {"foundCount": 0, "returnedCount": 0, "totalRecordCount": 0}}},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/B/records?_offset=1&_limit=10",
            json={"response": {"data": [], "dataInfo": {"foundCount": 0, "returnedCount": 0, "totalRecordCount": 0}}},
        )

        client = FMDataClient(fm_config)
        await client.get_records("A", limit=10)
        await client.get_records("B", limit=10)

        # Only one login call
        login_calls = [r for r in httpx_mock.get_requests() if r.method == "POST"]
        assert len(login_calls) == 1


class TestFMDataClientCRUD:

    @pytest.mark.asyncio
    async def test_get_records(self, httpx_mock, fm_config, fm_base_url):
        """Should GET records from a layout."""
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records?_offset=1&_limit=50",
            json={
                "response": {
                    "data": [
                        {"fieldData": {"id": "1", "name": "Alice"}, "recordId": "1", "modId": "0"}
                    ],
                    "dataInfo": {"foundCount": 1, "returnedCount": 1, "totalRecordCount": 100},
                }
            },
        )

        client = FMDataClient(fm_config)
        records = await client.get_records("Contacts", limit=50)

        assert len(records) == 1
        assert records[0]["fieldData"]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_get_record_by_id(self, httpx_mock, fm_config, fm_base_url):
        """Should GET a single record by ID."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records/42",
            json={"response": {"data": [{"fieldData": {"name": "Bob"}, "recordId": "42", "modId": "1"}]}},
        )

        client = FMDataClient(fm_config)
        record = await client.get_record("Contacts", "42")

        assert record["fieldData"]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_get_record_not_found(self, httpx_mock, fm_config, fm_base_url):
        """Should raise FMNotFoundError on 404."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records/999",
            status_code=404,
            json={"messages": [{"code": "101", "message": "Record is missing"}], "response": {}},
        )

        client = FMDataClient(fm_config)
        with pytest.raises(FMNotFoundError):
            await client.get_record("Contacts", "999")

    @pytest.mark.asyncio
    async def test_create_record(self, httpx_mock, fm_config, fm_base_url):
        """Should POST to create a record."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/layouts/Contacts/records",
            json={"response": {"recordId": "99", "modId": "0"}, "messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        result = await client.create_record("Contacts", {"name": "Charlie"})

        assert result["recordId"] == "99"

        # Verify request body
        post_req = [r for r in httpx_mock.get_requests() if r.method == "POST" and "/records" in str(r.url)][0]
        body = json.loads(post_req.content)
        assert body["fieldData"]["name"] == "Charlie"

    @pytest.mark.asyncio
    async def test_update_record(self, httpx_mock, fm_config, fm_base_url):
        """Should PATCH to update a record."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="PATCH",
            url=f"{fm_base_url}/layouts/Contacts/records/42",
            json={"response": {"modId": "2"}, "messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        result = await client.update_record("Contacts", "42", {"name": "Updated"})

        assert result["modId"] == "2"

    @pytest.mark.asyncio
    async def test_delete_record(self, httpx_mock, fm_config, fm_base_url):
        """Should DELETE a record."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="DELETE",
            url=f"{fm_base_url}/layouts/Contacts/records/42",
            json={"messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        # Should not raise
        await client.delete_record("Contacts", "42")

    @pytest.mark.asyncio
    async def test_find_records(self, httpx_mock, fm_config, fm_base_url):
        """Should POST to _find endpoint."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/layouts/Contacts/_find",
            json={"response": {"data": [{"fieldData": {"name": "Alice"}, "recordId": "1", "modId": "0"}]}},
        )

        client = FMDataClient(fm_config)
        results = await client.find("Contacts", [{"name": "Alice"}])

        assert len(results) == 1
        assert results[0]["fieldData"]["name"] == "Alice"


class TestFMDataClientScripts:

    @pytest.mark.asyncio
    async def test_run_script(self, httpx_mock, fm_config, fm_base_url):
        """Should call script endpoint."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/script/Export%20PDF?script.param=invoice_123",
            json={"response": {"scriptResult": "OK"}, "messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        result = await client.run_script("Contacts", "Export PDF", "invoice_123")

        assert result["scriptResult"] == "OK"


class TestFMDataClientMetadata:

    @pytest.mark.asyncio
    async def test_get_layouts(self, httpx_mock, fm_config, fm_base_url):
        """Should return layout names."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts",
            json={"response": {"data": [{"name": "Contacts"}, {"name": "Invoices"}]}},
        )

        client = FMDataClient(fm_config)
        layouts = await client.get_layouts()

        assert layouts == ["Contacts", "Invoices"]


class TestFMDataClientContainer:

    @pytest.mark.asyncio
    async def test_upload_container(self, httpx_mock, fm_config, fm_base_url, tmp_path):
        """Should upload a file to a container field."""
        file_path = tmp_path / "test.png"
        file_path.write_text("fake-image-data")

        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{fm_base_url}/layouts/Contacts/records/1/containers/Photo/1",
            json={"messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        result = await client.upload_container("Contacts", "1", "Photo", str(file_path))

        assert result is True

    @pytest.mark.asyncio
    async def test_get_container_url(self, httpx_mock, fm_config, fm_base_url):
        """Should return a container download URL."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        # Container URL comes from metadata
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/Contacts/records/1",
            json={"response": {"data": [{"fieldData": {"Photo": "https://fm.example.com/stream/abc123"}, "recordId": "1", "modId": "0"}]}},
        )

        client = FMDataClient(fm_config)
        url = await client.get_container_url("Contacts", "1", "Photo")

        assert url == "https://fm.example.com/stream/abc123"


class TestFMDataClientClose:

    @pytest.mark.asyncio
    async def test_close_logs_out(self, httpx_mock, fm_config, fm_base_url):
        """Should DELETE session on close."""
        httpx_mock.add_response(
            method="POST", url=f"{fm_base_url}/sessions",
            json={"response": {"token": "tk"}, "messages": [{"code": "0"}]},
        )
        httpx_mock.add_response(
            method="DELETE",
            url=f"{fm_base_url}/sessions/tk",
            json={"messages": [{"code": "0"}]},
        )

        client = FMDataClient(fm_config)
        # Trigger login first
        httpx_mock.add_response(
            method="GET",
            url=f"{fm_base_url}/layouts/x/records?_offset=1&_limit=1",
            json={"response": {"data": [], "dataInfo": {"foundCount": 0, "returnedCount": 0, "totalRecordCount": 0}}},
        )
        await client.get_records("x", limit=1)

        await client.close()
        # Verify DELETE /sessions/tk was called
        delete_calls = [r for r in httpx_mock.get_requests() if r.method == "DELETE"]
        assert len(delete_calls) == 1
