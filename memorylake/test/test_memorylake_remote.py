from __future__ import annotations

import json
import threading
from collections.abc import AsyncGenerator, Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import PurePosixPath
from typing import Any, ClassVar, Optional, cast

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
from typing_extensions import override

import memorylake
from memorylake.async_memorylake_memorytool import (
    AsyncMemoryLakeMemoryTool,
    AsyncMemoryLakeMemoryToolError,
)
from memorylake.memorylake_memorytool import (
    MemoryLakeMemoryTool,
    MemoryLakeMemoryToolError,
)

JsonDict = dict[str, Any]
OverrideCallable = Callable[[JsonDict], tuple[int, Any]]


def _dict_with_string_keys(source: Mapping[object, object]) -> JsonDict:
    return {str(key): value for key, value in source.items()}


@dataclass()
class _RecordedRequest:
    headers: dict[str, str]
    payload: JsonDict


class _MemoryLakeHTTPServer(ThreadingHTTPServer):
    memory_id: ClassVar[str] = "mem-test"

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _MemoryLakeRequestHandler)
        self.files: dict[str, str] = {}
        self.request_log: list[_RecordedRequest] = []
        self.response_overrides: dict[str, OverrideCallable] = {}
        self._lock: threading.Lock = threading.Lock()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def reset(self) -> None:
        with self._lock:
            self.files.clear()
            self.request_log.clear()
            self.response_overrides.clear()

    def record_request(self, headers: dict[str, str], payload: JsonDict) -> None:
        with self._lock:
            self.request_log.append(_RecordedRequest(headers=headers, payload=payload))

    def set_override(
        self,
        command: str,
        provider: OverrideCallable,
    ) -> None:
        with self._lock:
            self.response_overrides[command] = provider

    def get_override(self, command: str) -> Optional[OverrideCallable]:
        with self._lock:
            return self.response_overrides.get(command)

    def clear_override(self, command: str) -> None:
        with self._lock:
            self.response_overrides.pop(command, None)

    def handle_command(self, command: str, payload: JsonDict) -> tuple[int, Any]:
        override = self.get_override(command)
        if override is not None:
            return override(payload)

        if command == "create":
            return 200, self._create(payload)
        if command == "view":
            return 200, self._view(payload)
        if command == "str_replace":
            return 200, self._str_replace(payload)
        if command == "insert":
            return 200, self._insert(payload)
        if command == "delete":
            return 200, self._delete(payload)
        if command == "rename":
            return 200, self._rename(payload)
        if command == "clear_all_memory":
            return 200, self._clear_all_memory()
        if command == "exists":
            return 200, self._exists(payload)
        if command == "list":
            return 200, self._list()
        if command == "stats":
            return 200, self._stats()

        return 400, {"error": f"unsupported command: {command}"}

    def _create(self, payload: JsonDict) -> dict[str, str]:
        path = str(payload["path"])
        text = str(payload.get("file_text", ""))
        with self._lock:
            self.files[path] = text
        return {"content": "created"}

    def _view(self, payload: JsonDict) -> dict[str, str]:
        path = str(payload["path"])
        view_range: object | None = payload.get("view_range")

        with self._lock:
            if path.endswith("/"):
                entries = self._directory_entries(path)
                content = "\n".join(entries)
                return {"content": content}

            text = self.files.get(path)

        if text is None:
            return {"error": f"path not found: {path}"}

        lines: list[str] = list(text.splitlines())
        if isinstance(view_range, list) and len(view_range) == 2:
            range_list = cast(list[object], view_range)
            first_candidate: object = range_list[0]
            second_candidate: object = range_list[1]
            if isinstance(first_candidate, int) and isinstance(second_candidate, int):
                start_index = max(first_candidate - 1, 0)
                end_index = len(lines) if second_candidate == -1 else max(second_candidate, start_index + 1)
                lines = lines[start_index:end_index]
        content = "\n".join(lines)
        return {"content": content}

    def _str_replace(self, payload: JsonDict) -> dict[str, str]:
        path = str(payload["path"])
        old = str(payload.get("old_str", ""))
        new = str(payload.get("new_str", ""))
        with self._lock:
            text = self.files.get(path, "")
            self.files[path] = text.replace(old, new)
        return {"content": "replaced"}

    def _insert(self, payload: JsonDict) -> dict[str, str]:
        path = str(payload["path"])
        line_index = int(payload.get("insert_line", 0))
        insert_text = str(payload.get("insert_text", ""))
        with self._lock:
            text = self.files.get(path, "")
            lines = text.splitlines()
            line_count = len(lines)
            min_allowed = 0
            if line_index < min_allowed:
                line_index = min_allowed
            if line_index > line_count:
                line_index = line_count

            if line_index == 0:
                insert_at = 0
            elif line_index >= line_count:
                insert_at = line_count
            else:
                insert_at = line_index

            lines.insert(insert_at, insert_text)
            self.files[path] = "\n".join(lines)
        return {"content": "inserted"}

    def _delete(self, payload: JsonDict) -> dict[str, str]:
        path = str(payload["path"])
        with self._lock:
            if path.endswith("/"):
                keys = [key for key in self.files if key.startswith(path)]
                for key in keys:
                    self.files.pop(key, None)
                return {"content": "deleted"}

            if path in self.files:
                self.files.pop(path, None)
                return {"content": "deleted"}

        return {"error": f"path not found: {path}"}

    def _rename(self, payload: JsonDict) -> dict[str, str]:
        old_path = str(payload.get("old_path"))
        new_path = str(payload.get("new_path"))
        with self._lock:
            if old_path not in self.files:
                return {"error": f"source missing: {old_path}"}
            self.files[new_path] = self.files.pop(old_path)
        return {"content": "renamed"}

    def _clear_all_memory(self) -> dict[str, str]:
        with self._lock:
            self.files.clear()
        return {"content": "cleared"}

    def _exists(self, payload: JsonDict) -> dict[str, Any]:
        path = str(payload.get("path"))
        with self._lock:
            exists = path in self.files or any(key.startswith(f"{path.rstrip('/')}/") for key in self.files)
        return {"exists": exists}

    def _list(self) -> dict[str, Any]:
        with self._lock:
            files = list(self.files.keys())

        directories: set[str] = set()
        for file_path in files:
            current = PurePosixPath(file_path)
            for parent in current.parents:
                parent_str = str(parent)
                if parent_str.startswith("/memories") and parent_str != "/":
                    directories.add(parent_str + "/")

        entries = sorted(directories.union(files))
        return {"memories": entries}

    def _stats(self) -> dict[str, int]:
        with self._lock:
            files = dict(self.files)

        directories: set[str] = set()
        byte_total = 0
        for path, content in files.items():
            byte_total += len(content.encode("utf-8"))
            current = PurePosixPath(path)
            for parent in current.parents:
                parent_str = str(parent)
                if parent_str.startswith("/memories") and parent_str != "/":
                    directories.add(parent_str)

        return {
            "files": len(files),
            "directories": len(directories),
            "bytes": byte_total,
        }

    def _directory_entries(self, path: str) -> list[str]:
        prefix = path.rstrip("/") + "/"
        entries: set[str] = set()
        for file_path in self.files:
            if not file_path.startswith(prefix):
                continue
            remainder = file_path[len(prefix):]
            parts = remainder.split("/", 1)
            if len(parts) == 1:
                entries.add(parts[0])
            else:
                entries.add(parts[0] + "/")
        return sorted(entries)


