from __future__ import annotations

from typing import Any

import httpx
import pytest
from anthropic.types.beta import (
    BetaMemoryTool20250818CreateCommand,
    BetaMemoryTool20250818DeleteCommand,
    BetaMemoryTool20250818InsertCommand,
    BetaMemoryTool20250818RenameCommand,
    BetaMemoryTool20250818StrReplaceCommand,
    BetaMemoryTool20250818ViewCommand,
)

import memorylake
from memorylake.async_memorylake_memorytool import (
    AsyncMemoryLakeMemoryTool,
    AsyncMemoryLakeMemoryToolError,
)
from memorylake.memorylake_memorytool import (
    MemoryLakeMemoryTool,
    MemoryLakeMemoryToolError,
)

_COMMAND_ORDER = [
    "create",
    "str_replace",
    "insert",
    "delete",
    "rename",
    "clear_all_memory",
    "exists",
    "list",
    "stats",
]


class _DummyResponse:
    def __init__(self, data: Any) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._data


class _DummyAsyncResponse:
    def __init__(self, data: Any) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._data


class _DummyClient:
    def __init__(self, *, base_url: str, timeout: float, headers: dict[str, str], **_: Any) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
        self.calls.append((endpoint, json))
        command = json["payload"]["command"]
        if command == "create":
            return _DummyResponse({"content": "created"})
        if command == "str_replace":
            return _DummyResponse({"content": "replaced"})
        if command == "insert":
            return _DummyResponse({"content": "inserted"})
        if command == "delete":
            return _DummyResponse({"content": "deleted"})
        if command == "rename":
            return _DummyResponse({"content": "renamed"})
        if command == "clear_all_memory":
            return _DummyResponse({"content": "cleared"})
        if command == "list":
            return _DummyResponse({"memories": ["/memories/a.txt", "/memories/b/"]})
        if command == "stats":
            return _DummyResponse({"files": 2, "directories": 1, "bytes": 10})
        if command == "exists":
            return _DummyResponse({"exists": True})
        return _DummyResponse({"content": "ok"})

    def close(self) -> None:
        self.closed = True


class _DummyAsyncClient:
    def __init__(self, *, base_url: str, timeout: float, headers: dict[str, str], **_: Any) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
        self.calls.append((endpoint, json))
        command = json["payload"]["command"]
        if command == "view":
            return _DummyAsyncResponse({"content": "async-view"})
        if command == "create":
            return _DummyAsyncResponse({"content": "async-create"})
        if command == "str_replace":
            return _DummyAsyncResponse({"content": "async-replace"})
        if command == "insert":
            return _DummyAsyncResponse({"content": "async-insert"})
        if command == "delete":
            return _DummyAsyncResponse({"content": "async-delete"})
        if command == "rename":
            return _DummyAsyncResponse({"content": "async-rename"})
        if command == "clear_all_memory":
            return _DummyAsyncResponse({"content": "async-clear"})
        if command == "list":
            return _DummyAsyncResponse({"memories": ["/memories/x.txt"]})
        if command == "stats":
            return _DummyAsyncResponse({"files": 1, "directories": 0, "bytes": 5})
        if command == "exists":
            return _DummyAsyncResponse({"exists": False})
        return _DummyAsyncResponse({"content": "async-ok"})

    async def aclose(self) -> None:
        self.closed = True

    async def __aenter__(self) -> "_DummyAsyncClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        self.closed = True


def _assert_common_headers(headers: dict[str, str]) -> None:
    assert headers["x-memorylake-client-version"] == memorylake.__version__
    assert headers["Authorization"] == "token"


def test_remote_tool_returns_plain_string(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    class _StringClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            self.calls.append((endpoint, json))
            return _DummyResponse("string-response")

    monkeypatch.setattr(module.httpx, "Client", _StringClient)

    tool = MemoryLakeMemoryTool(
        base_url="https://api.example.com/",
        memory_id="mem-string",
        headers={"Authorization": "token"},
    )

    result = tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/plain.txt",
            view_range=[1, 2],
        ),
    )
    assert result == "string-response"

    client: _DummyClient = tool._client  # type: ignore[assignment]
    (_, payload) = client.calls[0]
    assert payload["payload"]["view_range"] == [1, 2]


