"""
Remote implementation of Anthropic's memory tool contract.

This module exposes ``MemoryLakeMemoryTool`` which subclasses ``BetaAbstractMemoryTool``
and forwards all commands to a remote MemoryLake server via HTTP. It implements the same
interface as the local ``MemoryTool`` but delegates the actual storage and operations
to a remote service.

The remote server is expected to accept the same command payloads and return compatible
responses as the local filesystem-based implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

import httpx
from anthropic.lib.tools import BetaAbstractMemoryTool
from anthropic.types.beta import (
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


__all__ = ["MemoryLakeMemoryTool", "MemoryLakeMemoryToolError"]


class MemoryLakeMemoryToolError(Exception):
    """Base error raised by :class:`MemoryLakeMemoryTool`."""


class MemoryLakeMemoryTool(BetaAbstractMemoryTool):
    """Remote HTTP-based implementation of the Anthropic memory tool contract."""

    _COMMAND_ADAPTER: Final[TypeAdapter[BetaMemoryTool20250818Command]] = TypeAdapter(
        BetaMemoryTool20250818Command
    )
    _REQUEST_VERSION: Final[str] = "claude_memory_tool_20250818"
    _API_ENDPOINT: Final[str] = "/public/v1/memory-tool"

    def __init__(
        self,
        base_url: str,
        memory_id: str,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Initialize the remote memory tool client.

        Args:
            base_url: Base URL of the MemoryLake server (e.g., "https://api.memorylake.example.com")
            memory_id: Unique memory identifier (e.g., "mem-42d72643d1af4f22892f00f3d953c428")
            timeout: Request timeout in seconds (default: 30.0)
            headers: Optional additional HTTP headers (e.g., for authentication)
        """
        super().__init__()
        self._base_url: str = base_url.rstrip("/")
        self._memory_id: str = memory_id
        self._timeout: float = timeout
        base_headers: dict[str, str] = dict(headers) if headers is not None else {}
        merged_headers: dict[str, str] = {**base_headers, "x-memorylake-client-version": __version__}
        self._headers: dict[str, str] = dict(merged_headers)
        self._client: httpx.Client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            headers=self._headers,
        )

    def __del__(self) -> None:
        """Clean up the HTTP client on deletion."""
        if hasattr(self, "_client"):
            self._client.close()

    def _execute_remote_command(self, payload: dict[str, Any]) -> str:
        """
        Execute a command on the remote server.

        Args:
            payload: Command payload to send

        Returns:
            Response text from the server

        Raises:
            MemoryLakeMemoryToolError: If the request fails or returns an error
        """
        # Wrap payload in the full request structure
        request_body: dict[str, Any] = {
            "memory_id": self._memory_id,
            "request": self._REQUEST_VERSION,
            "payload": payload,
        }

        try:
            response = self._client.post(self._API_ENDPOINT, json=request_body)
            response.raise_for_status()
            result_obj: object = response.json()

            if isinstance(result_obj, dict):
                raw_dict = cast(dict[object, object], result_obj)
                result_dict = _dict_with_string_keys(raw_dict)
                error_value = result_dict.get("error")
                if error_value is not None:
                    raise MemoryLakeMemoryToolError(str(error_value))

                content_value = result_dict.get("content")
                if content_value is None:
                    raise MemoryLakeMemoryToolError(
                        f"Invalid response: missing 'content' field: {result_dict}",
                    )

                return str(content_value)

            return str(result_obj)

        except httpx.HTTPStatusError as exc:
            error_detail: str = f"HTTP {exc.response.status_code}"
            try:
                error_json: object = exc.response.json()
                if isinstance(error_json, dict):
                    dict_body = _dict_with_string_keys(cast(dict[object, object], error_json))
                    error_value = dict_body.get("error") or dict_body.get("detail")
                    if error_value is not None:
                        error_detail = str(error_value)
                elif isinstance(error_json, list):
                    list_body = cast(list[object], error_json)
                    if list_body:
                        first_entry = list_body[0]
                        if isinstance(first_entry, dict):
                            first_dict = _dict_with_string_keys(cast(dict[object, object], first_entry))
                            detail_value = first_dict.get("detail") or first_dict.get("msg")
                            if detail_value is not None:
                                error_detail = str(detail_value)
                elif isinstance(error_json, str):
                    error_detail = error_json
            except Exception:
                error_detail = exc.response.text or error_detail

            raise MemoryLakeMemoryToolError(f"Remote command failed: {error_detail}") from exc

        except httpx.RequestError as exc:
            raise MemoryLakeMemoryToolError(f"Request failed: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Tool interface (invoked by Anthropic runtime)
    # ------------------------------------------------------------------ #
    @override
    def view(self, command: BetaMemoryTool20250818ViewCommand) -> str:
        payload: dict[str, Any] = {
            "command": "view",
            "path": command.path,
        }
        if command.view_range is not None:
            payload["view_range"] = command.view_range

        return self._execute_remote_command(payload)

    @override
    def create(self, command: BetaMemoryTool20250818CreateCommand) -> str:
        payload = {
            "command": "create",
            "path": command.path,
            "file_text": command.file_text,
        }
        return self._execute_remote_command(payload)

    @override
    def str_replace(self, command: BetaMemoryTool20250818StrReplaceCommand) -> str:
        payload = {
            "command": "str_replace",
            "path": command.path,
            "old_str": command.old_str,
            "new_str": command.new_str,
        }
        return self._execute_remote_command(payload)

    @override
    def insert(self, command: BetaMemoryTool20250818InsertCommand) -> str:
        payload = {
            "command": "insert",
            "path": command.path,
            "insert_line": command.insert_line,
            "insert_text": command.insert_text,
        }
        return self._execute_remote_command(payload)

    @override
    def delete(self, command: BetaMemoryTool20250818DeleteCommand) -> str:
        payload = {
            "command": "delete",
            "path": command.path,
        }
        return self._execute_remote_command(payload)

    @override
    def rename(self, command: BetaMemoryTool20250818RenameCommand) -> str:
        payload = {
            "command": "rename",
            "old_path": command.old_path,
            "new_path": command.new_path,
        }
        return self._execute_remote_command(payload)

    @override
    def clear_all_memory(self) -> str:
        payload = {"command": "clear_all_memory"}
        return self._execute_remote_command(payload)

    def execute_tool_payload(self, payload: Mapping[str, object]) -> str:
        """Validate and execute a raw tool payload from Anthropic responses."""
        command: BetaMemoryTool20250818Command = self._COMMAND_ADAPTER.validate_python(payload)
        result = self.execute(command)
        # Always return the string representation of the result
        return str(result)

    def close(self) -> None:
        """Explicitly close the HTTP client connection."""
        self._client.close()