class _MemoryLakeRequestHandler(BaseHTTPRequestHandler):
    server: _MemoryLakeHTTPServer  # pyright: ignore[reportIncompatibleVariableOverride]

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler naming)
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload_obj = json.loads(raw_body.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid json"})
            return

        if not isinstance(payload_obj, dict):
            self._send_json(400, {"error": "invalid payload"})
            return

        payload: JsonDict = _dict_with_string_keys(cast(Mapping[object, object], payload_obj))

        headers_dict: dict[str, str] = {str(key): str(value) for key, value in self.headers.items()}
        self.server.record_request(headers_dict, payload)

        memory_id_value = payload.get("memory_id")
        if not isinstance(memory_id_value, str):
            self._send_json(403, {"error": "unknown memory id"})
            return

        if memory_id_value != self.server.memory_id:
            self._send_json(403, {"error": "unknown memory id"})
            return

        body_obj = payload.get("payload")
        if not isinstance(body_obj, dict):
            self._send_json(400, {"error": "invalid command payload"})
            return

        body: JsonDict = _dict_with_string_keys(cast(Mapping[object, object], body_obj))

        command = body.get("command")
        if not isinstance(command, str):
            self._send_json(400, {"error": "missing command"})
            return

        status, response_body = self.server.handle_command(command, body)
        self._send_json(status, response_body)

    @override
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - signature from parent
        return

    def _send_json(self, status: int, body: Any) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


@contextmanager
def _run_test_server() -> Generator[_MemoryLakeHTTPServer, None, None]:
    server = _MemoryLakeHTTPServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server.reset()
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture()
def memorylake_server() -> Generator[_MemoryLakeHTTPServer, None, None]:
    with _run_test_server() as server:
        yield server


@pytest.fixture()
def sync_tool(memorylake_server: _MemoryLakeHTTPServer) -> Generator[MemoryLakeMemoryTool, None, None]:
    tool = MemoryLakeMemoryTool(
        base_url=memorylake_server.base_url,
        memory_id=memorylake_server.memory_id,
        headers={"Authorization": "token"},
    )
    try:
        yield tool
    finally:
        tool.close()


@pytest.fixture()
async def async_tool(memorylake_server: _MemoryLakeHTTPServer) -> AsyncGenerator[AsyncMemoryLakeMemoryTool, None]:
    tool = AsyncMemoryLakeMemoryTool(
        base_url=memorylake_server.base_url,
        memory_id=memorylake_server.memory_id,
        headers={"Authorization": "token"},
    )
    try:
        yield tool
    finally:
        await tool.close()


@contextmanager
def override_command(
    server: _MemoryLakeHTTPServer,
    command: str,
    provider: OverrideCallable,
) -> Generator[None, None, None]:
    server.set_override(command, provider)
    try:
        yield
    finally:
        server.clear_override(command)


def test_remote_tool_full_workflow(sync_tool: MemoryLakeMemoryTool, memorylake_server: _MemoryLakeHTTPServer) -> None:
    create_result = sync_tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/one.txt",
            file_text="line-one\nline-two",
        ),
    )
    assert create_result == "created"

    view_result = sync_tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/one.txt",
        ),
    )
    assert "line-one" in view_result

    range_result = sync_tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/one.txt",
            view_range=[2, 2],
        ),
    )
    assert range_result.strip() == "line-two"

    replace_result = sync_tool.str_replace(
        BetaMemoryTool20250818StrReplaceCommand(
            command="str_replace",
            path="/memories/one.txt",
            old_str="line-two",
            new_str="line-three",
        ),
    )
    assert replace_result == "replaced"

    insert_result = sync_tool.insert(
        BetaMemoryTool20250818InsertCommand(
            command="insert",
            path="/memories/one.txt",
            insert_line=1,
            insert_text="line-inserted",
        ),
    )
    assert insert_result == "inserted"

    view_after_insert = sync_tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/one.txt",
        ),
    )
    assert view_after_insert.splitlines() == ["line-one", "line-inserted", "line-three"]

    rename_result = sync_tool.rename(
        BetaMemoryTool20250818RenameCommand(
            command="rename",
            old_path="/memories/one.txt",
            new_path="/memories/two.txt",
        ),
    )
    assert rename_result == "renamed"

    delete_result = sync_tool.delete(
        BetaMemoryTool20250818DeleteCommand(
            command="delete",
            path="/memories/two.txt",
        ),
    )
    assert delete_result == "deleted"

    with pytest.raises(MemoryLakeMemoryToolError):
        sync_tool.view(
            BetaMemoryTool20250818ViewCommand(
                command="view",
                path="/memories/two.txt",
            ),
        )

    cleared = sync_tool.clear_all_memory()
    assert cleared == "cleared"

    payload_result = sync_tool.execute_tool_payload(
        {
            "command": "create",
            "path": "/memories/payload.txt",
            "file_text": "payload",
        },
    )
    assert payload_result == "created"

    assert len(memorylake_server.request_log) >= 1