def test_remote_tool_http_error_text_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    request = httpx.Request("POST", "https://api.example.com/public/v1/memory-tool")
    response = httpx.Response(502, request=request, content=b"<!DOCTYPE html>")

    class _HttpErrorTextClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            del endpoint, json
            raise httpx.HTTPStatusError("fail", request=request, response=response)

    monkeypatch.setattr(module.httpx, "Client", _HttpErrorTextClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-http-text")

    with pytest.raises(MemoryLakeMemoryToolError) as excinfo:
        tool.create(
            BetaMemoryTool20250818CreateCommand(
                command="create",
                path="/memories/plain.txt",
                file_text="text",
            ),
        )

    assert "<!DOCTYPE html>" in str(excinfo.value)


def test_remote_tool_memory_exists_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    class _ExistsErrorClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            if json["payload"]["command"] == "exists":
                raise httpx.RequestError("exists-fail", request=httpx.Request("POST", "https://api.example.com"))
            return super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "Client", _ExistsErrorClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-exists")

    with pytest.raises(MemoryLakeMemoryToolError):
        tool.memory_exists("/memories/missing.txt")


def test_remote_tool_list_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    class _ListInvalidClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            if json["payload"]["command"] == "list":
                self.calls.append((endpoint, json))
                return _DummyResponse({"memories": "oops"})
            return super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "Client", _ListInvalidClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-list-invalid")

    with pytest.raises(MemoryLakeMemoryToolError):
        tool.list_memories("/memories")


def test_remote_tool_list_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    request = httpx.Request("POST", "https://api.example.com/public/v1/memory-tool")
    response = httpx.Response(404, request=request, json={"error": "listfail"})

    class _ListHttpErrorClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            if json["payload"]["command"] == "list":
                raise httpx.HTTPStatusError("fail", request=request, response=response)
            return super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "Client", _ListHttpErrorClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-list-error")

    with pytest.raises(MemoryLakeMemoryToolError) as excinfo:
        tool.list_memories("/memories")

    assert "listfail" in str(excinfo.value)


def test_remote_tool_stats_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    class _StatsInvalidClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            if json["payload"]["command"] == "stats":
                self.calls.append((endpoint, json))
                return _DummyResponse(["not", "mapping"])
            return super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "Client", _StatsInvalidClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-stats-invalid")

    with pytest.raises(MemoryLakeMemoryToolError):
        tool.stats()


def test_remote_tool_stats_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    request = httpx.Request("POST", "https://api.example.com/public/v1/memory-tool")
    response = httpx.Response(503, request=request, json={"error": "statsfail"})

    class _StatsHttpErrorClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            if json["payload"]["command"] == "stats":
                raise httpx.HTTPStatusError("fail", request=request, response=response)
            return super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "Client", _StatsHttpErrorClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-stats-error")

    with pytest.raises(MemoryLakeMemoryToolError) as excinfo:
        tool.stats()

    assert "statsfail" in str(excinfo.value)


def test_remote_tool_uses_version_header(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    monkeypatch.setattr(module.httpx, "Client", _DummyClient)

    tool = MemoryLakeMemoryTool(
        base_url="https://api.example.com/",
        memory_id="mem-123",
        headers={"Authorization": "token"},
    )

    response = tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/one.txt",
            file_text="hello",
        ),
    )
    assert response == "created"

    replace_response = tool.str_replace(
        BetaMemoryTool20250818StrReplaceCommand(
            command="str_replace",
            path="/memories/one.txt",
            old_str="hello",
            new_str="world",
        ),
    )
    assert replace_response == "replaced"

    insert_response = tool.insert(
        BetaMemoryTool20250818InsertCommand(
            command="insert",
            path="/memories/one.txt",
            insert_line=1,
            insert_text="line",
        ),
    )
    assert insert_response == "inserted"

    delete_response = tool.delete(
        BetaMemoryTool20250818DeleteCommand(command="delete", path="/memories/one.txt"),
    )
    assert delete_response == "deleted"

    rename_response = tool.rename(
        BetaMemoryTool20250818RenameCommand(
            command="rename",
            old_path="/memories/one.txt",
            new_path="/memories/two.txt",
        ),
    )
    assert rename_response == "renamed"

    clear_response = tool.clear_all_memory()
    assert clear_response == "cleared"

    assert tool.memory_exists("/memories/one.txt") is True

    listed = tool.list_memories("/memories")
    assert listed == ["/memories/a.txt", "/memories/b/"]

    stats = tool.stats()
    assert stats == {"files": 2, "directories": 1, "bytes": 10}

    client: _DummyClient = tool._client  # type: ignore[assignment]
    assert client.base_url == "https://api.example.com"
    _assert_common_headers(client.headers)

    assert len(client.calls) >= len(_COMMAND_ORDER)
    for entry_call, expected_command in zip(client.calls, _COMMAND_ORDER):
        endpoint, payload = entry_call
        assert endpoint == "/public/v1/memory-tool"
        assert payload["payload"]["command"] == expected_command

    raw_result = tool.execute_tool_payload(
        {"command": "view", "path": "/memories/one.txt"},
    )
    assert raw_result == "ok"


