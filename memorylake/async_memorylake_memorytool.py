"""
Asynchronous remote implementation of Anthropic's memory tool contract.

This module mirrors ``memorylake_memorytool`` but provides an async variant that
communicates with the MemoryLake server using ``httpx.AsyncClient``. The
``AsyncMemoryLakeMemoryTool`` class subclasses
``BetaAsyncAbstractMemoryTool`` so it can be registered with Anthropic's async
tooling APIs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import httpx
from anthropic.lib.tools import BetaAsyncAbstractMemoryTool
from anthropic.types.beta import (
    BetaCacheControlEphemeralParam,
    BetaMemoryTool20250818Command,
    BetaMemoryTool20250818CreateCommand,
    BetaMemoryTool20250818DeleteCommand,
    BetaMemoryTool20250818InsertCommand,
    BetaMemoryTool20250818RenameCommand,
    BetaMemoryTool20250818StrReplaceCommand,
    BetaMemoryTool20250818ViewCommand,
)
from pydantic import TypeAdapter
from typing_extensions import override

from ._version import __version__

JsonDict = dict[str, object]


def _dict_with_string_keys(source: Mapping[object, object]) -> JsonDict:
    return {str(key): value for key, value in source.items()}


__all__ = ["AsyncMemoryLakeMemoryTool", "AsyncMemoryLakeMemoryToolError"]


class AsyncMemoryLakeMemoryToolError(Exception):
    """Base error raised by :class:`AsyncMemoryLakeMemoryTool`."""


class AsyncMemoryLakeMemoryTool(BetaAsyncAbstractMemoryTool):
    """Remote HTTP-based async implementation of the Anthropic memory tool contract."""

    _COMMAND_ADAPTER: Final[TypeAdapter[BetaMemoryTool20250818Command]] = TypeAdapter(
        BetaMemoryTool20250818Command,
    )
    _REQUEST_VERSION: Final[str] = "claude_memory_tool_20250818"
    _API_ENDPOINT: Final[str] = "/public/v1/memory-tool"

    def __init__(
        self,
        base_url: str,
        memory_id: str,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        *,
        cache_control: BetaCacheControlEphemeralParam | None = None,
    ) -> None:
        """
        Initialize the remote async memory tool client.

        Args:
            base_url: Base URL of the MemoryLake server (e.g., "https://api.memorylake.example.com")
            memory_id: Unique memory identifier (e.g., "mem-42d72643d1af4f22892f00f3d953c428")
            timeout: Request timeout in seconds (default: 30.0)
            headers: Optional additional HTTP headers (e.g., for authentication)
            cache_control: Optional cache control parameter for Anthropic tool registration
        """
        super().__init__(cache_control=cache_control)
        self._base_url: str = base_url.rstrip("/")
        self._memory_id: str = memory_id
        self._timeout: float = timeout
        base_headers: dict[str, str] = dict(headers) if headers is not None else {}
        merged_headers: dict[str, str] = {**base_headers, "x-memorylake-client-version": __version__}
        self._headers: dict[str, str] = dict(merged_headers)
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers=self._headers,
        )
        self._client_entered: bool = False
        self._closed: bool = False

    async def __aenter__(self) -> "AsyncMemoryLakeMemoryTool":
        if self._closed:
            raise AsyncMemoryLakeMemoryToolError("Client is closed and cannot be re-entered.")
        await self._client.__aenter__()
        self._client_entered = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        if self._client_entered:
            await self._client.__aexit__(exc_type, exc, tb)
            self._client_entered = False
            self._closed = True

    async def close(self) -> None:
        """Explicitly close the HTTP client connection."""
        if self._closed:
            return
        if self._client_entered:
            await self._client.__aexit__(None, None, None)
            self._client_entered = False
        else:
            await self._client.aclose()
        self._closed = True

    async def _execute_remote_command(self, payload: dict[str, Any]) -> str:
        """
        Execute a command on the remote server.

        Args:
            payload: Command payload to send

        Returns:
            Response text from the server

        Raises:
            AsyncMemoryLakeMemoryToolError: If the request fails or returns an error
        """
        request_body: dict[str, Any] = {
            "memory_id": self._memory_id,
            "request": self._REQUEST_VERSION,
            "payload": payload,
        }

        try:
            response = await self._client.post(self._API_ENDPOINT, json=request_body)
            response.raise_for_status()
            result_obj: object = response.json()

            if isinstance(result_obj, dict):
                result_dict = _dict_with_string_keys(result_obj)
                error_value = result_dict.get("error")
                if error_value is not None:
                    raise AsyncMemoryLakeMemoryToolError(str(error_value))

                content_value = result_dict.get("content")
                if content_value is None:
                    raise AsyncMemoryLakeMemoryToolError(
                        f"Invalid response: missing 'content' field: {result_dict}",
                    )

                return str(content_value)

            return str(result_obj)
        except httpx.HTTPStatusError as exc:
            error_detail: str = f"HTTP {exc.response.status_code}"
            try:
                error_json: object = exc.response.json()
                if isinstance(error_json, dict):
                    dict_body = _dict_with_string_keys(error_json)
                    error_value = dict_body.get("error") or dict_body.get("detail")
                    if error_value is not None:
                        error_detail = str(error_value)
                elif isinstance(error_json, list):
                    list_body: list[object] = list(error_json)
                    if list_body:
                        first_entry = list_body[0]
                        if isinstance(first_entry, dict):
                            first_dict = _dict_with_string_keys(first_entry)
                            detail_value = first_dict.get("detail") or first_dict.get("msg")
                            if detail_value is not None:
                                error_detail = str(detail_value)
                elif isinstance(error_json, str):
                    error_detail = error_json
            except Exception:
                error_detail = exc.response.text or error_detail
            raise AsyncMemoryLakeMemoryToolError(f"Remote command failed: {error_detail}") from exc
        except httpx.RequestError as exc:
            raise AsyncMemoryLakeMemoryToolError(f"Request failed: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Tool interface (invoked by Anthropic runtime)
    # ------------------------------------------------------------------ #
    @override
    async def view(self, command: BetaMemoryTool20250818ViewCommand) -> str:
        payload: dict[str, Any] = {
            "command": "view",
            "path": command.path,
        }
        if command.view_range is not None:
            payload["view_range"] = command.view_range

        return await self._execute_remote_command(payload)

    @override
    async def create(self, command: BetaMemoryTool20250818CreateCommand) -> str:
        payload = {
            "command": "create",
            "path": command.path,
            "file_text": command.file_text,
        }
        return await self._execute_remote_command(payload)

    @override
    async def str_replace(self, command: BetaMemoryTool20250818StrReplaceCommand) -> str:
        payload = {
            "command": "str_replace",
            "path": command.path,
            "old_str": command.old_str,
            "new_str": command.new_str,
        }
        return await self._execute_remote_command(payload)

    @override
    async def insert(self, command: BetaMemoryTool20250818InsertCommand) -> str:
        payload = {
            "command": "insert",
            "path": command.path,
            "insert_line": command.insert_line,
            "insert_text": command.insert_text,
        }
        return await self._execute_remote_command(payload)

    @override
    async def delete(self, command: BetaMemoryTool20250818DeleteCommand) -> str:
        payload = {
            "command": "delete",
            "path": command.path,
        }
        return await self._execute_remote_command(payload)

    @override
    async def rename(self, command: BetaMemoryTool20250818RenameCommand) -> str:
        payload = {
            "command": "rename",
            "old_path": command.old_path,
            "new_path": command.new_path,
        }
        return await self._execute_remote_command(payload)

    @override
    async def clear_all_memory(self) -> str:
        payload = {"command": "clear_all_memory"}
        return await self._execute_remote_command(payload)

    async def execute_tool_payload(self, payload: Mapping[str, object]) -> str:
        """Validate and execute a raw tool payload from Anthropic responses."""
        command: BetaMemoryTool20250818Command = self._COMMAND_ADAPTER.validate_python(payload)
        result = await self.execute(command)
        return str(result)