def test_remote_tool_uses_version_header(
    sync_tool: MemoryLakeMemoryTool,
    memorylake_server: _MemoryLakeHTTPServer,
) -> None:
    sync_tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/header.txt",
            file_text="body",
        ),
    )
    recorded = memorylake_server.request_log[0]
    header_map = {key.lower(): value for key, value in recorded.headers.items()}
    assert header_map["x-memorylake-client-version"] == memorylake.__version__
    assert header_map["authorization"] == "token"


def test_remote_tool_error_response(
    sync_tool: MemoryLakeMemoryTool,
    memorylake_server: _MemoryLakeHTTPServer,
) -> None:
    with override_command(
        memorylake_server,
        "clear_all_memory",
        lambda payload: (200, {"error": "boom"}),
    ):
        with pytest.raises(MemoryLakeMemoryToolError, match="boom"):
            sync_tool.clear_all_memory()


def test_remote_tool_invalid_content(
    sync_tool: MemoryLakeMemoryTool,
    memorylake_server: _MemoryLakeHTTPServer,
) -> None:
    with override_command(
        memorylake_server,
        "view",
        lambda payload: (200, {}),
    ):
        with pytest.raises(MemoryLakeMemoryToolError, match="Invalid response"):
            sync_tool.view(
                BetaMemoryTool20250818ViewCommand(
                    command="view",
                    path="/memories/missing.txt",
                ),
            )