@pytest.mark.asyncio
async def test_async_remote_tool_uses_version_header(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as async_module

    monkeypatch.setattr(async_module.httpx, "AsyncClient", _DummyAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(
        base_url="https://api.example.com/",
        memory_id="mem-async",
        headers={"Authorization": "token"},
    )

    response = await tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/two.txt",
        ),
    )
    assert response == "async-view"

    create_result = await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/two.txt",
            file_text="hello",
        ),
    )
    assert create_result == "async-create"

    replace_result = await tool.str_replace(
        BetaMemoryTool20250818StrReplaceCommand(
            command="str_replace",
            path="/memories/two.txt",
            old_str="hello",
            new_str="world",
        ),
    )
    assert replace_result == "async-replace"

    insert_result = await tool.insert(
        BetaMemoryTool20250818InsertCommand(
            command="insert",
            path="/memories/two.txt",
            insert_line=1,
            insert_text="line",
        ),
    )
    assert insert_result == "async-insert"

    delete_result = await tool.delete(
        BetaMemoryTool20250818DeleteCommand(
            command="delete",
            path="/memories/two.txt",
        ),
    )
    assert delete_result == "async-delete"

    rename_result = await tool.rename(
        BetaMemoryTool20250818RenameCommand(
            command="rename",
            old_path="/memories/two.txt",
            new_path="/memories/three.txt",
        ),
    )
    assert rename_result == "async-rename"

    clear_result = await tool.clear_all_memory()
    assert clear_result == "async-clear"

    exists = await tool.memory_exists("/memories/three.txt")
    assert exists is False

    listed = await tool.list_memories("/memories")
    assert listed == ["/memories/x.txt"]

    stats = await tool.stats()
    assert stats == {"files": 1, "directories": 0, "bytes": 5}

    exec_result = await tool.execute_tool_payload(
        {"command": "view", "path": "/memories/two.txt"},
    )
    assert exec_result == "async-view"

    client: _DummyAsyncClient = tool._client  # type: ignore[assignment]
    assert client.base_url == "https://api.example.com"
    _assert_common_headers(client.headers)

    assert len(client.calls) >= 2
    endpoint, payload = client.calls[0]
    assert endpoint == "/public/v1/memory-tool"
    assert payload["payload"]["command"] == "view"
    assert payload["payload"]["path"] == "/memories/two.txt"

    await tool.close()
    assert client.closed is True


