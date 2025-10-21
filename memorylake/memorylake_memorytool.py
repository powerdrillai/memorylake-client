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
from typing import Any, Final

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

__all__ = ["MemoryLakeMemoryTool", "MemoryLakeMemoryToolError"]

from ._version import __version__


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
        self._headers: dict[str, str] = dict(headers) if headers is not None else {}
        merged_headers: dict[str, str] = {**self._headers, "x-memorylake-client-version": __version__}
        self._client: httpx.Client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            headers=merged_headers,
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
            result: Any = response.json()

            # Handle error responses from the server
            if isinstance(result, dict) and "error" in result:
                error_msg: str = str(result["error"])
                raise MemoryLakeMemoryToolError(error_msg)

            # Return the content as a string
            if isinstance(result, dict):
                if "content" not in result:
                    raise MemoryLakeMemoryToolError(f"Invalid response: missing 'content' field: {result}")
                content: Any = result["content"]
                return str(content)
            else:
                return str(result)

        except httpx.HTTPStatusError as exc:
            error_detail: str = f"HTTP {exc.response.status_code}"
            try:
                error_body: Any = exc.response.json()
                if isinstance(error_body, dict) and "error" in error_body:
                    error_detail = str(error_body["error"])
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

    # ------------------------------------------------------------------ #
    # Extended API methods (not part of BetaAbstractMemoryTool)
    # ------------------------------------------------------------------ #
    def memory_exists(self, path: str) -> bool:
        """
        Check if a memory path exists on the remote server.

        Args:
            path: Memory path to check

        Returns:
            True if the path exists, False otherwise

        Raises:
            MemoryLakeMemoryToolError: If the request fails
        """
        request_body: dict[str, Any] = {
            "memory_id": self._memory_id,
            "request": self._REQUEST_VERSION,
            "payload": {"command": "exists", "path": path},
        }

        try:
            response = self._client.post(self._API_ENDPOINT, json=request_body)
            response.raise_for_status()
            result = response.json()
            return bool(result.get("exists", False))
        except httpx.RequestError as exc:
            raise MemoryLakeMemoryToolError(f"Request failed: {exc}") from exc

    def list_memories(self, path: str = "/memories") -> list[str]:
        """
        List all memory paths under the given directory.

        Args:
            path: Directory path to list (default: "/memories")

        Returns:
            List of memory paths

        Raises:
            MemoryLakeMemoryToolError: If the request fails
        """
        request_body: dict[str, Any] = {
            "memory_id": self._memory_id,
            "request": self._REQUEST_VERSION,
            "payload": {"command": "list", "path": path},
        }

        try:
            response = self._client.post(self._API_ENDPOINT, json=request_body)
            response.raise_for_status()
            result: Any = response.json()

            if not isinstance(result, dict):
                raise MemoryLakeMemoryToolError(f"Invalid response format: expected dict, got {type(result).__name__}")

            memories: Any = result.get("memories", [])
            if not isinstance(memories, list):
                raise MemoryLakeMemoryToolError(f"Invalid memories format: expected list, got {type(memories).__name__}")

            return [str(item) for item in memories]
        except httpx.HTTPStatusError as exc:
            error_detail: str = f"HTTP {exc.response.status_code}"
            try:
                error_body: Any = exc.response.json()
                if isinstance(error_body, dict) and "error" in error_body:
                    error_detail = str(error_body["error"])
            except Exception:
                error_detail = exc.response.text or error_detail
            raise MemoryLakeMemoryToolError(f"List failed: {error_detail}") from exc
        except httpx.RequestError as exc:
            raise MemoryLakeMemoryToolError(f"Request failed: {exc}") from exc

    def stats(self) -> dict[str, int]:
        """
        Get statistics about the remote memory storage.

        Returns:
            Dictionary with keys: "files", "directories", "bytes"

        Raises:
            MemoryLakeMemoryToolError: If the request fails
        """
        request_body: dict[str, Any] = {
            "memory_id": self._memory_id,
            "request": self._REQUEST_VERSION,
            "payload": {"command": "stats"},
        }

        try:
            response = self._client.post(self._API_ENDPOINT, json=request_body)
            response.raise_for_status()
            result: Any = response.json()

            if not isinstance(result, dict):
                raise MemoryLakeMemoryToolError(f"Invalid response format: expected dict, got {type(result).__name__}")

            return {
                "files": int(result.get("files", 0)),
                "directories": int(result.get("directories", 0)),
                "bytes": int(result.get("bytes", 0)),
            }
        except httpx.HTTPStatusError as exc:
            error_detail: str = f"HTTP {exc.response.status_code}"
            try:
                error_body: Any = exc.response.json()
                if isinstance(error_body, dict) and "error" in error_body:
                    error_detail = str(error_body["error"])
            except Exception:
                error_detail = exc.response.text or error_detail
            raise MemoryLakeMemoryToolError(f"Stats failed: {error_detail}") from exc
        except httpx.RequestError as exc:
            raise MemoryLakeMemoryToolError(f"Request failed: {exc}") from exc

    def execute_tool_payload(self, payload: Mapping[str, object]) -> str:
        """Validate and execute a raw tool payload from Anthropic responses."""
        command: BetaMemoryTool20250818Command = self._COMMAND_ADAPTER.validate_python(payload)
        result = self.execute(command)
        # Always return the string representation of the result
        return str(result)

    def close(self) -> None:
        """Explicitly close the HTTP client connection."""
        self._client.close()