def test_remote_tool_http_error(
    sync_tool: MemoryLakeMemoryTool,
    memorylake_server: _MemoryLakeHTTPServer,
) -> None:
    with override_command(
        memorylake_server,
        "clear_all_memory",
        lambda payload: (503, {"error": "server"}),
    ):
        with pytest.raises(MemoryLakeMemoryToolError, match="server"):
            sync_tool.clear_all_memory()


def test_remote_tool_request_error(monkeypatch: pytest.MonkeyPatch, sync_tool: MemoryLakeMemoryTool) -> None:
    def _raise_request_error(*_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.RequestError("boom", request=httpx.Request("POST", "http://example.com"))

    client_any: Any = getattr(sync_tool, "_client")
    monkeypatch.setattr(client_any, "post", _raise_request_error, raising=False)

    with pytest.raises(MemoryLakeMemoryToolError, match="Request failed"):
        sync_tool.clear_all_memory()


@pytest.mark.asyncio
async def test_async_remote_tool_full_workflow(
    async_tool: AsyncMemoryLakeMemoryTool,
    memorylake_server: _MemoryLakeHTTPServer,
) -> None:
    del memorylake_server
    await async_tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/async.txt",
            file_text="hello\nworld",
        ),
    )

    view_value = await async_tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/async.txt",
        ),
    )
    assert "hello" in view_value

    replace_result = await async_tool.str_replace(
        BetaMemoryTool20250818StrReplaceCommand(
            command="str_replace",
            path="/memories/async.txt",
            old_str="world",
            new_str="async",
        ),
    )
    assert replace_result == "replaced"

    await async_tool.insert(
        BetaMemoryTool20250818InsertCommand(
            command="insert",
            path="/memories/async.txt",
            insert_line=0,
            insert_text="intro",
        ),
    )

    post_insert_view = await async_tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/async.txt",
        ),
    )
    assert post_insert_view.splitlines()[0] == "intro"

    await async_tool.rename(
        BetaMemoryTool20250818RenameCommand(
            command="rename",
            old_path="/memories/async.txt",
            new_path="/memories/async-renamed.txt",
        ),
    )

    await async_tool.delete(
        BetaMemoryTool20250818DeleteCommand(
            command="delete",
            path="/memories/async-renamed.txt",
        ),
    )

    await async_tool.clear_all_memory()


@pytest.mark.asyncio
async def test_async_remote_tool_error(async_tool: AsyncMemoryLakeMemoryTool, memorylake_server: _MemoryLakeHTTPServer) -> None:
    with override_command(
        memorylake_server,
        "clear_all_memory",
        lambda payload: (200, {"error": "async-fail"}),
    ):
        with pytest.raises(AsyncMemoryLakeMemoryToolError, match="async-fail"):
            await async_tool.clear_all_memory()


@pytest.mark.asyncio
async def test_async_remote_tool_http_error(
    async_tool: AsyncMemoryLakeMemoryTool,
    memorylake_server: _MemoryLakeHTTPServer,
) -> None:
    with override_command(
        memorylake_server,
        "clear_all_memory",
        lambda payload: (502, {"error": "bad-gateway"}),
    ):
        with pytest.raises(AsyncMemoryLakeMemoryToolError, match="bad-gateway"):
            await async_tool.clear_all_memory()


@pytest.mark.asyncio
async def test_async_remote_tool_request_error(
    async_tool: AsyncMemoryLakeMemoryTool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_request_error(*_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.RequestError("async-boom", request=httpx.Request("POST", "http://example.com"))

    client_any: Any = getattr(async_tool, "_client")
    monkeypatch.setattr(client_any, "post", _raise_request_error, raising=False)

    with pytest.raises(AsyncMemoryLakeMemoryToolError, match="Request failed"):
        await async_tool.clear_all_memory()