def test_remote_tool_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    class _ErrorClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            del endpoint, json
            return _DummyResponse({"error": "boom"})

    monkeypatch.setattr(module.httpx, "Client", _ErrorClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-err")

    with pytest.raises(MemoryLakeMemoryToolError) as excinfo:
        tool.clear_all_memory()

    assert "boom" in str(excinfo.value)


def test_remote_tool_invalid_content(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    class _InvalidClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            del endpoint, json
            return _DummyResponse({})

    monkeypatch.setattr(module.httpx, "Client", _InvalidClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-invalid")

    with pytest.raises(MemoryLakeMemoryToolError):
        tool.view(BetaMemoryTool20250818ViewCommand(command="view", path="/a.txt"))


def test_remote_tool_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    request = httpx.Request("POST", "https://api.example.com/public/v1/memory-tool")
    response = httpx.Response(500, request=request, json={"error": "server"})

    class _HttpErrorClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            del endpoint, json
            raise httpx.HTTPStatusError("fail", request=request, response=response)

    monkeypatch.setattr(module.httpx, "Client", _HttpErrorClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-http")

    with pytest.raises(MemoryLakeMemoryToolError) as excinfo:
        tool.clear_all_memory()

    assert "server" in str(excinfo.value)


def test_remote_tool_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import memorylake_memorytool as module

    class _RequestErrorClient(_DummyClient):
        def post(self, endpoint: str, json: dict[str, Any]) -> _DummyResponse:
            del endpoint, json
            raise httpx.RequestError("boom", request=httpx.Request("POST", "https://api.example.com"))

    monkeypatch.setattr(module.httpx, "Client", _RequestErrorClient)

    tool = MemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-request")

    with pytest.raises(MemoryLakeMemoryToolError):
        tool.clear_all_memory()


@pytest.mark.asyncio
async def test_async_context_manager_closes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    monkeypatch.setattr(module.httpx, "AsyncClient", _DummyAsyncClient)

    async with AsyncMemoryLakeMemoryTool(
        base_url="https://api.example.com/",
        memory_id="mem-ctx",
        headers={"Authorization": "token"},
    ) as tool:
        client: _DummyAsyncClient = tool._client  # type: ignore[assignment]
        assert client.base_url == "https://api.example.com"
    assert client.closed is True


@pytest.mark.asyncio
async def test_async_close_after_enter(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    monkeypatch.setattr(module.httpx, "AsyncClient", _DummyAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(
        base_url="https://api.example.com/",
        memory_id="mem-close",
        headers={"Authorization": "token"},
    )
    await tool.__aenter__()
    client: _DummyAsyncClient = tool._client  # type: ignore[assignment]
    await tool.close()
    assert client.closed is True
    await tool.close()


@pytest.mark.asyncio
async def test_async_view_string_response_with_range(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    class _StringAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            self.calls.append((endpoint, json))
            return _DummyAsyncResponse("raw-async")

    monkeypatch.setattr(module.httpx, "AsyncClient", _StringAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(
        base_url="https://api.example.com/",
        memory_id="mem-async-string",
        headers={"Authorization": "token"},
    )

    result = await tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/range.txt",
            view_range=[5, 10],
        ),
    )
    assert result == "raw-async"

    client: _StringAsyncClient = tool._client  # type: ignore[assignment]
    (_, payload) = client.calls[0]
    assert payload["payload"]["view_range"] == [5, 10]


@pytest.mark.asyncio
async def test_async_http_error_text_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    request = httpx.Request("POST", "https://api.example.com/public/v1/memory-tool")
    response = httpx.Response(500, request=request, content=b"<error>oops</error>")

    class _HttpErrorAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            del endpoint, json
            raise httpx.HTTPStatusError("fail", request=request, response=response)

    monkeypatch.setattr(module.httpx, "AsyncClient", _HttpErrorAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-http-async")

    with pytest.raises(AsyncMemoryLakeMemoryToolError) as excinfo:
        await tool.create(
            BetaMemoryTool20250818CreateCommand(
                command="create",
                path="/memories/range.txt",
                file_text="data",
            ),
        )

    assert "<error>oops</error>" in str(excinfo.value)


@pytest.mark.asyncio
async def test_async_memory_exists_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    class _ExistsAsyncErrorClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            if json["payload"]["command"] == "exists":
                raise httpx.RequestError("exists-async", request=httpx.Request("POST", "https://api.example.com"))
            return await super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "AsyncClient", _ExistsAsyncErrorClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-exists-async")

    with pytest.raises(AsyncMemoryLakeMemoryToolError):
        await tool.memory_exists("/memories/fail.txt")


@pytest.mark.asyncio
async def test_async_list_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    class _ListInvalidAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            if json["payload"]["command"] == "list":
                self.calls.append((endpoint, json))
                return _DummyAsyncResponse({"memories": "oops"})
            return await super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "AsyncClient", _ListInvalidAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-list-async")

    with pytest.raises(AsyncMemoryLakeMemoryToolError):
        await tool.list_memories("/memories")


@pytest.mark.asyncio
async def test_async_list_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    request = httpx.Request("POST", "https://api.example.com/public/v1/memory-tool")
    response = httpx.Response(400, request=request, json={"error": "async-list"})

    class _ListHttpErrorAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            if json["payload"]["command"] == "list":
                raise httpx.HTTPStatusError("fail", request=request, response=response)
            return await super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "AsyncClient", _ListHttpErrorAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-list-http")

    with pytest.raises(AsyncMemoryLakeMemoryToolError) as excinfo:
        await tool.list_memories("/memories")

    assert "async-list" in str(excinfo.value)


@pytest.mark.asyncio
async def test_async_stats_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    class _StatsInvalidAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            if json["payload"]["command"] == "stats":
                self.calls.append((endpoint, json))
                return _DummyAsyncResponse("not-a-mapping")
            return await super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "AsyncClient", _StatsInvalidAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-stats-async")

    with pytest.raises(AsyncMemoryLakeMemoryToolError):
        await tool.stats()


@pytest.mark.asyncio
async def test_async_stats_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    request = httpx.Request("POST", "https://api.example.com/public/v1/memory-tool")
    response = httpx.Response(429, request=request, json={"error": "async-stats"})

    class _StatsHttpErrorAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            if json["payload"]["command"] == "stats":
                raise httpx.HTTPStatusError("fail", request=request, response=response)
            return await super().post(endpoint, json)

    monkeypatch.setattr(module.httpx, "AsyncClient", _StatsHttpErrorAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-stats-http")

    with pytest.raises(AsyncMemoryLakeMemoryToolError) as excinfo:
        await tool.stats()

    assert "async-stats" in str(excinfo.value)


@pytest.mark.asyncio
async def test_async_reenter_after_close(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    monkeypatch.setattr(module.httpx, "AsyncClient", _DummyAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-closed")

    await tool.close()

    with pytest.raises(AsyncMemoryLakeMemoryToolError):
        await tool.__aenter__()


@pytest.mark.asyncio
async def test_async_remote_tool_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    class _ErrorAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            del endpoint, json
            return _DummyAsyncResponse({"error": "async-boom"})

    monkeypatch.setattr(module.httpx, "AsyncClient", _ErrorAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-err")

    with pytest.raises(AsyncMemoryLakeMemoryToolError):
        await tool.clear_all_memory()


@pytest.mark.asyncio
async def test_async_remote_tool_invalid_content(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    class _InvalidAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            del endpoint, json
            return _DummyAsyncResponse({})

    monkeypatch.setattr(module.httpx, "AsyncClient", _InvalidAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-invalid")

    with pytest.raises(AsyncMemoryLakeMemoryToolError):
        await tool.view(BetaMemoryTool20250818ViewCommand(command="view", path="/a.txt"))


@pytest.mark.asyncio
async def test_async_remote_tool_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    request = httpx.Request("POST", "https://api.example.com/public/v1/memory-tool")
    response = httpx.Response(404, request=request, json={"error": "missing"})

    class _HttpErrorAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            del endpoint, json
            raise httpx.HTTPStatusError("fail", request=request, response=response)

    monkeypatch.setattr(module.httpx, "AsyncClient", _HttpErrorAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-http")

    with pytest.raises(AsyncMemoryLakeMemoryToolError) as excinfo:
        await tool.clear_all_memory()

    assert "missing" in str(excinfo.value)


@pytest.mark.asyncio
async def test_async_remote_tool_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorylake import async_memorylake_memorytool as module

    class _RequestErrorAsyncClient(_DummyAsyncClient):
        async def post(self, endpoint: str, json: dict[str, Any]) -> _DummyAsyncResponse:
            del endpoint, json
            raise httpx.RequestError("boom", request=httpx.Request("POST", "https://api.example.com"))

    monkeypatch.setattr(module.httpx, "AsyncClient", _RequestErrorAsyncClient)

    tool = AsyncMemoryLakeMemoryTool(base_url="https://api.example.com", memory_id="mem-request")

    with pytest.raises(AsyncMemoryLakeMemoryToolError):
        await tool.clear_all_memory()
